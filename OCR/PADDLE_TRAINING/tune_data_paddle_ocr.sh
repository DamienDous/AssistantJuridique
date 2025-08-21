#!/usr/bin/env bash
set -Eeuo pipefail
: "${DEBUG:=0}"; [[ "$DEBUG" == "1" ]] && set -x
trap 'echo "[ERROR] ${BASH_SOURCE[0]}:${LINENO} → ${BASH_COMMAND}" >&2' ERR

IMG_DIR=${1:-/workspace/raw_img}
ANNO_DIR=${2:-/workspace/anno}   # non utilisé ici (json traités par json2crops.py)
OUT_DIR=${3:-/workspace/data}

mkdir -p "$OUT_DIR/images"

echo "▶ Préparation des images → $OUT_DIR/images"
shopt -s nullglob

# 1) PDFs -> PNG (300dpi, sRGB)
pdfs=("$IMG_DIR"/*.pdf)
if (( ${#pdfs[@]} > 0 )); then
  echo "  • Conversion PDF → PNG (300dpi, sRGB)"
  for f in "${pdfs[@]}"; do
    base="$(basename "$f" .pdf)"
    # une page -> base_0000.png, etc.
    magick -density 300 -colorspace sRGB -alpha off "$f" "$OUT_DIR/images/${base}_%04d.png"
  done
fi

# 2) Images déjà prêtes -> copie
echo "  • Copie des images existantes"
rsync -a --include='*/' \
  --include='*.png' --include='*.jpg' --include='*.jpeg' --include='*.tif' --include='*.tiff' \
  --exclude='*' "$IMG_DIR"/ "$OUT_DIR/images/" || true

# 3) Comptage
mapfile -t IMGS < <(find "$OUT_DIR/images" -type f \( -iname "*.png" -o -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.tif" -o -iname "*.tiff" \) | sort)
echo "  → Images prêtes : ${#IMGS[@]}"

# 4) NE PAS créer train/val ici (les JSON génèrent des crops via scripts/json2crops.py)
echo "✔ Images prêtes. Étape suivante : json2crops.py construira crops + train/val."
