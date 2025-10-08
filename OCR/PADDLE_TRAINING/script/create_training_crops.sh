#!/usr/bin/env bash
set -euo pipefail

# =======================
#  CONFIG & VARIABLES
# =======================
BASE_DIR="${1:-/workspace}"
IMG_DIR="$BASE_DIR/img"
JSON_DIR="$BASE_DIR/anno"
REND_DIR="$BASE_DIR/text_renderer"
DICT_PATH="$BASE_DIR/dict"
PY=python3

mkdir -p "$BASE_DIR" "$BASE_DIR/output" "$BASE_DIR/crops"

# Vérif outils
command -v "$PY" >/dev/null || { echo "❌ Python introuvable."; exit 1; }
command -v nproc >/dev/null || { echo "⚠️  nproc absent, on utilisera 4 threads"; NPROC=4; } || NPROC=$(nproc)

# =======================
#  ÉTAPE 1 – Extraction crops DocLayNet
# =======================
echo "==[1/7]== DocLayNet → crops"
$PY script/json2crops.py \
  --json_dir "$JSON_DIR" \
  --img_dir  "$IMG_DIR" \
  --glob_dir "$BASE_DIR" \
  --val_split 0.05 --test_split 0.05 \
  --target_h 48 --target_w 320 --hstride 4 \
  --workers "${NPROC:-4}" \
  --save_format png --png_compress 1

echo "✅ Crops générés dans $BASE_DIR/output et $BASE_DIR/crops"

# =======================
#  ÉTAPE 2 – Corpus FR + fonds synthétiques
# =======================
echo "==[2/7]== Génération corpus FR + fonds synthétiques"
$PY script/extract_cold_french_law.py
$PY script/generate_backgrounds.py

echo "== Synthèse 100k lignes artificielles"
$PY "$REND_DIR/main.py" \
  --corpus_file ./corpus_juridique_600k.txt \
  --font_dir "$REND_DIR/fonts" \
  --bg_dir "$REND_DIR/backgrounds" \
  --num_img 100000 \
  --save_dir "$REND_DIR/paddleocr_synth" \
  --img_height 48 --img_width 320 \
  --chars_file "$DICT_PATH"

find "$REND_DIR/paddleocr_synth" -type f -name "*.png" > "$BASE_DIR/output/synth_paths.txt"
if [[ -f "$REND_DIR/paddleocr_synth/labels.txt" ]]; then
  paste <(cat "$BASE_DIR/output/synth_paths.txt") <(cut -f2- "$REND_DIR/paddleocr_synth/labels.txt") > "$GLOB_DIR/output/train_synth.txt"
fi

# =======================
#  ÉTAPE 3 – Merge & super-crops
# =======================
echo "==[3/7]== Merge & super-crops"
cp "$BASE_DIR/output/train.txt" train_list.txt
$PY script/generate_long_crops.py

mv train_list_long.txt   "$BASE_DIR/output/train_long.txt"
mv train_list_mixed.txt  "$BASE_DIR/output/train_mixed.txt"

cat "$BASE_DIR/output/train_mixed.txt" "$BASE_DIR/output/train.txt" \
    | shuf > "$BASE_DIR/output/train_merged.txt"

# =======================
#  ÉTAPE 4 – Normalisation + filtre OOV
# =======================
echo "==[4/7]== Normalisation + filtre OOV"
$PY script/normalize_and_validate_dataset.py \
  --base "$BASE_DIR" \
  --char "$DICT_PATH" \
  --max_len 256 \
  --expect_width 320 \
  --hstride 4 \
  --drop_too_long

# =======================
#  ÉTAPE 5 – Audit qualité
# =======================
echo "==[5/7]== Audit qualité des crops"
$PY script/crops_analyzer.py

# =======================
#  ÉTAPE 6 – Stratification A/B/C
# =======================
echo "==[6/7]== Stratification A/B/C"
$PY script/create_crops_groups.py
mv train_A.txt "$BASE_DIR/output/train_A.txt" 2>/dev/null || true
mv train_B.txt "$BASE_DIR/output/train_B.txt" 2>/dev/null || true
mv train_C.txt "$BASE_DIR/output/train_C.txt" 2>/dev/null || true

# =======================
#  ÉTAPE 7 – Proposition dictionnaire
# =======================
echo "==[7/7]== Proposition MAJ dictionnaire"
$PY - "$BASE_DIR" << 'PY'
import sys, collections
root = sys.argv[1]
chars = collections.Counter()
def iter_labels(tsv):
    with open(tsv, encoding='utf-8') as f:
        for line in f:
            if '\t' not in line: continue
            yield line.rstrip('\n').split('\t',1)[1]
for split in ('train.txt','val.txt'):
    try:
        for lab in iter_labels(f"{root}/output/{split}"):
            chars.update(lab)
    except FileNotFoundError:
        pass
good = [c for c,_ in chars.most_common() if not c.isspace()]
out = f"{root}/dict/latin_dict.candidate.txt"
with open(out,"w",encoding="utf-8") as f:
    f.writelines(c + "\n" for c in good)
print(f"✅ Dictionnaire candidat écrit → {out}")
PY

echo "🎉 Pipeline terminé avec succès !"