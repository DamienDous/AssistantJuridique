# ------------------------
# Étape 1 : builder
# ------------------------
FROM ubuntu:18.04 AS builder
ENV TESSDATA_PREFIX=/usr/local/share/tessdata
ENV DEBIAN_FRONTEND=noninteractive \
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
    poppler-utils python3 python3-pip \
    qt4-qmake libqt4-dev libxrender-dev libx11-dev libxext-dev libgl1-mesa-dev \
    libboost-all-dev \
    && update-alternatives --install /usr/bin/gcc  gcc  /usr/bin/gcc-9 100 \
    && update-alternatives --install /usr/bin/g++  g++  /usr/bin/g++-9 100 \
&& rm -rf /var/lib/apt/lists/*

# Installer curl et compiler Ghostscript 9.56
RUN apt-get update && apt-get install -y curl && \
    curl -LO https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs9560/ghostscript-9.56.0.tar.gz && \
    tar -xzf ghostscript-9.56.0.tar.gz && cd ghostscript-9.56.0 && \
    ./configure && make -j"$(nproc)" && make install && \
    cd .. && rm -rf ghostscript-9.56.0*

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
RUN mkdir -p $TESSDATA_PREFIX
RUN git clone --depth 1 https://github.com/tesseract-ocr/tessdata.git /tmp/tessdata && \
    cp /tmp/tessdata/*.traineddata $TESSDATA_PREFIX/ && \
    cp /tmp/tessdata/osd.traineddata $TESSDATA_PREFIX/ && \
    rm -rf /tmp/tessdata

# Installer Python 3.8 manuellement
RUN add-apt-repository ppa:deadsnakes/ppa -y && \
apt-get update && \
apt-get install -y python3.8 python3.8-dev python3.8-distutils curl && \
curl -sS https://bootstrap.pypa.io/pip/3.8/get-pip.py | python3.8

RUN ln -sf /usr/bin/python3.8 /usr/bin/python && \
    ln -sf /usr/local/bin/pip /usr/bin/pip3

# 5. Installer les librairies Python + OCRmyPDF
WORKDIR /app
COPY requirements.txt /app/
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel && \
    pip3 install --no-cache-dir pymupdf==1.22.3 && \
    pip3 install --no-cache-dir -r requirements.txt && \
    pip3 install --no-cache-dir ocrmypdf && \
    pip3 install --no-cache-dir pikepdf==6.2.4 && \
    pip3 install --no-cache-dir img2pdf

# 6. Copier ton application
COPY . /app

# ------------------------
# Étape 2 : runtime
# ------------------------
FROM ubuntu:18.04

ENV DEBIAN_FRONTEND=noninteractive \
    TESSDATA_PREFIX=/usr/local/share/tessdata \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONPATH="/usr/local/lib/python3.8/dist-packages"

# 1. Runtime minimal : libs image, PDF, Python, Java, OCRmyPDF dépendances
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgomp1 \
    libleptonica-dev libtiff5 libpng16-16 libjpeg8 zlib1g \
    poppler-utils qpdf \
    python3.8 python3.8-distutils python3-pip \
    libqtcore4 libqtgui4 libqt4-network libxrender1 libx11-6 libxext6 libgl1-mesa-glx \
    libboost-system1.65.1 libboost-filesystem1.65.1 bc unpaper libvips-tools && \
    ln -sf /usr/bin/python3.8 /usr/bin/python && \
    ln -sf /usr/bin/python3.8 /usr/bin/python3 && \
    ln -sf /usr/local/bin/pip /usr/bin/pip3 && \
    rm -rf /var/lib/apt/lists/*

# installer et générer le locale français
RUN apt-get update \
 && apt-get install -y --no-install-recommends locales \
 && locale-gen fr_FR.UTF-8 \
 && update-locale LANG=fr_FR.UTF-8 LC_ALL=fr_FR.UTF-8
 
# 2. Copier binaires et bibliothèques nécessaires depuis le builder
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder /usr/local/lib/ /usr/local/lib/
COPY --from=builder /usr/local/lib/python3.8/dist-packages /usr/local/lib/python3.8/dist-packages
COPY --from=builder /usr/local/share/tessdata /usr/local/share/tessdata
# Copier l'interpréteur Python 3.8 et pip
COPY --from=builder /usr/bin/python3.8 /usr/bin/python3.8
COPY --from=builder /usr/local/bin/pip /usr/local/bin/pip
# Mettre à jour les liens symboliques
RUN ln -sf /usr/bin/python3.8 /usr/bin/python && \
    ln -sf /usr/local/bin/pip /usr/bin/pip3
COPY --from=builder /usr/lib/x86_64-linux-gnu/libstdc++.so.6 /usr/lib/x86_64-linux-gnu/libstdc++.so.6
COPY --from=builder /usr/local/bin/gs /usr/local/bin/gs
COPY --from=builder /usr/local/lib/libgs.so* /usr/local/lib/
# Mettre à jour le cache de ld
RUN ldconfig
# Copier les scripts
COPY dico_juridique.txt /app/dico_juridique.txt
COPY pipeline_OCR/pipelines/pipeline_base/structure_juridique.py /app/pipeline_OCR/pipelines/pipeline_base/structure_juridique.py

# 4. Copier ton code APP
WORKDIR /app
COPY --from=builder /app /app

# 5. Entrypoint
CMD ["/bin/bash"]