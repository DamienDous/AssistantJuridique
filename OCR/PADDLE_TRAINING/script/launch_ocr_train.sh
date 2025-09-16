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
echo "[INFO] Génération train/val.txt (dataset manquant ou vide)..."
# rm -f "$BASE_DIR/train.txt" "$BASE_DIR/val.txt"
python3 script/json2crops.py \
  --json_dir "$ANNO_DIR" \
  --img_dir "$IMG_DIR" \
  --glob_dir "$BASE_DIR" \
  --val_split 0.1 \
  --incremental \
  --workers 0 \
  --save_format jpg --jpg_quality 95 \
  --png_compress 1

if [ ! -s "$OUT_DIR/train.txt" ] || [ ! -s "$OUT_DIR/val.txt" ]; then
  echo "❌ train.txt ou val.txt introuvable ou vide → arrêt"
  exit 1
fi

# 2) Normalisation
python3 script/normalize_and_validate_dataset.py \
  --base "$BASE_DIR" \
  --out_base "$OUT_DIR" \
  --config "$CONFIG_MULTI" \
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
  -o Global.save_model_dir="./output/rec_ppocr_v3_latin"
cd -

# 4) Export modèles
export_ctc=""
if [ -f "/opt/PaddleOCR/output/rec_ppocr_v3_latin/latest.pdparams" ]; then
  ts=$(date +%Y%m%d_%H%M%S)
  export_ctc="/workspace/output/inference/rec_ppocr_v3_latin_ctc_$ts"
  python3 /opt/PaddleOCR/tools/export_model.py \
    -c "$CONFIG" \
    -o Global.pretrained_model=/opt/PaddleOCR/output/rec_ppocr_v3_latin/latest \
      Global.save_inference_dir="$export_ctc"
else
  echo "⚠️ Aucun checkpoint trouvé, export ignoré"
fi

# 5) Évaluation automatique (CTC-only)
VAL_FILE="$OUT_DIR/val.txt"
TRAIN_FILE="$OUT_DIR/train.txt"

if [ ! -f "$VAL_FILE" ]; then
  if [ -f "$TRAIN_FILE" ]; then
    echo "⚠️ $VAL_FILE manquant → duplication de $TRAIN_FILE pour éviter plantage"
    cp "$TRAIN_FILE" "$VAL_FILE"
  else
    echo "⚠️ Aucun train/val.txt trouvé → évaluation ignorée"
    exit 0
  fi
fi

if [ -d "$export_ctc" ]; then
  echo "▶ Évaluation automatique sur le set test (CTC-only)..."
  EXPORT_DIR="$export_ctc" BASE_DIR="$BASE_DIR" python3 /workspace/script/eval_after_export.py
else
  echo "⚠️ Évaluation ignorée (pas de modèle exporté CTC-only)."
fi
