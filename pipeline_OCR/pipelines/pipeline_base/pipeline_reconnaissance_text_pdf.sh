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
OCR_DIR="${BASE_OUT}/${FILENAME}_ocr"
TXT_DIR="${BASE_OUT}/${FILENAME}_txt"
CORR_DIR="${BASE_OUT}/${FILENAME}_txt_corrige"
FINAL_PDF="${BASE_OUT}/${FILENAME}_final_corrige.pdf"

mkdir -p "$IMAGES_DIR" "$SCANNED_DIR" "$OCR_DIR" "$TXT_DIR" "$CORR_DIR"

# Étape 1 : PDF → TIFF
echo "📄 Étape 1 : PDF → TIFF"
pdftoppm -r 300 "$PDF_FILE" "$IMAGES_DIR/page" -tiff

# Étape 2 : ScanTailor
echo "🔧 Étape 2 : ScanTailor"
scantailor-cli --layout=1 --content-detection=normal --deskew=auto --output-dpi=300 --despeckle=strong \
  -c textord_no_rejects=1 "$IMAGES_DIR" "$SCANNED_DIR"

# (Optionnel) Forcer les métadonnées DPI à 300 pour éviter que Tesseract tombe à 70dpi
if command -v exiftool >/dev/null 2>&1; then
  echo "🛠️ Étape 2b : Ajustement DPI des TIFF"
  exiftool -overwrite_original \
           -XResolution=300 -YResolution=300 \
           "$SCANNED_DIR"/*.tif >/dev/null
fi

## Étape 3 : OCR complet avec OCRmyPDF
echo "🔠 Étape 3 : OCR et génération PDF searchable avec ocrmypdf"
# On prend le PDF d’entrée (ou on regroupe les TIFF si besoin via img2pdf)
# Ici on réutilise directement le PDF brut, nettoyé par ScanTailor si vous l'avez reconverti en PDF.
ocrmypdf \
  --force-ocr \
  --language fra \
  "$PDF_FILE" \
  "$FINAL_PDF"

echo "✅ PDF final searchable généré : $FINAL_PDF"

## Étape 4 : Extraction du texte corrigé
echo "📂 Étape 4 : Extraction du texte pour LanguageTool"
mkdir -p "$TXT_DIR"
pdftotext -layout "$FINAL_PDF" "$TXT_DIR/${FILENAME}.txt"

## Étape 5 : Correction linguistique
echo "🧠 Étape 5 : Correction avec LanguageTool"
python3 "$(dirname "$0")/04_correction.py" "$TXT_DIR/${FILENAME}.txt" "$CORR_DIR"

## Étape 6 : Copie et clean-up
cp "$FINAL_PDF" "$ROOT_DIR/traitement_lot/output/${FILENAME}_final_corrige.pdf"
echo "✅ PDF copié dans /app/pipeline_OCR/traitement_lot/output/"
