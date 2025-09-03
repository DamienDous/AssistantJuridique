#!/usr/bin/env bash
set -Eeuo pipefail
: "${DEBUG:=0}"; [[ "$DEBUG" == "1" ]] && set -x
trap 'echo "[ERROR] ${BASH_SOURCE[0]}:${LINENO} -> ${BASH_COMMAND}" >&2' ERR

# --- Chemins stables ---
: "${FORCE_DATA:=0}"

# --- Entrée (BASE_DIR passé en arg 1) ---
BASE_DIR="${1:-/workspace/data}"
IMG_DIR="$BASE_DIR/img"
ANNO_DIR="$BASE_DIR/anno"

# Pré-entraîné par défaut = LATIN PP-OCRv3
: "${PRETRAIN_REC_PATH:=/models/ppocrv3/latin/train/latest.pdparams}"
# : "${DICT_LATIN:=dict/latin_dict.txt}"
# : "${CONFIG:=config/latin_PP-OCRv3_rec.yml}"
# Choix du config multihead (PP-OCRv3)
CONFIG="config/en_PP-OCRv3_rec.multihead.yml"  # tu as déjà ce fichier
PRETRAIN="/models/ppocrv3/latin/train/latest"  # prefix (pas d’extension)
DICT="/workspace/dict/latin_dict.txt"
CFG_PATH="$CONFIG"

is_multihead="$(python3 - "$CFG_PATH" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
arch = (cfg or {}).get("Architecture", {})
head = arch.get("Head", {})
is_mh = (isinstance(head, dict) and head.get("name") == "MultiHead") \
        or (isinstance(head, dict) and head.get("head_list"))
print("yes" if is_mh else "no")
PY
)"

if [ "$is_multihead" != "yes" ] && [ "${ALLOW_NON_MULTIHEAD:-0}" != "1" ]; then
  echo "CONFIG ($CONFIG) n'est pas MultiHead; utilise un checkpoint CTC-only ou change de config."
  exit 2
fi

# abort si arch MultiHead absente du config choisi
grep -q "Head *: *MultiHead" "$CONFIG" || {
  echo "CONFIG ($CONFIG) n'est pas MultiHead; utilise un checkpoint CTC-only ou change de config."; exit 2;
}

# abort si le préfixe ne pointe pas sur des fichiers attendus
for s in pdparams; do
  test -f "${PRETRAIN}.${s}" || { echo "Manque ${PRETRAIN}.${s}"; exit 2; }
done

echo "=== launch_ocr_train.sh (latin, config-only) ==="
echo "BASE_DIR    : $BASE_DIR"
echo "CONFIG      : $CONFIG"
echo "FORCE_DATA  : $FORCE_DATA"

start_time=$(date +%s)

# Préparer l’arborescence
mkdir -p "$IMG_DIR" "$ANNO_DIR"

# Purge du staging si demandé
if [ "$FORCE_DATA" = "1" ]; then
  rm -rf "$BASE_DIR/crops" "$BASE_DIR/.cache" \
         "$BASE_DIR/train.txt" "$BASE_DIR/val.txt"
fi

# 1) Crops & labels
echo "▶ Extraction crops depuis JSON → $IMG_DIR"
python3 script/json2crops.py \
  --json_dir "$ANNO_DIR" \
  --img_dir "$IMG_DIR" \
  --out_dir "$BASE_DIR" \
  --val_split 0.1 \
  --incremental \
  --workers 0 \
  --save_format jpg --jpg_quality 95 \
  --png_compress 1

# 2) Normalisation & validation (avec cache)
echo "▶ Normalisation & validation dataset (rebuild)"
python3 script/normalize_and_validate_dataset.py --base "$BASE_DIR" --config "$CONFIG" \
  --char "$DICT" --max_len 256 --expect_width 320 --hstride 4 --drop_too_long

pre_end=$(date +%s)
pre_elapsed=$(( pre_end - start_time ))
printf "\n⏱️ Temps de pré traitement : %02d:%02d:%02d\n" \
  $((pre_elapsed/3600)) $((pre_elapsed%3600/60)) $((pre_elapsed%60))

# 3) Entraînement (AUCUN override)
export PYTHONFAULTHANDLER=1
echo "▶ Lancement training (config-only)"
# python3 /opt/PaddleOCR/tools/train.py -c "$CONFIG"


python3 tools/train.py -c "$CONFIG" \
  -o Global.pretrained_model="$PRETRAIN" \
     Global.character_dict_path="$DICT" \
     Global.use_space_char=True
     
train_end=$(date +%s)
train_elapsed=$(( train_end - start_time ))

printf "\n⏱️ Temps d'exécution : %02d:%02d:%02d\n" \
  $((train_elapsed/3600)) $((train_elapsed%3600/60)) $((train_elapsed%60))