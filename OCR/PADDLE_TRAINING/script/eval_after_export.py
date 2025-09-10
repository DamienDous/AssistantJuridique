from paddleocr import PaddleOCR
import os, csv, hashlib, pytesseract, Levenshtein

# --- Paths
model_dir = os.environ["EXPORT_DIR"]
data_dir = os.environ.get("BASE_DIR", "/workspace/data")
anno_path = os.path.join(data_dir, "val.txt")
csv_path = "./evaluation_results.csv"
config_path = "/workspace/config/latin_PP-OCRv3_rec.yml"

# --- Load GT
def load_gt_from_txt(path):
    gt = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "\t" not in line:
                continue
            img, label = line.strip().split("\t", 1)
            stem = os.path.splitext(os.path.basename(img))[0]
            gt[stem] = label
    return gt

gt = load_gt_from_txt(anno_path)

# --- Path resolver (avec fallback crops/)
def find_image_path(img_rel, data_dir):
    # chemin direct (cas train/val.txt)
    p = os.path.join(data_dir, img_rel)
    if os.path.exists(p):
        return p
    # fallback dans crops/
    p2 = os.path.join(data_dir, "crops", img_rel)
    if os.path.exists(p2):
        return p2
    # fallback sans extension
    base = os.path.splitext(img_rel)[0]
    for ext in [".jpg", ".png", ".jpeg"]:
        candidate = os.path.join(data_dir, "crops", base + ext)
        if os.path.exists(candidate):
            return candidate
    return None

# --- Metrics
def cer(ref, hyp):
    return Levenshtein.distance(ref, hyp) / max(1, len(ref))

def wer(ref, hyp):
    return Levenshtein.distance(" ".join(ref.split()), " ".join(hyp.split())) / max(1, len(ref.split()))

def evaluate(ocr_func, gt):
    scores = {"cer": [], "wer": []}
    for img_rel, ref in gt.items():
        img_path = find_image_path(img_rel, data_dir)
        if not img_path:
            print(f"[MISS] {img_rel}")
            continue
        hyp = ocr_func(img_path)
        scores["cer"].append(cer(ref, hyp))
        scores["wer"].append(wer(ref, hyp))
    return {k: sum(v)/len(v) if v else 1.0 for k,v in scores.items()}

# --- PaddleOCR custom (ton export uniquement reco)
paddle_custom = PaddleOCR(
    det_model_dir=None,                         # désactive la détection
    cls_model_dir=None,                         # désactive angle classifier
    lang="latin",                               # important pour éviter l'assert
    text_recognition_model_dir=model_dir,       # ton modèle entraîné
    use_textline_orientation=False
)
run_paddle_custom = lambda img: " ".join(
    [l[1][0] for l in paddle_custom.ocr(img, cls=False)[0]]
)

# --- Baseline Paddle intégré
paddle_base = PaddleOCR(
    det_model_dir=None,
    cls_model_dir=None,
    lang="latin",
    use_textline_orientation=False
)
run_paddle_base = lambda img: " ".join(
    [l[1][0] for l in paddle_base.ocr(img, cls=False)[0]]
)

# --- Tesseract
run_tess = lambda img: pytesseract.image_to_string(img, lang="eng").strip()

# --- Scores
res_custom = evaluate(run_paddle_custom, gt)
res_base   = evaluate(run_paddle_base, gt)
res_tess   = evaluate(run_tess, gt)

print("Custom:", res_custom)
print("Base:", res_base)
print("Tesseract:", res_tess)

# --- CSV log
yml_hash = hashlib.md5(open(config_path,"r",encoding="utf-8").read().encode()).hexdigest()
header = ["yaml_hash","ocr","cer","wer","export_dir"]
rows = [
    [yml_hash, "paddle_custom", res_custom["cer"], res_custom["wer"], model_dir],
    [yml_hash, "paddle_base",   res_base["cer"],   res_base["wer"],   "builtin"],
    [yml_hash, "tesseract",     res_tess["cer"],   res_tess["wer"],   "builtin"]
]
write_header = not os.path.exists(csv_path)
with open(csv_path,"a",newline="",encoding="utf-8") as f:
    w = csv.writer(f)
    if write_header: w.writerow(header)
    w.writerows(rows)
print(f"[OK] Résultats ajoutés à {csv_path}")
