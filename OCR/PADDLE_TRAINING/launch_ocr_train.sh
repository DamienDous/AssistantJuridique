#!/usr/bin/env bash
set -Eeuo pipefail
: "${DEBUG:=0}"; [[ "$DEBUG" == "1" ]] && set -x
trap 'echo "[ERROR] ${BASH_SOURCE[0]}:${LINENO} -> ${BASH_COMMAND}" >&2' ERR

# --- Chemins stables (le YAML doit pointer /workspace/data) ---
: "${PADDLE_OCR_DIR:=/opt/PaddleOCR}"
: "${CONFIG:=/workspace/latin_PP-OCRv3_rec.yml}"     # ← YAML latin
: "${USE_SHM:=1}"                                        # 1=travail en RAM puis sync vers DATA_DIR
: "${SHM_DIR:=/dev/shm/data}"                            # dossier RAM
: "${FORCE_DATA:=0}"

# Pré-entraîné par défaut = LATIN PP-OCRv3
: "${PRETRAIN_REC_PATH:=/models/ppocrv3/latin/train/latest.pdparams}"
: "${DICT_LATIN:=/workspace/dicts/latin_dict.txt}"

# --- Entrée (BASE_DIR passé en arg 1) ---
BASE_DIR="${1:-${BASE_DIR:-/workspace/project}}"
IMG_DIR="$BASE_DIR/img"
ANNO_DIR="$BASE_DIR/anno"
DATA_DIR="$BASE_DIR/data"

# (optionnel) export du dict latin pour construire manuellement charset.txt
: "${EXPORT_LATIN_DICT:=0}"   # 1 = copie le dict latin dans project/reference_dicts
: "${EXPORT_MODE:=stop}"      # stop|append

if [ "$EXPORT_LATIN_DICT" = "1" ]; then
  REFERENCE_DIR="$BASE_DIR/reference_dicts"
  mkdir -p "$REFERENCE_DIR"
  cp -f "$DICT_LATIN" "$REFERENCE_DIR/latin_dict.txt"
  echo "▶ latin_dict.txt exporté → $REFERENCE_DIR"
  [ "$EXPORT_MODE" = "stop" ] && exit 0
fi

[ -f "$CONFIG" ] || { echo "[FATAL] CONFIG n'est pas un fichier: $CONFIG"; exit 2; }

echo "=== launch_ocr_train.sh (latin, config-only) ==="
echo "BASE_DIR    : $BASE_DIR"
echo "IMG_DIR     : $IMG_DIR"
echo "ANNO_DIR    : $ANNO_DIR"
echo "DATA_DIR    : $DATA_DIR"
echo "CONFIG      : $CONFIG"
echo "USE_SHM     : $USE_SHM (SHM_DIR=$SHM_DIR)"
echo "FORCE_DATA  : $FORCE_DATA"

# Préparer l’arborescence
mkdir -p "$IMG_DIR" "$ANNO_DIR" "$DATA_DIR" "$(dirname "$SHM_DIR")"

# Lien symbolique pour que le YAML (qui pointe /workspace/data) utilise project/data
ln -sfn "$DATA_DIR" /workspace/data

# Purge du staging si demandé
if [ "$FORCE_DATA" = "1" ]; then
  rm -rf "$DATA_DIR/images" "$DATA_DIR/crops" "$DATA_DIR/.cache" \
         "$DATA_DIR/train.txt" "$DATA_DIR/val.txt"
  # NE PAS supprimer charset.txt si tu le maintiens à la main
fi

# Recrée et resynchronise les images (copie propre)
rm -rf "$DATA_DIR/images"
mkdir -p "$DATA_DIR/images"
cp -a "$IMG_DIR/." "$DATA_DIR/images/" || true

# 1) Prétraitement (PDF→PNG, index) si dispo
if [ -x /tools/tune_data_paddle_ocr.sh ]; then
  /tools/tune_data_paddle_ocr.sh "$IMG_DIR" "$ANNO_DIR" "$DATA_DIR"
fi

# 2) Crops & labels (on écrit d'abord dans DATA_DIR pour persistance)
echo "▶ Extraction crops depuis JSON → $IMG_DIR"
python3 scripts/json2crops.py \
  --json_dir "$ANNO_DIR" \
  --img_dir  "$IMG_DIR" \
  --out_dir  "$DATA_DIR" \
  --incremental \
  --cache_file "$DATA_DIR/.cache/json2crops.manifest.json"

# 3) Option RAM : copie vers /dev/shm/data pour la phase de contrôle
ACTIVE_DIR="$DATA_DIR"
if [ "$USE_SHM" = "1" ]; then
  echo "▶ Copie dataset → $SHM_DIR (RAM)"
  rm -rf "$SHM_DIR" && mkdir -p "$SHM_DIR"
  cp -a "$DATA_DIR/." "$SHM_DIR/"
  ACTIVE_DIR="$SHM_DIR"
fi

