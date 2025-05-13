# ------------------------
# Étape 1 : builder
# ------------------------
FROM ubuntu:22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    TESSDATA_PREFIX=/usr/share/tessdata

RUN apt-get update && \
      apt-get install -y --no-install-recommends \
      ca-certificates curl git wget \
      build-essential pkg-config \
      gcc g++ cmake autoconf automake libtool \
      qt5-qmake qtbase5-dev qtbase5-dev-tools qttools5-dev qttools5-dev-tools \
      libqt5svg5-dev libqt5opengl5-dev \
      libxrender-dev libx11-dev libxext-dev libgl1-mesa-dev \
      libboost-all-dev \
      libleptonica-dev libcurl4-openssl-dev libjpeg-dev \
      libpng-dev libtiff-dev \
      python3 python3-pip python3-setuptools python3-wheel \
      poppler-utils default-jre \
    && rm -rf /var/lib/apt/lists/*

# 2. Compiler ScanTailor CLI (avec détection Qt dynamique)
RUN git clone https://github.com/4lex4/scantailor-advanced.git /opt/scantailor && \
    cd /opt/scantailor && \
    mkdir build && cd build && \
    ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ]; then \
        LIBARCH="aarch64-linux-gnu"; \
    else \
        LIBARCH="x86_64-linux-gnu"; \
    fi && \
    echo "Using Qt5 path: /usr/lib/$LIBARCH/cmake/Qt5" && \
    cmake .. \
        -DCMAKE_PREFIX_PATH="/usr/lib/qt5;/usr/lib/$LIBARCH/cmake/Qt5" \
        -DQT_QMAKE_EXECUTABLE=/usr/lib/qt5/bin/qmake \
        -DQt5LinguistTools_DIR=/usr/lib/$LIBARCH/cmake/Qt5LinguistTools \
        -DCMAKE_INSTALL_PREFIX=/opt/scantailor/install && \
    make -j"$(nproc)" && \
    make install

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

# 4. Récupérer les données linguistiques Tesseract
RUN git clone --depth 1 https://github.com/tesseract-ocr/tessdata.git /tmp/tessdata && \
    cp /tmp/tessdata/*.traineddata $TESSDATA_PREFIX/ && \
    rm -rf /tmp/tessdata

# 5. Installer les paquets Python + OCRmyPDF
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
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    TESSDATA_PREFIX=/usr/share/tessdata \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      libgomp1 \
      libleptonica-dev libtiff5 libpng16-16 libjpeg8 zlib1g \
      poppler-utils ghostscript qpdf \
      python3 python3-pip default-jre \
      libqt5core5a libqt5gui5 libqt5network5 \
      libxrender1 libx11-6 libxext6 libgl1-mesa-glx \
      libxml2-dev libxslt1-dev && \
    pip3 install --no-cache-dir img2pdf && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3 1 && \
    rm -rf /var/lib/apt/lists/*

# Installer les locales
RUN apt-get update && \
    apt-get install -y --no-install-recommends locales && \
    locale-gen fr_FR.UTF-8 && \
    update-locale LANG=fr_FR.UTF-8 LC_ALL=fr_FR.UTF-8

# 2. Copier les binaires compilés
COPY --from=builder /usr/local/bin/tesseract /usr/local/bin/
COPY --from=builder /opt/scantailor/install/bin/scantailor /usr/local/bin/scantailor
COPY --from=builder /usr/local/lib/libtesseract.so.5* /usr/local/lib/
COPY --from=builder /usr/share/tessdata /usr/share/tessdata
# Copier uniquement les bibliothèques de l'architecture active (aarch64 ou x86_64)
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        cp -u /usr/lib/x86_64-linux-gnu/libstdc++.so.6 /usr/lib/x86_64-linux-gnu/ || true && \
        cp -u /usr/lib/x86_64-linux-gnu/libboost_system.so.1.74.0 /usr/lib/x86_64-linux-gnu/ || true && \
        cp -u /usr/lib/x86_64-linux-gnu/libboost_filesystem.so.1.74.0 /usr/lib/x86_64-linux-gnu/ || true ; \
    else \
        cp -u /usr/lib/aarch64-linux-gnu/libstdc++.so.6 /usr/lib/aarch64-linux-gnu/ || true && \
        cp -u /usr/lib/aarch64-linux-gnu/libboost_system.so.1.74.0 /usr/lib/aarch64-linux-gnu/ || true && \
        cp -u /usr/lib/aarch64-linux-gnu/libboost_filesystem.so.1.74.0 /usr/lib/aarch64-linux-gnu/ || true ; \
    fi
COPY --from=builder /usr/local/lib/python3.10/dist-packages /usr/local/lib/python3.10/dist-packages
COPY --from=builder /usr/local/bin/ocrmypdf /usr/local/bin/
COPY dico_juridique.txt /app/dico_juridique.txt
COPY pipeline_OCR/pipelines/pipeline_base/structure_juridique.py /app/pipeline_OCR/pipelines/pipeline_base/structure_juridique.py

WORKDIR /app
COPY --from=builder /app /app

CMD ["/bin/bash"]
