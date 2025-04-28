#!/bin/bash
set -euo pipefail

# Usage: $0 input.pdf workdir
IN_PDF="$1"
WORKDIR="$2"

# variables de chemin
FNAME=$(basename "$IN_PDF" .pdf)
BASE="$WORKDIR/${FNAME}_traitement"
IMGDIR="$BASE/${FNAME}_images"
SCANDIR="$BASE/${FNAME}_scanned"
CLEANPDF="$BASE/${FNAME}_scanned.pdf"
OCRPDF="$BASE/${FNAME}_ocr.pdf"

mkdir -p "$IMGDIR" "$SCANDIR"

# 1) PDF → TIFF @300 dpi
echo "📄 Étape 1 : PDF → TIFF"
pdftoppm -r 300 "$IN_PDF" "$IMGDIR/page" -tiff

# 2) ScanTailor (deskew, layout, despeckle, columbus…)
echo "🔧 Étape 2 : ScanTailor"
scantailor-cli \
  --layout=1 --content-detection=normal --deskew=auto \
  --output-dpi=300 --despeckle=strong \
  -c textord_no_rejects=1 \
  "$IMGDIR" "$SCANDIR"

# 2c) Reconstruction d’un PDF « nettoyé » mono-colonne
echo "📄 Étape 2c : Reconstruction PDF mono-colonne"
img2pdf -o "$CLEANPDF" "$SCANDIR"/*.tif

# 3) OCR avec OCRmyPDF + Tesseract en mode Auto+OSD (PSM 1)
echo "🔠 Étape 3 : OCR et génération PDF searchable"
ocrmypdf \
  --force-ocr \
  --language fra \
  --tesseract-pagesegmode 1 \
  --tesseract-config "--psm 1" \
  "$CLEANPDF" "$OCRPDF"

# 4) Extraction texte brut pour post-traitement
echo "📂 Étape 4 : Extraction du texte pour LanguageTool"
TXT="$BASE/${FNAME}.txt"
pdftotext -layout "$OCRPDF" "$TXT"

## Étape 4b : Nettoyage post-OCR
echo "🧹 Étape 4b : Nettoyage post-OCR"
"$(dirname "$0")/clean_text.sh" \
  "$TXT_DIR/${FILENAME}.txt" \
  "$CORR_DIR/${FILENAME}.txt"

## Étape 5 : Correction linguistique
echo "🧠 Étape 5 : Correction avec LanguageTool"
python3 "$(dirname "$0")/04_correction.py" \
  "$CORR_DIR/${FILENAME}.txt" \
  "$CORR_DIR"

## Étape 6 : Copie et clean-up
cp "$FINAL_PDF" "$ROOT_DIR/traitement_lot/output/${FILENAME}_final_corrige.pdf"
echo "✅ PDF copié dans /app/pipeline_OCR/traitement_lot/output/"

## Étape 7 : Structuration sémantique
echo "🏷️ Étape 7 : Structuration juridique"
python3 "$(dirname "$0")/structure_juridique.py" \
   "$CORR_DIR/${FILENAME}.txt" \
   "$ROOT_DIR/traitement_lot/output/${FILENAME}.json"

  > candidats_lexique.txt

## Étape 8 : Copie du texte corrigé
echo "📋 Étape 8 : Copie du texte corrigé dans output/"
cp "$CORR_DIR/${FILENAME}.txt" \
   "$ROOT_DIR/traitement_lot/output/${FILENAME}.txt"

# Exemple : extraire les suites de mots en majuscules ou capitalisés
grep -hoE '\b[A-Z][A-Za-zéèêçàâûùîï]+(\s+[A-Z][A-Za-zéèêçàâûùîï]+)*\b' \
  pipeline_OCR/traitement_lot/output/*/*_txt_corrige/*.txt \
  | sort | uniq -c | sort -nr \
  | head -n 200 \