# --- 3bis) Vérif/auto-fix format des labels : "path<TAB>label" + LF ---
fix_labels() {
  local f="$1"
  [ -f "$f" ] || return 0
  # 1) retirer CRLF Windows
  sed -i 's/\r$//' "$f"
  # 2) si aucune tabulation détectée mais qu'on a au moins un espace, on met 1 seule TAB après le premier token
  if ! grep -qP '\t' "$f" && grep -q ' ' "$f"; then
    awk '{
      i = index($0, " ");
      if (i>0) print substr($0,1,i-1) "\t" substr($0,i+1);
      else print $0
    }' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  fi
}
echo "▶ Vérification format labels (TAB)…"
fix_labels "$ACTIVE_DIR/train.txt"
fix_labels "$ACTIVE_DIR/val.txt"
# recopie dans DATA_DIR si on travaille en RAM
if [ "$USE_SHM" = "1" ]; then
  cp -f "$ACTIVE_DIR/train.txt" "$DATA_DIR/train.txt"
  cp -f "$ACTIVE_DIR/val.txt"   "$DATA_DIR/val.txt"
fi

# 4) Normalisation & validation (avec cache)
CACHE_DIR="$DATA_DIR/.cache"
mkdir -p "$CACHE_DIR"
NORM_FINGERPRINT_SRC="/tmp/norm_fingerprint.txt"
{
  find "$DATA_DIR" -maxdepth 1 -type f \( -name 'train.txt' -o -name 'val.txt' -o -name 'charset.txt' \) -print0 \
    | sort -z | xargs -0 sha256sum 2>/dev/null
  find "$DATA_DIR/crops" -type f -name '*.png' -print0 2>/dev/null \
    | sort -z | xargs -0 sha256sum 2>/dev/null
  sha256sum "$CONFIG"
  echo "PIPELINE_NORMALIZE_VERSION=v1"
} > "$NORM_FINGERPRINT_SRC"

NORM_HASH_NEW="$(sha256sum "$NORM_FINGERPRINT_SRC" | awk '{print $1}')"
NORM_HASH_FILE="$CACHE_DIR/norm.sha256"

if [ -f "$NORM_HASH_FILE" ] && [ "$NORM_HASH_NEW" = "$(cat "$NORM_HASH_FILE")" ]; then
  echo "[CACHE] Normalisation inchangée, on skippe l'étape."
else
  echo "▶ Normalisation & validation dataset (rebuild)"
  python3 scripts/normalize_and_validate_dataset.py --base "$ACTIVE_DIR"
  echo "$NORM_HASH_NEW" > "$NORM_HASH_FILE"
fi

# 5) Charset = LATIN STRICT (écrasement systématique pour coller au pré-entraîné)
CHARSET_DEST="$DATA_DIR/charset.txt"
if [ ! -s "$DICT_LATIN" ]; then
  echo "[FATAL] DICT_LATIN introuvable: $DICT_LATIN"; exit 4;
fi
cp -f "$DICT_LATIN" "$CHARSET_DEST"

# 5bis) Filtrer les lignes OOV (= contenant des caractères hors charset) pour éviter pertes silencieuses
python3 - <<'PY'
import sys, pathlib
base = pathlib.Path("/workspace/data")
chars = set(base.joinpath("charset.txt").read_text(encoding="utf-8").splitlines())
def clean(split):
    p = base.joinpath(f"{split}.txt")
    if not p.exists(): return
    keep, drop = [], 0
    for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not ln.strip(): continue
        parts = ln.split("\t", 1)
        if len(parts) < 2: continue
        path, lab = parts[0], parts[1]
        if any((c not in chars) for c in lab):
            drop += 1
            continue
        keep.append(f"{path}\t{lab}")
    p.write_text("\n".join(keep)+"\n", encoding="utf-8")
    print(f"[OOV] {split}: dropped={drop}, kept={len(keep)}")
for s in ("train","val"): clean(s)
PY

# 6) Sync RAM → disque
if [ "$USE_SHM" = "1" ]; then
  echo "▶ Sync RAM → $DATA_DIR"
  rsync -a --delete "$SHM_DIR/." "$DATA_DIR/"
fi

# 7) Diagnostics utiles
CHARSET_LINES=$(wc -l < "$CHARSET_DEST" || echo "?")
echo "CHARSET     : $CHARSET_DEST (${CHARSET_LINES} lines)"
echo "======================"

# 7bis) Résolution du YAML : imposer prétrain LATIN + pas de reprise de checkpoint
if [ ! -f "$PRETRAIN_REC_PATH" ]; then
  PRETRAIN_REC_PATH="$(ls -1 /models/ppocrv3/latin/train/*.pdparams 2>/dev/null | head -n1 || true)"
fi
[ -f "$PRETRAIN_REC_PATH" ] || { echo "[FATAL] .pdparams LATIN introuvable sous /models/ppocrv3/latin/train"; exit 5; }

# 8) Entraînement (AUCUN override)
export PYTHONFAULTHANDLER=1
cd "$PADDLE_OCR_DIR"
echo "▶ Lancement training (config-only)"
python3 tools/train.py -c "$CONFIG"
