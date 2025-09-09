#!/usr/bin/env bash
set -Eeuo pipefail
: "${DEBUG:=0}"; [[ "$DEBUG" == "1" ]] && set -x
trap 'echo "[ERROR] ${BASH_SOURCE[0]}:${LINENO} -> ${BASH_COMMAND}" >&2' ERR

# --- Entrée ---
BASE_DIR="${1:-/workspace/data}"
IMG_DIR="$BASE_DIR/img"
ANNO_DIR="$BASE_DIR/anno"

# --- Config ---
CONFIG="/workspace/config/latin_PP-OCRv3_rec.yml"
CONFIG_MULTI="/workspace/config/latin_PP-OCRv3_rec.multihead.yml"
DICT="/workspace/dict/latin_dict.txt"

RESUME="${RESUME:-0}"
CHECKPOINTS="./output/latin_ppocrv3/latest"

echo "=== launch_ocr_train.sh ==="
echo "BASE_DIR    : $BASE_DIR"
echo "CONFIG      : $CONFIG"
echo "CONFIG_MULTI      : $CONFIG_MULTI"
echo "DICT        : $DICT"
echo "RESUME      : $RESUME"

# Sanity checks
[[ -f "$CONFIG" ]] || { echo "Config introuvable: $CONFIG"; exit 2; }
[[ -f "$CONFIG_MULTI" ]] || { echo "Config introuvable: $CONFIG_MULTI"; exit 2; }
[[ -f "$DICT"   ]] || { echo "Dict introuvable  : $DICT";   exit 2; }

mkdir -p "$IMG_DIR" "$ANNO_DIR"

# 1) Crops & labels
python3 script/json2crops.py \
  --json_dir "$ANNO_DIR" \
  --img_dir "$IMG_DIR" \
  --out_dir "$BASE_DIR" \
  --val_split 0.1 \
  --incremental \
  --workers 0 \
  --save_format jpg --jpg_quality 95 \
  --png_compress 1

# 2) Normalisation & validation
python3 script/normalize_and_validate_dataset.py \
  --base "$BASE_DIR" \
  --config "$CONFIG_MULTI" \
  --char "$DICT" \
  --max_len 256 --expect_width 320 --hstride 4 --drop_too_long

# 3) Entraînement OCR
cd /opt/PaddleOCR

echo "▶ Train OCR..."
python3 tools/train.py -c "$CONFIG_MULTI" \
  -o Train.dataset.label_file_list="[\"/workspace/data/train.txt\"]" \
  -o Eval.dataset.label_file_list="[\"/workspace/data/val.txt\"]" \
  -o Global.character_dict_path="$DICT" \
  -o Global.use_space_char=True

# 4) Export du modèle (avec timestamp unique)
ts=$(date +%Y%m%d_%H%M%S)
export_dir="./inference/rec_ppocr_v3_latin_$ts"

echo "▶ Export du modèle vers $export_dir ..."
python3 tools/export_model.py \
  -c "$CONFIG" \
  -o Global.pretrained_model=./output/rec_ppocr_v3_latin/latest \
     Global.save_inference_dir="$export_dir"

# Vérification succès export
if [ -d "$export_dir" ]; then
    echo "[OK] Modèle exporté dans $export_dir"
else
    echo "[ERREUR] L'export a échoué."
    exit 1
fi

# --- Copie du modèle exporté dans /workspace/output_models ---
mkdir -p /workspace/output_models/$(basename "$export_dir")
cp -r "$export_dir"/* /workspace/output_models/$(basename "$export_dir")/
echo "[OK] Modèle copié dans /workspace/output_models/$(basename "$export_dir")"

# 5) Évaluation automatique
echo "▶ Évaluation automatique sur le set test..."
EXPORT_DIR="$export_dir" python3 script/eval_after_export.py