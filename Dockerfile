# Base Dockerfile minimal Ubuntu 18.04 pour Tesseract 5 et pipeline OCR
FROM ubuntu:18.04

ENV DEBIAN_FRONTEND=noninteractive \
    TESSDATA_PREFIX=/usr/share/tessdata \
    CC=gcc-9 \
    CXX=g++-9 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONIOENCODING=utf-8

# 1) Mise à jour du système et installation des outils de base (cacheable)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      software-properties-common \
      ca-certificates \
      git \
 && rm -rf /var/lib/apt/lists/*

# 2) Configuration des dépôts pour GCC-9 (cacheable)
RUN add-apt-repository ppa:ubuntu-toolchain-r/test -y && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      gcc-9 g++-9 \
 && update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-9 100 \
 && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-9 100 \
 && rm -rf /var/lib/apt/lists/*

# 3) Installation des bibliothèques de build et runtime (cacheable)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential pkg-config \
      libleptonica-dev libtiff-dev libpng-dev libjpeg-dev zlib1g-dev poppler-utils \
      python3 python3-pip default-jre \
      autoconf automake libtool cmake \
      ghostscript qpdf \
      qt4-qmake libqt4-dev libxrender-dev libx11-dev libxext-dev libgl1-mesa-dev libboost-all-dev \
 && rm -rf /var/lib/apt/lists/*

# 4) Compiler ScanTailor CLI (cacheable)
RUN git clone https://github.com/scantailor/scantailor.git /opt/scantailor && \
    cd /opt/scantailor && \
    sed -i 's/cmake_minimum_required(VERSION 2.6)/cmake_minimum_required(VERSION 3.5)/' CMakeLists.txt && \
    mkdir build && cd build && cmake .. -DQT_QMAKE_EXECUTABLE=/usr/bin/qmake && \
    make -j"$(nproc)" && cp scantailor-cli /usr/local/bin/ && rm -rf /opt/scantailor

# 5) Compiler et installer Tesseract 5 (lourd, cacheable)
RUN git clone --depth 1 https://github.com/tesseract-ocr/tesseract.git /opt/tesseract && \
    cd /opt/tesseract && \
    ./autogen.sh && \
    ./configure --disable-legacy --enable-shared \
      CXXFLAGS="-std=c++17 -Wno-format-security -Wno-error=format-security" && \
    make -j"$(nproc)" && make install && ldconfig && \
    mkdir -p $TESSDATA_PREFIX/configs && \
    cp -r /opt/tesseract/tessdata/configs/* $TESSDATA_PREFIX/configs/ && \
    rm -rf /opt/tesseract

# 6) Télécharger modèles linguistiques (traineddata) seulement
RUN git clone --depth 1 https://github.com/tesseract-ocr/tessdata.git /tmp/tessdata && \
    cp /tmp/tessdata/*.traineddata $TESSDATA_PREFIX/ && \
    rm -rf /tmp/tessdata

# 7) Préparer Python : copier requirements et installer (isolé des autres couches)
WORKDIR /app
COPY requirements.txt /app/
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel && \
    pip3 install --no-cache-dir -r requirements.txt

# 8) Copier le code et installer OCRmyPDF (couche légère à part)
COPY . /app
RUN pip3 install --no-cache-dir ocrmypdf

# 9) Entrypoint
CMD ["/bin/bash"]
