FROM debian:buster

ENV DEBIAN_FRONTEND=noninteractive

# --- Étape 1 : Installer toutes les dépendances système ---
    RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    qt4-qmake \
    libqt4-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    zlib1g-dev \
    libboost-all-dev \
    libxrender-dev \
    git \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-fra \
    python3 \
    python3-pip \
    ghostscript \
    default-jre \
 && rm -rf /var/lib/apt/lists/*

# --- Étape 2 : Compiler et installer scantailor-cli (version originale) ---
RUN git clone https://github.com/scantailor/scantailor.git /opt/scantailor && \
    cd /opt/scantailor && \
    sed -i 's/cmake_minimum_required(VERSION 2.6)/cmake_minimum_required(VERSION 3.5)/' CMakeLists.txt && \
    mkdir build && cd build && \
    cmake .. -DQT_QMAKE_EXECUTABLE=/usr/bin/qmake && \
    make -j$(nproc) && \
    cp scantailor-cli /usr/local/bin/

# --- Étape 3 : Copier ton code dans le conteneur ---
WORKDIR /app
COPY . /app

# --- Étape 4 : Installer les dépendances Python ---
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel
RUN pip3 install --no-cache-dir -r requirements.txt

# --- Étape finale : shell par défaut ---
CMD ["/bin/bash"]
