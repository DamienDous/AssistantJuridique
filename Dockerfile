# ------------------------
# Étape 1 : builder
# ------------------------
FROM ubuntu:18.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    TESSDATA_PREFIX=/usr/share/tessdata \
    CC=gcc-9 \
    CXX=g++-9

# 1. Installer les dépendances de build
RUN apt-get update && \
apt-get install -y --no-install-recommends \
    software-properties-common \
&& add-apt-repository ppa:ubuntu-toolchain-r/test -y \
&& apt-get update && \
apt-get install -y --no-install-recommends \
    git build-essential pkg-config \
    gcc-9 g++-9 \
    autoconf automake libtool cmake \
    libleptonica-dev libtiff-dev libpng-dev libjpeg-dev zlib1g-dev \
    poppler-utils python3 python3-pip default-jre \
    qt4-qmake libqt4-dev libxrender-dev libx11-dev libxext-dev libgl1-mesa-dev \
    libboost-all-dev \
    && update-alternatives --install /usr/bin/gcc  gcc  /usr/bin/gcc-9 100 \
    && update-alternatives --install /usr/bin/g++  g++  /usr/bin/g++-9 100 \
&& rm -rf /var/lib/apt/lists/*

# 2. Compiler ScanTailor CLI
RUN git clone https://github.com/scantailor/scantailor.git /opt/scantailor && \
    cd /opt/scantailor && \
    sed -i 's/cmake_minimum_required(VERSION 2.6)/cmake_minimum_required(VERSION 3.5)/' CMakeLists.txt && \
    mkdir build && cd build && cmake .. -DQT_QMAKE_EXECUTABLE=/usr/bin/qmake && \
    make -j"$(nproc)" && \
    cp scantailor-cli /usr/local/bin/ && \
    rm -rf /opt/scantailor

# 3. Compiler et installer Tesseract 5
RUN git clone --depth 1 https://github.com/tesseract-ocr/tesseract.git /opt/tesseract && \
    cd /opt/tesseract && \
    ./autogen.sh && \
    ./configure --disable-legacy --enable-shared \
        CXXFLAGS="-std=c++17 -Wno-format-security -Wno-error=format-security" && \
    make -j"$(nproc)" && \
    make install && ldconfig && \
    mkdir -p $TESSDATA_PREFIX/configs && \
    cp -r tessdata/configs/* $TESSDATA_PREFIX/configs/ && \
    rm -rf /opt/tesseract

# 4. Récupérer uniquement les données linguistiques
RUN git clone --depth 1 https://github.com/tesseract-ocr/tessdata.git /tmp/tessdata && \
    cp /tmp/tessdata/*.traineddata $TESSDATA_PREFIX/ && \
    rm -rf /tmp/tessdata

# 5. Installer les librairies Python + OCRmyPDF
WORKDIR /app
COPY requirements.txt /app/
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel && \
    pip3 install --no-cache-dir -r requirements.txt && \
    pip3 install --no-cache-dir ocrmypdf

# 6. Copier ton application
COPY . /app

# ------------------------
# Étape 2 : runtime
# ------------------------
FROM ubuntu:18.04

ENV DEBIAN_FRONTEND=noninteractive \
    TESSDATA_PREFIX=/usr/share/tessdata \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

## Avant tout, activer universe en forçant IPv4
RUN apt-get -o Acquire::ForceIPv4=true update && \
    apt-get -o Acquire::ForceIPv4=true install -y --no-install-recommends \
      apt-transport-https ca-certificates software-properties-common && \
    sed -i 's|http://archive.ubuntu.com/|https://archive.ubuntu.com/|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com/|https://security.ubuntu.com/|g' /etc/apt/sources.list && \
    add-apt-repository universe && \
    rm -rf /var/lib/apt/lists/*

## Installer tous les libs restants, toujours en IPv4
RUN apt-get -o Acquire::ForceIPv4=true update && \
    apt-get -o Acquire::ForceIPv4=true install -y --no-install-recommends \
      libgomp1 \
      libleptonica5 libtiff5 libpng16-16 libjpeg8 zlib1g \
      poppler-utils ghostscript qpdf \
      python3 python3-pip default-jre \
      libqtcore4 libqtgui4 libqt4-network libxrender1 libx11-6 libxext6 libgl1-mesa-glx \
    && pip3 install --no-cache-dir img2pdf \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3 1 \
    && rm -rf /var/lib/apt/lists/*

# installer et générer le locale français
RUN apt-get update \
 && apt-get install -y --no-install-recommends locales \
 && locale-gen fr_FR.UTF-8 \
 && update-locale LANG=fr_FR.UTF-8 LC_ALL=fr_FR.UTF-8
 
# 2. Copier les binaires compilés et données
COPY --from=builder /usr/local/bin/tesseract /usr/local/bin/
COPY --from=builder /usr/local/bin/scantailor-cli /usr/local/bin/
# Copier les libs Tesseract (construites dans le builder) vers le runtime
COPY --from=builder /usr/local/lib/libtesseract.so.5* /usr/local/lib/
# copier la libstdc++ du builder (GCC-9)
COPY --from=builder /usr/lib/x86_64-linux-gnu/libstdc++.so.6 /usr/lib/x86_64-linux-gnu/libstdc++.so.6
# Mettre à jour le cache de ld
RUN ldconfig
COPY --from=builder /usr/share/tessdata /usr/share/tessdata
# Copier aussi les libs Boost nécessaires (runtime)
COPY --from=builder /usr/lib/x86_64-linux-gnu/libboost_system.so.1.65.1 /usr/lib/x86_64-linux-gnu/
COPY --from=builder /usr/lib/x86_64-linux-gnu/libboost_filesystem.so.1.65.1 /usr/lib/x86_64-linux-gnu/
# 3. Copier les modules Python et OCRmyPDF
COPY --from=builder /usr/local/lib/python3.6/dist-packages /usr/local/lib/python3.6/dist-packages

# copier les scripts CLI installés par pip dans builder
COPY --from=builder /usr/local/bin/ocrmypdf /usr/local/bin/
COPY dico_juridique.txt /app/dico_juridique.txt
# Copier votre script de structuration
COPY pipeline_OCR/pipelines/pipeline_base/structure_juridique.py /app/pipeline_OCR/pipelines/pipeline_base/structure_juridique.py

# 4. Copier ton code APP
WORKDIR /app
COPY --from=builder /app /app

# 5. Entrypoint
CMD ["/bin/bash"]