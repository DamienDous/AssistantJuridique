FROM python:3.10-slim

# 1. Mise à jour et installation des dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
	unzip \
	poppler-utils \
	tesseract-ocr \
	tesseract-ocr-fra \
	unpaper \
	imagemagick \
	ghostscript \
	curl \
	openjdk-17-jre-headless \
	&& rm -rf /var/lib/apt/lists/*

# 2. Installation des dépendances Python
RUN pip install --no-cache-dir pillow numpy ocrmypdf language_tool_python

# 3. Création des dossiers utilisés par le pipeline
RUN mkdir -p /data /data/out/pdf /data/out/txt /data/logs /tools

# RUN curl -L -o /tools/LanguageTool-6.4.zip https://languagetool.org/download/LanguageTool-6.4.zip \
#  && unzip /tools/LanguageTool-6.4.zip -d /tools/ \
#  && rm /tools/LanguageTool-6.4.zip

# 4. Scripts utilitaires (tout est maintenant dans /tools)
COPY ocr_script.sh                                          /tools/ocr_script.sh
COPY tools/read_and_crop.py                                 /tools/read_and_crop.py
COPY pipeline_OCR/pipelines/pipeline_base/clean_text.sh		/tools/clean_text.sh
COPY pipeline_OCR/pipelines/pipeline_base/04_correction.py	/tools/04_correction.py
COPY dico_juridique.txt										/app/dico_juridique.txt

# 5. Droits d’exécution sur les scripts bash
RUN chmod +x /tools/*.sh

# 6. Dossier de travail par défaut
WORKDIR /data

# 7. Commande par défaut (tu peux la surcharger au run)
CMD ["/bin/bash"]
