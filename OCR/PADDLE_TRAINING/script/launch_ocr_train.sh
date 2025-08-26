#!/usr/bin/env bash
set -Eeuo pipefail
: "${DEBUG:=0}"; [[ "$DEBUG" == "1" ]] && set -x
trap 'echo "[ERROR] ${BASH_SOURCE[0]}:${LINENO} -> ${BASH_COMMAND}" >&2' ERR

# --- Chemins stables ---
: "${FORCE_DATA:=0}"

# --- Entrée (BASE_DIR passé en arg 1) ---
BASE_DIR="${1:-${BASE_DIR:-/workspace/data}}"
IMG_DIR="$BASE_DIR/img"
ANNO_DIR="$BASE_DIR/anno"
DATA_DIR="$BASE_DIR/data"

# Pré-entraîné par défaut = LATIN PP-OCRv3
: "${PRETRAIN_REC_PATH:=/models/ppocrv3/latin/train/latest.pdparams}"
: "${DICT_LATIN:=dict/latin_dict.txt}"
: "${CONFIG:=config/latin_PP-OCRv3_rec.yml}"
[ -f "$CONFIG" ] || { echo "[FATAL] CONFIG n'est pas un fichier: $CONFIG"; exit 2; }

echo "=== launch_ocr_train.sh (latin, config-only) ==="
echo "BASE_DIR    : $BASE_DIR"
echo "CONFIG      : $CONFIG"
echo "FORCE_DATA  : $FORCE_DATA"

start_time=$(date +%s)

# Préparer l’arborescence
mkdir -p "$IMG_DIR" "$ANNO_DIR" "$DATA_DIR"

# Purge du staging si demandé
if [ "$FORCE_DATA" = "1" ]; then
  rm -rf "$DATA_DIR/crops" "$DATA_DIR/.cache" \
         "$DATA_DIR/train.txt" "$DATA_DIR/val.txt"
fi

# 1) Crops & labels
echo "▶ Extraction crops depuis JSON → $IMG_DIR"
python3 script/json2crops.py \
  --json_dir "$ANNO_DIR" \
  --img_dir  "$IMG_DIR" \
  --out_dir  "$DATA_DIR" \
  --incremental \
  --cache_file "$DATA_DIR/.cache/json2crops.manifest.json"

# 2) Normalisation & validation (avec cache)
echo "▶ Normalisation & validation dataset (rebuild)"
python3 /workspace/script/normalize_and_validate_dataset.py --base "$BASE_DIR" --config "$CONFIG" \
  --char "$DICT_LATIN" --max_len 256 --expect_width 320 --hstride 4 --drop_too_long

pre_end=$(date +%s)
pre_elapsed=$(( pre_end - start_time ))
printf "\n⏱️ Temps de pré traitement : %02d:%02d:%02d\n" \
  $((pre_elapsed/3600)) $((pre_elapsed%3600/60)) $((pre_elapsed%60))

# 3) Entraînement (AUCUN override)
export PYTHONFAULTHANDLER=1
cd /opt/PaddleOCR
echo "▶ Lancement training (config-only)"
python3 tools/train.py -c "$CONFIG"

train_end=$(date +%s)
train_elapsed=$(( train_end - start_time ))

printf "\n⏱️ Temps d'exécution : %02d:%02d:%02d\n" \
  $((train_elapsed/3600)) $((train_elapsed%3600/60)) $((train_elapsed%60))