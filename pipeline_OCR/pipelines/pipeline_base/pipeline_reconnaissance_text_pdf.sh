#!/bin/bash
set -e
set -u  # Erreur si variable non définie
export TESSDATA_PREFIX=/usr/local/share/tessdata

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

PNG_DIR="$1"
if [ ! -d "$PNG_DIR" ]; then
  echo "❌ Le dossier d’images PNG n’existe pas : $PNG_DIR"
  exit 1
fi

# Chemins de travail
FILENAME=$(basename "$PNG_DIR")
BASE_OUT="$WORKDIR/${FILENAME}_traitement"
IMAGES_DIR="${BASE_OUT}/${FILENAME}_images"
CLEANED_DIR="${BASE_OUT}/${FILENAME}_cleaned"
SLICES_DIR="${BASE_OUT}/${FILENAME}_slices"
TXT_DIR="${BASE_OUT}/${FILENAME}_txt"
CORR_DIR="${BASE_OUT}/${FILENAME}_txt_corrige"
FINAL_PDF="${BASE_OUT}/${FILENAME}_final_corrige.pdf"

mkdir -p "$IMAGES_DIR" "$CLEANED_DIR" "$SLICES_DIR" "$TXT_DIR" "$CORR_DIR"

echo "📥 Étape 1 : Copie des PNG vers le dossier de travail"
cp "$PNG_DIR"/*.png "$IMAGES_DIR/"

echo "🧼 Étape 2 : Nettoyage avec unpaper"
mkdir -p "$CLEANED_DIR"
for img in "$IMAGES_DIR"/*.png; do
  BASENAME=$(basename "$img")
  unpaper --overwrite "$img" "$CLEANED_DIR/$BASENAME"
done
INPUT_IMG_DIR="$CLEANED_DIR"
IMG=$(ls "$CLEANED_DIR"/*.png | head -n 1)

echo "✂️ Étape 2 bis : Découpage vertical des grandes images"
SLICE_HEIGHT=1730
HEIGHT=$(vipsheader -f height "$img")
WIDTH=$(vipsheader -f width "$img")
IMG_BASENAME=$(basename "$img" .png)

NUM_SLICES=$(( (HEIGHT + SLICE_HEIGHT - 1) / SLICE_HEIGHT ))
echo "Découpage de $img (${WIDTH} x ${HEIGHT} px) en $NUM_SLICES tranches..."

for ((i=0; i<NUM_SLICES; i++)); do
  OFFSET=$((i * SLICE_HEIGHT))
  HEIGHT_SLICE=$SLICE_HEIGHT

  # Ajuster la hauteur si on dépasse à la dernière tranche
  if (( OFFSET + SLICE_HEIGHT > HEIGHT )); then
    HEIGHT_SLICE=$(( HEIGHT - OFFSET ))
  fi

  OUTFILE="$SLICES_DIR/${IMG_BASENAME}_slice_$((i+1)).png"
  vips crop "$img" "$OUTFILE" 0 "$OFFSET" "$WIDTH" "$HEIGHT_SLICE"
done


INPUT_IMG_DIR="$SLICES_DIR"

# --- Étape 3 : Génération PDF avec img2pdf sans option -S ---
echo "🔠 Étape 3 : OCR et génération PDF searchable avec ocrmypdf"
CLEANPDF="$BASE_OUT/${FILENAME}_cleaned.pdf"
images=( "$INPUT_IMG_DIR"/*.png )
python3 -m img2pdf "${images[@]}" -o "$CLEANPDF"
ocrmypdf \
  --force-ocr \
  --oversample 300 \
  --language fra \
  --tesseract-pagesegmode 3 \
  "$CLEANPDF" \
  "$FINAL_PDF"

echo "📄 Résolution du PDF final (info Ghostscript) :"
pdfinfo "$FINAL_PDF" | grep -i 'Page size\|File size'

# --- ÉTAPE 4 : Extraction du texte global pour correction ---
echo "📂 Étape 4 : Extraction du texte pour LanguageTool"
pdftotext -layout "$FINAL_PDF" "$TXT_DIR/${FILENAME}.txt"

# --- ÉTAPE 5 : Extraction du texte brut par page (optionnel, NLP) ---
echo "📂 Étape 5 : Extraction du texte brut par page avec tesseract"
for img in "$INPUT_IMG_DIR"/*.png; do
  OUTFILE="$TXT_DIR/$(basename "${img%.png}").txt"
  tesseract "$img" "${OUTFILE%.txt}" -l fra+eng
done

# --- ÉTAPE 6 : Nettoyage post-OCR ---
echo "🧹 Étape 6 : Nettoyage post-OCR"
"$SCRIPT_DIR/clean_text.sh" \
  "$TXT_DIR/${FILENAME}.txt" \
  "$CORR_DIR/${FILENAME}.txt"

# --- ÉTAPE 7 : Correction avec LanguageTool ---
echo "🧠 Étape 7 : Correction avec LanguageTool"
python3 "$SCRIPT_DIR/04_correction.py" \
  "$CORR_DIR/${FILENAME}.txt" \
  "$CORR_DIR"

# --- ÉTAPE 8 : Copie du PDF final ---
echo "✅ Étape 8 : Copie du PDF final dans output/"
cp "$FINAL_PDF" "$ROOT_DIR/traitement_lot/output/${FILENAME}_final_corrige.pdf"

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
cp "$FINAL_PDF" "$ROOT_DIR/traitement_lot/output/${FILENAME}_final_corrige.pdf"
cp "$CORR_DIR/${FILENAME}.txt" "$ROOT_DIR/traitement_lot/output/${FILENAME}.txt"
