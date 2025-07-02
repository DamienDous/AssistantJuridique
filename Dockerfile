FROM debian:bookworm
RUN apt-get update && apt-get install -y python3 python3-pip

# 1. Mise à jour et installation des dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
	unzip \
	poppler-utils \
	tesseract-ocr \
	tesseract-ocr-fra \
	unpaper \
	ghostscript \
	curl \
	openjdk-17-jre-headless \
	ca-certificates \
	build-essential \
	pkg-config \
	libpng-dev \
	libjpeg-dev \
	libtiff-dev \
	libwebp-dev \
	libopenjp2-7-dev \
	libheif-dev \
	libde265-dev \
	libraw-dev \
	jq \
	&& rm -rf /var/lib/apt/lists/*

# 2. Installation des dépendances Python
RUN pip install --break-system-packages --no-cache-dir pillow numpy ocrmypdf language_tool_python nltk
# Télécharge le tokenizer de phrases français
RUN mkdir -p /usr/share/nltk_data
RUN python3 -c "import nltk; nltk.download('punkt', download_dir='/usr/share/nltk_data')"
RUN python3 -c "import nltk; nltk.download('punkt_tab', download_dir='/usr/share/nltk_data')"

# 3. Création des dossiers utilisés par le pipeline
RUN mkdir -p /data /data/out/pdf /data/out/txt /data/logs /tools

# Téléchargement et extraction de LanguageTool en avance (optionnel)
RUN mkdir -p /tools/lt && \
	curl -L -o /tools/lt.zip https://languagetool.org/download/LanguageTool-6.4.zip && \
	unzip /tools/lt.zip -d /tools/lt && \
	rm /tools/lt.zip
	
# Installation ImageMagick 7 depuis source
RUN curl -L https://imagemagick.org/archive/ImageMagick.tar.gz | tar xz -C /tmp && \
cd /tmp/ImageMagick-* && \
./configure && \
make -j$(nproc) && \
make install && \
ldconfig && \
cd / && \
rm -rf /tmp/ImageMagick-*

RUN magick --version

# 4. Scripts utilitaires (tout est maintenant dans /tools)
COPY OCR/ocr_script.sh                          /tools/ocr_script.sh
COPY CLEAN/read_and_crop.py                     /tools/read_and_crop.py
COPY OCR/clean_text.sh		                    /tools/clean_text.sh
COPY OCR/langage_tool_correction.py	            /tools/langage_tool_correction.py
COPY OCR/dico_juridique.txt						/app/dico_juridique.txt
COPY OCR/entrypoint.sh 							/tools/entrypoint.sh
COPY OCR/batch_ocr_tester.sh 					/tools/batch_ocr_tester.sh
COPY OCR/launch_all.sh 							/tools/launch_all.sh
COPY OCR/vote_ocr_paragraphe.py 				/tools/vote_ocr_paragraphe.py

# 5. Droits d’exécution sur les scripts bash
RUN chmod +x /tools/*.sh
# 6. Dossier de travail par défaut
WORKDIR /

# Entrypoint custom
# ENTRYPOINT ["/tools/launch_all.sh"]

# 7. Commande par défaut (tu peux la surcharger au run)
CMD ["/data", "/data/out", "16"]
