#!/usr/bin/env python3
import numpy as np
from paddleocr import PaddleOCR
import os, csv, hashlib, pytesseract, Levenshtein, cv2, json, time, warnings, yaml
from pathlib import Path
warnings.filterwarnings("ignore", category=UserWarning)
import logging
logging.getLogger("ppocr").setLevel(logging.WARNING)
logging.getLogger("paddleocr").setLevel(logging.WARNING)
logging.getLogger("ppocr_debug").setLevel(logging.ERROR)

# --- Chemins
EXPORT_DIR = os.environ.get("EXPORT_DIR", "./output/inference/rec_ppocr_v3_latin_test")
BASE_DIR   = os.environ.get("BASE_DIR", "/workspace")
config_path = "/workspace/config/latin_PP-OCRv3_rec.yml"
anno_path   = os.path.join("/workspace/output/", "test.txt")
csv_path    = "/workspace/eval/evaluation_results.csv"
checkpoints_root = "./train_long/checkpoints"

model_dir = str(Path(EXPORT_DIR))

# --- Load GT
def load_gt_from_txt(path):
    gt = {}
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or "\t" not in line:
                print(f"[WARN] Ligne {lineno} mal formée dans {path}: {repr(line)} → ignorée")
                continue
            img, label = line.split("\t", 1)
            stem = os.path.splitext(os.path.basename(img))[0]
            gt[stem] = label
    return gt

gt = load_gt_from_txt(anno_path)
nb_val = len(gt)

# --- Compter train.txt
nb_train = 0
train_txt = os.path.join(BASE_DIR, "train.txt")
if os.path.exists(train_txt):
    nb_train = sum(1 for _ in open(train_txt, encoding="utf-8"))

# --- Path resolver (fallback crops/)
def find_image_path(img_rel, data_dir):
    p = os.path.join(data_dir, img_rel)
    if os.path.exists(p):
        return p
    p2 = os.path.join(data_dir, "crops", img_rel)
    if os.path.exists(p2):
        return p2
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
        img_path = find_image_path(img_rel, BASE_DIR)
        if not img_path:
            continue
        hyp = ocr_func(img_path)
        scores["cer"].append(cer(ref, hyp))
        scores["wer"].append(wer(ref, hyp))
    return {k: sum(v)/len(v) if v else 1.0 for k,v in scores.items()}

# --- Charger OCR
ocr_det = PaddleOCR(det=True, rec=False, cls=False, use_gpu=False, lang="latin")
rec_model = str(Path(EXPORT_DIR) / "inference")

ocr_rec = PaddleOCR(
    use_angle_cls=False,
    lang='latin',
    rec=True,
    det=False,
    cls=False,
    rec_algorithm='SVTR_LCNet',
    rec_model_dir=rec_model,
    rec_image_shape="3,48,320",
    rec_char_dict_path="/workspace/dict/latin_dict.txt",
    use_space_char=True
)
print(f"[INFO] OCR chargé depuis : {rec_model}")

# --- OCR step-by-step
def run_paddle_step(img_path):
    img = cv2.imread(img_path)
    if img is None:
        return ""
    det_results = ocr_det.ocr(img_path, cls=False)
    if not det_results or not det_results[0]:
        return ""
    preds = []
    for box in det_results[0]:
        import numpy as np
        points = np.array(box[0], dtype="int")
        x, y, w, h = cv2.boundingRect(points)
        crop = img[y:y+h, x:x+w]
        rec_res = ocr_rec.ocr(crop, cls=False)
        if rec_res and rec_res[0]:
            raw = rec_res[0][0]
            text = str(raw[0]) if isinstance(raw, (list, tuple)) else str(raw)
            preds.append(text)
    return " ".join(preds)

# --- Tesseract baseline
run_tess = lambda img: pytesseract.image_to_string(img, lang="eng").strip()

# --- Scores
res_custom = evaluate(run_paddle_step, gt)
res_tess   = evaluate(run_tess, gt)

print("Custom (step-by-step):", res_custom)
print("Tesseract:", res_tess)

# --- Hash et config
yml_hash = hashlib.md5(open(config_path,"r",encoding="utf-8").read().encode()).hexdigest()
with open(config_path, "r", encoding="utf-8") as f:
    yml_content = yaml.safe_load(f)

cfg_selected = {
    "Global": yml_content.get("Global", {}),
    "Train": yml_content.get("Train", {}),
    "Eval": yml_content.get("Eval", {}),
    "Optimizer": yml_content.get("Optimizer", {}),
    "Architecture": yml_content.get("Architecture", {})
}
config_str = json.dumps(cfg_selected, ensure_ascii=False)

# --- Identifier le dernier dossier checkpoint
best_model_id, best_model_size = None, None
if os.path.exists(checkpoints_root):
    subdirs = [d for d in os.listdir(checkpoints_root) if os.path.isdir(os.path.join(checkpoints_root, d))]
    subdirs = sorted(subdirs, reverse=True)  # dernier entraînement d'abord
    if subdirs:
        best_model_id = subdirs[0]
        best_dir = os.path.join(checkpoints_root, best_model_id)
        size_bytes = sum(os.path.getsize(os.path.join(r, f)) for r,_,fs in os.walk(best_dir) for f in fs)
        best_model_size = round(size_bytes / (1024*1024), 2)

# --- Taille du modèle exporté
export_model_size = None
if os.path.exists(EXPORT_DIR):
    size_bytes = sum(os.path.getsize(os.path.join(r, f)) for r,_,fs in os.walk(EXPORT_DIR) for f in fs)
    export_model_size = round(size_bytes / (1024*1024), 2)

# --- CSV log
header = ["date","yaml_hash","ocr","cer","wer","nb_train","nb_val",
          "export_dir","export_model_size_MB","best_model_id","best_model_size_MB","config"]

rows = [
    [time.strftime("%Y-%m-%d %H:%M:%S"), yml_hash, "paddle_custom_step",
     res_custom["cer"], res_custom["wer"],
     nb_train, nb_val, model_dir, export_model_size, best_model_id, best_model_size, config_str],
    [time.strftime("%Y-%m-%d %H:%M:%S"), yml_hash, "tesseract",
     res_tess["cer"], res_tess["wer"],
     nb_train, nb_val, "builtin", "", "", "", ""]
]

write_header = not os.path.exists(csv_path)
os.makedirs(os.path.dirname(csv_path), exist_ok=True)
with open(csv_path,"a",newline="",encoding="utf-8") as f:
    w = csv.writer(f)
    if write_header:
        w.writerow(header)
    w.writerows(rows)

print(f"[OK] Résultats ajoutés à {csv_path}")
