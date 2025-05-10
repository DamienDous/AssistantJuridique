#!/bin/bash
set -e
set -u  # Erreur si variable non définie

# Vérification des arguments
if [ $# -ne 2 ]; then
  echo "Usage: $0 chemin/vers/fichier.pdf chemin/vers/dossier_temporaire"
  exit 1
fi

# Création des répertoires
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

PDF_FILE="$1"
WORKDIR="$2"
export WORKDIR

if [ ! -f "$PDF_FILE" ]; then
  echo "❌ Le fichier PDF n'existe pas : $PDF_FILE"
  exit 1
fi

# Chemins de travail
FILENAME=$(basename "$PDF_FILE" .pdf)
BASE_OUT="$WORKDIR/${FILENAME}_traitement"
IMAGES_DIR="${BASE_OUT}/${FILENAME}_images"
SCANNED_DIR="${BASE_OUT}/${FILENAME}_scanned"
TXT_DIR="${BASE_OUT}/${FILENAME}_txt"
CORR_DIR="${BASE_OUT}/${FILENAME}_txt_corrige"
FINAL_PDF="${BASE_OUT}/${FILENAME}_final_corrige.pdf"

mkdir -p "$IMAGES_DIR" "$SCANNED_DIR" "$TXT_DIR" "$CORR_DIR"

# Étape 1 : PDF → TIFF
echo "📄 Étape 1 : PDF → TIFF"
pdftoppm -r 300 "$PDF_FILE" "$IMAGES_DIR/page" -tiff

# Étape 2 : ScanTailor
echo "🔧 Étape 2 : ScanTailor"
scantailor-cli --layout=1 --content-detection=normal --deskew=auto --output-dpi=300 --despeckle=strong \
  -c textord_no_rejects=1 "$IMAGES_DIR" "$SCANNED_DIR"

## Étape 3 : OCR complet avec OCRmyPDF
echo "🔠 Étape 3 : OCR et génération PDF searchable avec ocrmypdf"
CLEANPDF="$BASE_OUT/${FILENAME}_scanned.pdf"
ocrmypdf --force-ocr --language fra --tesseract-pagesegmode 1 \
  "$CLEANPDF" "$FINAL_PDF"

## Étape 4 : Extraction du texte corrigé
echo "📂 Étape 4 : Extraction du texte pour LanguageTool"
pdftotext -layout "$FINAL_PDF" "$TXT_DIR/${FILENAME}.txt"

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

## Étape 8 : Extraction et mise à jour du dictionnaire métier
DICT_FILE="/app/dico_juridique.txt"
echo "🏷️ Étape 8 : Extraction des candidats lexique et mise à jour du dictionnaire → $DICT_FILE"
# On prépare le fichier
mkdir -p "$(dirname "$DICT_FILE")"
touch "$DICT_FILE"

# Extraction des termes en MAJ (ou capitalisés en début de mot),
# on ne garde que ceux >3 caractères et apparus >1 fois
grep -hoE '\b[[:upper:]][[:alpha:]]+(?:\s+[[:upper:]][[:alpha:]]+)*\b' \
  "$CORR_DIR/${FILENAME}.txt" \
  | sort | uniq -c \
  | awk '$1>1 && length($2)>3 { print $2 }' \
  >> "$DICT_FILE"

# Dé-duplication & tri du dictionnaire
sort -u "$DICT_FILE" -o "$DICT_FILE"

echo "✅ Dictionnaire métier mis à jour : $(wc -l < "$DICT_FILE") termes"

## Étape 9 : Copie du texte corrigé
echo "📋 Étape 9 : Copie du texte corrigé dans output/"
cp "$CORR_DIR/${FILENAME}.txt" \
   "$ROOT_DIR/traitement_lot/output/${FILENAME}.txt"

