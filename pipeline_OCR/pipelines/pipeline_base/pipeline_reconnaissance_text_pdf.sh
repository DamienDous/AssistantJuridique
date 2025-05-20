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
CLEANED_DIR="${BASE_OUT}/${FILENAME}_cleaned"
TXT_DIR="${BASE_OUT}/${FILENAME}_txt"
CORR_DIR="${BASE_OUT}/${FILENAME}_txt_corrige"
FINAL_PDF="${BASE_OUT}/${FILENAME}_final_corrige.pdf"

mkdir -p "$IMAGES_DIR" "$SCANNED_DIR" "$CLEANED_DIR" "$TXT_DIR" "$CORR_DIR"

# Étape 1 : PDF → TIFF
echo "📄 Étape 1 : PDF → TIFF"
pdftoppm -r 300 "$PDF_FILE" "$IMAGES_DIR/page" -tiff

# --- ÉTAPE 2 : Nettoyage de l'image (ScanTailor ou unpaper selon plateforme) ---
PLATFORM=$(uname | tr '[:upper:]' '[:lower:]')
USE_SCANTAILOR=false

## Étape 3 : OCR complet avec OCRmyPDF
# Détection docker (Linux) OU Windows
if command -v scantailor-cli >/dev/null 2>&1; then
    USE_SCANTAILOR=true
fi

if $USE_SCANTAILOR; then
    echo "🔧 Étape 2 : ScanTailor CLI détecté, nettoyage avancé..."
    scantailor-cli --layout=1 --content-detection=normal --deskew=auto --output-dpi=300 --despeckle=strong \
        -c textord_no_rejects=1 "$IMAGES_DIR" "$SCANNED_DIR"
    INPUT_IMG_DIR="$SCANNED_DIR"
else
    echo "🧼 Étape 2 : ScanTailor CLI non trouvé, utilisation de unpaper à la place"
    for img in "$IMAGES_DIR"/*.tif; do
      BASENAME=$(basename "$img")
      unpaper --overwrite "$img" "$CLEANED_DIR/$BASENAME"
    done
    INPUT_IMG_DIR="$CLEANED_DIR"
fi

echo "🔠 Étape 3 : OCR et génération PDF searchable avec ocrmypdf"
CLEANPDF="$BASE_OUT/${FILENAME}_cleaned.pdf"
img2pdf "$INPUT_IMG_DIR"/*.tif -o "$CLEANPDF"
ocrmypdf --force-ocr --language fra --tesseract-pagesegmode 1 \
  "$CLEANPDF" "$FINAL_PDF"

# --- ÉTAPE 4 : Extraction du texte global pour correction ---
echo "📂 Étape 4 : Extraction du texte pour LanguageTool"
pdftotext -layout "$FINAL_PDF" "$TXT_DIR/${FILENAME}.txt"

# --- ÉTAPE 5 : Extraction du texte brut par page (optionnel, NLP) ---
echo "📂 Étape 5 : Extraction du texte brut par page avec tesseract"
for img in "$INPUT_IMG_DIR"/*.tif; do
  OUTFILE="$TXT_DIR/$(basename "${img%.tif}").txt"
  tesseract "$img" "${OUTFILE%.txt}" -l fra+eng
done

# --- ÉTAPE 6 : Nettoyage post-OCR (script custom) ---
echo "🧹 Étape 6 : Nettoyage post-OCR"
"$SCRIPT_DIR/clean_text.sh" \
  "$TXT_DIR/${FILENAME}.txt" \
  "$CORR_DIR/${FILENAME}.txt"

# --- ÉTAPE 7 : Correction linguistique (LanguageTool Python) ---
echo "🧠 Étape 7 : Correction avec LanguageTool"
python3 "$SCRIPT_DIR/04_correction.py" \
  "$CORR_DIR/${FILENAME}.txt" \
  "$CORR_DIR"

# --- ÉTAPE 8 : Copie du PDF final ---
cp "$FINAL_PDF" "$ROOT_DIR/traitement_lot/output/${FILENAME}_final_corrige.pdf"
echo "✅ PDF copié dans /app/pipeline_OCR/traitement_lot/output/"

# --- ÉTAPE 9 : Structuration sémantique (facultatif) ---
echo "🏷️ Étape 9 : Structuration juridique"
python3 "$SCRIPT_DIR/structure_juridique.py" \
   "$CORR_DIR/${FILENAME}.txt" \
   "$ROOT_DIR/traitement_lot/output/${FILENAME}.json"

# --- ÉTAPE 10 : Extraction lexique métier ---
DICT_FILE="/app/dico_juridique.txt"
# On prépare le fichier
echo "🏷️ Étape 10 : Extraction des candidats lexique et mise à jour du dictionnaire → $DICT_FILE"
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

# --- ÉTAPE 11 : Copie du texte corrigé ---
echo "📋 Étape 11 : Copie du texte corrigé dans output/"
cp "$CORR_DIR/${FILENAME}.txt" \
   "$ROOT_DIR/traitement_lot/output/${FILENAME}.txt"

