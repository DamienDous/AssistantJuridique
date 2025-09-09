import os, glob, csv, hashlib, yaml
import pytesseract
from paddleocr import PaddleOCR
import Levenshtein

# --- Paths
model_dir = os.environ["EXPORT_DIR"]
data_dir = "/workspace/data"
img_dir = os.path.join(data_dir, "crops")
anno_path = os.path.join(data_dir, "val.txt")
csv_path = "./evaluation_results.csv"
config_path = "/workspace/config/latin_PP-OCRv3_rec.yml"

# --- Ground truth depuis val.txt
def load_gt_from_txt(path):
    gt = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "\t" not in line:  # sécurité
                continue
            img, label = line.strip().split("\t", 1)
            stem = os.path.splitext(os.path.basename(img))[0]
            gt[stem] = label
    return gt

gt = load_gt_from_txt(anno_path)

def cer(ref, hyp):
    return Levenshtein.distance(ref, hyp) / max(1, len(ref))

def wer(ref, hyp):
    return Levenshtein.distance(" ".join(ref.split()), " ".join(hyp.split())) / max(1, len(ref.split()))

def evaluate(ocr_func, img_dir, gt):
    scores = {"cer": [], "wer": []}
    for img_rel, ref in gt.items():
        img_path = os.path.join(data_dir, img_rel)
        if not os.path.exists(img_path):
            continue
        hyp = ocr_func(img_path)
        scores["cer"].append(cer(ref, hyp))
        scores["wer"].append(wer(ref, hyp))
    return {k: sum(v)/len(v) if v else 1.0 for k,v in scores.items()}

# --- OCRs
paddle_custom = PaddleOCR(det_model_dir=None, rec_model_dir=model_dir, use_angle_cls=False, lang="en")
run_paddle_custom = lambda img: " ".join([l[1][0] for l in paddle_custom.ocr(img, cls=False)[0]])

paddle_base = PaddleOCR(use_angle_cls=False, lang="en")
run_paddle_base = lambda img: " ".join([l[1][0] for l in paddle_base.ocr(img, cls=False)[0]])

run_tess = lambda img: pytesseract.image_to_string(img, lang="eng").strip()

# --- Scores
res_custom = evaluate(run_paddle_custom, img_dir, gt)
res_base = evaluate(run_paddle_base, img_dir, gt)
res_tess = evaluate(run_tess, img_dir, gt)

# --- Infos YAML
with open(config_path, "r", encoding="utf-8") as f:
    yml = f.read()
yml_hash = hashlib.md5(yml.encode()).hexdigest()

# --- Dataset size
nb_train = len(open(os.path.join(data_dir,"train.txt")).read().splitlines())
nb_val = len(open(os.path.join(data_dir,"val.txt")).read().splitlines())
nb_test = len(open(os.path.join(data_dir,"test/anno")).readlines()) if os.path.isdir(os.path.join(data_dir,"test/anno")) else len(gt)

# --- CSV append
header = ["yaml_hash","train_size","val_size","test_size","ocr","cer","wer","export_dir"]

rows = []
for name, res in [("paddle_custom",res_custom),("paddle_base",res_base),("tesseract",res_tess)]:
    rows.append([yml_hash, nb_train, nb_val, nb_test, name, res["cer"], res["wer"], export_dir])

write_header = not os.path.exists(csv_path)
with open(csv_path,"a",newline="",encoding="utf-8") as f:
    w = csv.writer(f)
    if write_header: w.writerow(header)
    w.writerows(rows)

print(f"Résultats ajoutés à {csv_path}")