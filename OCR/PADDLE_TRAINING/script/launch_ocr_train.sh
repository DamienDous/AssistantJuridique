#!/usr/bin/env bash
set -Eeuo pipefail
: "${DEBUG:=0}"; [[ "$DEBUG" == "1" ]] && set -x
trap 'echo "[ERROR] ${BASH_SOURCE[0]}:${LINENO} -> ${BASH_COMMAND}" >&2' ERR

BASE_DIR="${1:-/workspace}"
IMG_DIR="$BASE_DIR/img"
ANNO_DIR="$BASE_DIR/anno"
OUT_DIR="$BASE_DIR/output"

CONFIG="/workspace/config/latin_PP-OCRv3_rec.yml"                 # CTC-only (pour export/éval)
CONFIG_MULTI="/workspace/config/latin_PP-OCRv3_rec.multihead.yml" # MultiHead (pour entraînement)
DICT="/workspace/dict/latin_dict.txt"

echo "=== launch_ocr_train.sh ==="
echo "BASE_DIR    : $BASE_DIR"
echo "CONFIG      : $CONFIG"
echo "CONFIG_MULTI: $CONFIG_MULTI"
echo "DICT        : $DICT"

# 1) Crops & labels
echo "[INFO] Génération train/val.txt ..."
# rm -f "$BASE_DIR/train.txt" "$BASE_DIR/val.txt"
MAXLEN=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_MULTI'))['Global']['max_text_length'])")
python3 script/json2crops.py \
  --json_dir "$ANNO_DIR" \
  --img_dir "$IMG_DIR" \
  --glob_dir "$BASE_DIR" \
  --val_split 0.1 \
  --incremental \
  --workers 0 \
  --save_format jpg --jpg_quality 95 \
  --png_compress 1 \
  --maxlen $MAXLEN

if [ ! -s "$OUT_DIR/train.txt" ] || [ ! -s "$OUT_DIR/val.txt" ]; then
  echo "❌ train.txt ou val.txt introuvable ou vide → arrêt"
  exit 1
fi

# 2) Normalisation
python3 script/normalize_and_validate_dataset.py \
  --base "$BASE_DIR" \
  --out_base "$OUT_DIR" \
  --char "$DICT" \
  --max_len 256 --expect_width 640 --hstride 4 --drop_too_long

# 3) Entraînement OCR (toujours MultiHead)
cd /opt/PaddleOCR
echo "=== Lancement de l’entraînement (MultiHead) ==="
python3 tools/train.py -c "$CONFIG_MULTI" \
  -o Train.dataset.label_file_list="[\"$OUT_DIR/train.txt\"]" \
  -o Eval.dataset.label_file_list="[\"$OUT_DIR/val.txt\"]" \
  -o Global.character_dict_path="$DICT" \
  -o Global.use_space_char=True \
  -o Global.save_model_dir="/workspace/output/rec_ppocr_v3_latin"

# 4) Évaluation MultiHead + baseline Tesseract
echo "▶ Évaluation automatique MultiHead + Tesseract..."
python3 /workspace/script/eval_multihead.py \
  --config "$CONFIG_MULTI" \
  --checkpoint "./output/rec_ppocr_v3_latin/latest" \
  --dict "$DICT" \
  --val "$OUT_DIR/val.txt" \
  --base "$BASE_DIR"