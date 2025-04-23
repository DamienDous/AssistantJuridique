#!/bin/bash
set -e
set -u  # Erreur si variable non définie

# Vérification des arguments
if [ $# -ne 2 ]; then
  echo "Usage: $0 chemin/vers/fichier.pdf chemin/vers/dossier_temporaire"
  exit 1
fi

# Création automatique des répertoires nécessaires
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Vérification des arguments
if [ $# -ne 2 ]; then
  echo "Usage: $0 chemin/vers/fichier.pdf chemin/vers/dossier_temporaire"
  exit 1
fi

PDF_FILE="$1"
WORKDIR="$2"
export WORKDIR="$2"

if [ ! -f "$PDF_FILE" ]; then
  echo "❌ Le fichier PDF n'existe pas : $PDF_FILE"
  exit 1
fi

# Export de TESSDATA_PREFIX si non défini
if [ -z "${TESSDATA_PREFIX:-}" ]; then
  if [ -f "$HOME/Fork/tessdata/fra.traineddata" ]; then
    export TESSDATA_PREFIX="$HOME/Fork/tessdata"
    echo "ℹ️ TESSDATA_PREFIX défini à $TESSDATA_PREFIX"
  fi
fi

# Variables
FILENAME=$(basename "$PDF_FILE" .pdf)
BASE_OUT="$WORKDIR/${FILENAME}_traitement"
IMAGES_DIR="${BASE_OUT}/${FILENAME}_images"
SCANNED_DIR="${BASE_OUT}/${FILENAME}_scanned"
OCR_DIR="${BASE_OUT}/${FILENAME}_ocr"
TXT_DIR="${BASE_OUT}/${FILENAME}_txt"
CORR_DIR="$WORKDIR/${FILENAME}_traitement/${FILENAME}_txt_corrige"
FINAL_PDF="${BASE_OUT}/${FILENAME}_final_corrige.pdf"

mkdir -p "$IMAGES_DIR" "$SCANNED_DIR" "$OCR_DIR" "$TXT_DIR" "$CORR_DIR"

echo "📄 Étape 1 : PDF → TIFF"
pdftoppm -r 300 "$PDF_FILE" "$IMAGES_DIR/page" -tiff

echo "🔧 Étape 2 : ScanTailor"
scantailor-cli \
  --layout=1 \
  --content-detection=normal \
  --deskew=auto \
  --output-dpi=300 \
  --despeckle=strong \
  -c textord_no_rejects=1 \
  "$IMAGES_DIR" \
  "$SCANNED_DIR"

echo "🔠 Étape 3 : OCR"
for img in "$SCANNED_DIR"/*.tif; do
  base=$(basename "$img" .tif)
  tesseract "$img" "$OCR_DIR/$base" -l fra \
    --psm 6 --oem 1 \
    -c preserve_interword_spaces=1 \
    -c tessedit_char_blacklist='|~' \
    -c textord_heavy_nr=1 \
    -c tessedit_create_pdf=1 \
    -c tessedit_create_txt=1
  mv "$OCR_DIR/$base.txt" "$TXT_DIR/$base.txt"
done

echo "🧠 Étape 4 : Correction avec LanguageTool"
python3 "$(dirname "$0")/04_correction.py"

# 📄 Dossier contenant le texte corrigé
TXT_DIR="${BASE_OUT}/${FILENAME}_txt"

# 📁 Dossier de destination
DEST_DIR="${BASE_OUT}/${FILENAME}_txt_corrige"
mkdir -p "$DEST_DIR"

# 🔍 Recherche du fichier texte le plus crédible
CORRIGE_PATH=$(find "$TXT_DIR" -type f -name "*.txt" | head -n 1)

# ✅ Copie s'il existe
if [[ -f "$CORRIGE_PATH" ]]; then
    cp "$CORRIGE_PATH" "$DEST_DIR/${FILENAME}.txt"
    echo "✅ Texte corrigé copié pour évaluation : $DEST_DIR/${FILENAME}.txt"
else
    echo "❌ Aucun fichier texte corrigé trouvé dans $TXT_DIR"
    exit 1
fi

echo "🧾 Étape 5 : Fusion PDF"
pdfunite "$OCR_DIR"/*.pdf "$FINAL_PDF"

echo "✅ Pipeline terminé ! PDF final corrigé : $FINAL_PDF"

# 📥 Étape 6 : Copie du PDF final dans output local
cp "$FINAL_PDF" "$ROOT_DIR/traitement_lot/output/${FILENAME}_final_corrige.pdf"
echo "✅ PDF final copié dans /app/pipeline_OCR/traitement_lot/output/"