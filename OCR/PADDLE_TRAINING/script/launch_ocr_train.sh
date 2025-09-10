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

echo "▶ Vérification cache d'entraînement..."
set +e
python3 - <<'PY'
import os, hashlib

def make_fingerprint():
    base = os.environ.get("BASE_DIR", "/workspace/data")
    cfg  = "/workspace/config/latin_PP-OCRv3_rec.multihead.yml"
    h = hashlib.sha256()
    anno = os.path.join(base, "anno")
    if os.path.isdir(anno):
        for root,_,fs in os.walk(anno):
            for fn in sorted(fs):
                if fn.lower().endswith(".json"):
                    with open(os.path.join(root,fn),"rb") as f:
                        h.update(f.read())
    if os.path.isfile(cfg):
        with open(cfg,"rb") as f:
            h.update(f.read())
    return h.hexdigest()

outdir="/opt/PaddleOCR/output/rec_ppocr_v3_latin"
os.makedirs(outdir, exist_ok=True)
hashfile = os.path.join(outdir,".train.sha256")

new = make_fingerprint()
old = open(hashfile).read().strip() if os.path.isfile(hashfile) else None

if old == new:
    print("[CACHE] Entraînement inchangé, on skippe.")
    raise SystemExit(100)   # code spécial pour Bash
else:
    with open(hashfile,"w") as f: f.write(new+"\n")
    print("[CACHE] Changements détectés → nouvel entraînement requis.")
PY

ret=$?   # capture le code de sortie Python
set -e
if [ $ret -eq 100 ]; then
    echo "=== Skip entraînement (pas de changement détecté) ==="
    SKIP=1
else
    echo "=== Lancement de l’entraînement ==="
    SKIP=0
    cd /opt/PaddleOCR
    python3 tools/train.py -c "$CONFIG_MULTI" \
      -o Train.dataset.label_file_list="[\"$BASE_DIR/train.txt\"]" \
      -o Eval.dataset.label_file_list="[\"$BASE_DIR/val.txt\"]" \
      -o Global.character_dict_path="$DICT" \
      -o Global.use_space_char=True \
      -o Global.save_model_dir="./output/rec_ppocr_v3_latin"
    cd -
fi


# 4) Export du modèle (avec timestamp unique)
ts=$(date +%Y%m%d_%H%M%S)
export_dir="/workspace/output/inference/rec_ppocr_v3_latin_$ts"

# Vérifie que le dossier des checkpoints existe
if [ -d "./output/rec_ppocr_v3_latin" ]; then
    latest_ckpt=$(find ./output/rec_ppocr_v3_latin -type f -name "*.pdparams" 2>/dev/null | sort -r | head -n1)
    # fallback
    if [ -z "$latest_ckpt" ] && [ -f "./output/rec_ppocr_v3_latin/latest.pdparams" ]; then
        latest_ckpt="./output/rec_ppocr_v3_latin/latest.pdparams"
    fi
else
    latest_ckpt=""
fi

if [ "$SKIP" -eq 1 ]; then
    # Rien de nouveau, on exporte sans recharger latest
    python3 tools/export_model.py \
      -c "$CONFIG" \
      -o Global.save_inference_dir="$export_dir"
else
    # Nouvel entraînement → export avec le dernier checkpoint
    python3 tools/export_model.py \
      -c "$CONFIG" \
      -o Global.pretrained_model="$latest_ckpt" \
         Global.save_inference_dir="$export_dir"
fi


# 5) Évaluation automatique
if [ -n "$export_dir" ] && [ -d "$export_dir" ]; then
    echo "▶ Évaluation automatique sur le set test..."
    EXPORT_DIR="$export_dir" python3 /workspace/script/eval_after_export.py
else
    echo "⚠️ Évaluation ignorée (pas de modèle exporté)."
fi