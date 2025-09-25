#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, cv2, csv, json, paddle
import numpy as np
from pathlib import Path
import pytesseract
from Levenshtein import distance as lev_dist
from tools.program import load_config
from paddleocr import TextDetection
from ppocr.modeling.architectures import build_model
from ppocr.postprocess import CTCLabelDecode, SARLabelDecode, DBPostProcess
from ppocr.postprocess import build_post_process

import shutil

# Copie auto du config si absent
det_cfg_src = "/workspace/det/PP-OCRv5_server_det_infer/inference.yml"
det_cfg_dst = "/workspace/config/inference_det.yml"

if not os.path.exists(det_cfg_dst):
    print(f"[INFO] Copie du config {det_cfg_src} → {det_cfg_dst}")
    shutil.copy(det_cfg_src, det_cfg_dst)
else:
    print(f"[INFO] Utilisation du config existant : {det_cfg_dst}")

# --------------------------
# Metrics
# --------------------------
def cer(ref, hyp): return lev_dist(ref, hyp) / max(1, len(ref))
def wer(ref, hyp): return lev_dist(" ".join(ref.split()), " ".join(hyp.split())) / max(1, len(ref.split()))

# --------------------------
# JSON → texte GT
# --------------------------
def json_to_gt_text(json_path, sort_by_position=True):
    try:
        data = json.load(open(json_path, encoding="utf-8"))
    except Exception:
        return ""
    cells = data.get("cells", [])
    if not isinstance(cells, list): return ""

    lines = []
    for c in cells:
        txt = c.get("text", "").strip()
        bbox = c.get("bbox", None)
        if not txt: continue
        if sort_by_position and bbox and len(bbox) >= 2:
            x, y = bbox[0], bbox[1]
            lines.append(((y, x), txt))
        else:
            lines.append(((0,0), txt))

    if sort_by_position:
        lines.sort(key=lambda t: (t[0][0], t[0][1]))  # tri Y puis X

    return " ".join([t[1] for t in lines])

def ensure_gt(page_file, gt_dir, json_dir):
    gt_file = Path(gt_dir) / (page_file.stem + ".txt")
    if gt_file.exists():
        return gt_file
    json_file = Path(json_dir) / (page_file.stem + ".json")
    if not json_file.exists():
        return None
    text = json_to_gt_text(json_file, sort_by_position=True)
    gt_file.parent.mkdir(parents=True, exist_ok=True)
    with open(gt_file, "w", encoding="utf-8") as f:
        f.write(text)
    return gt_file

# --------------------------
# Prétraitement page
# --------------------------
def preprocess_page(img_path, target_size=960):
    img = cv2.imread(img_path).astype("float32")
    if img is None:
        raise FileNotFoundError(img_path)

    h, w = img.shape[:2]
    scale = target_size / max(h, w)
    new_h, new_w = int(h * scale), int(w * scale)
    resized = cv2.resize(img, (new_w, new_h))
    canvas = np.ones((target_size, target_size, 3), dtype=np.float32) * 255
    canvas[:new_h, :new_w] = resized

    canvas /= 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std  = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    canvas = (canvas - mean) / std

    ratio_h, ratio_w = scale, scale
    return canvas, (h, w, ratio_h, ratio_w)

# --------------------------
# Charger modèle DBNet
# --------------------------
def load_det_model(infer_dir):
    """
    Charge un modèle de détection (DBNet) exporté en mode inference
    :param infer_dir: dossier contenant inference.pdiparams + inference.yml + inference.json
    :return: instance TextDetection
    """
    model = TextDetection(
        model_name=None,          # sinon il essaie de télécharger HuggingFace
        model_dir=infer_dir,      # ton dossier local
        device="gpu"              # ou "cpu"
    )
    return model

def debug_draw_boxes(img, boxes, page_name="page"):
    """
    Trace les bounding boxes détectées sur une copie de l'image.
    Sauvegarde le résultat dans /workspace/debug_boxes.
    """
    debug_dir = "/workspace/debug_boxes"
    os.makedirs(debug_dir, exist_ok=True)

    vis = img.copy()
    for i, box in enumerate(boxes):
        box = np.array(box).reshape(-1, 1, 2).astype(int)
        cv2.polylines(vis, [box], isClosed=True, color=(0, 0, 255), thickness=2)
        cv2.putText(vis, str(i), tuple(box[0][0]), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 0, 0), 1, cv2.LINE_AA)

    out_path = os.path.join(debug_dir, f"{page_name}_debug.png")
    cv2.imwrite(out_path, vis)
    print(f"[DEBUG] Boxes visualisées → {out_path}")

def detect_text_boxes(model, post, img, shape_list):
    tensor = paddle.to_tensor(img.astype("float32").transpose(2,0,1)[np.newaxis])
    with paddle.no_grad():
        outs_dict = model(tensor)
        for k, v in outs_dict.items():
            print(f"[DEBUG] {k} shape: {v.shape}")
    if isinstance(outs_dict, dict):
        if "maps" in outs_dict:
            preds = outs_dict["maps"]
            print("[DEBUG] Using outs_dict['maps'], shape:", preds.shape)
        elif "Student" in outs_dict and isinstance(outs_dict["Student"], dict):
            preds = outs_dict["Student"].get("maps", None)
            print("[DEBUG] Using Student['maps'], shape:", None if preds is None else preds.shape)
        else:
            preds = list(outs_dict.values())[0]
            print("[DEBUG] Using first value, shape:", preds.shape)
    else:
        preds = outs_dict
        print("[DEBUG] outs_dict not dict, shape:", preds.shape)

    # Toujours envelopper dans un dict pour DBPostProcess
    preds = {"maps": preds}

    # Postprocess
    shape = np.array([shape_list], dtype=np.float32)
    result = post(preds, shape)
    print(f"[DEBUG] shape passed to post: {shape}")
    print(f"[DEBUG] post() returned {type(result)}, len {len(result)}")

    boxes, scores = [], []
    for i, item in enumerate(result):
        if isinstance(item, dict) and "points" in item:
            pts = np.array(item["points"])
            print(f"[DEBUG] Box #{i} points shape:", pts.shape)
            if pts.ndim == 2 and pts.shape[1] == 2:
                boxes.append(pts.astype(int))
            elif pts.ndim == 3 and pts.shape[1] == 4 and pts.shape[2] == 2:
                for j, sub in enumerate(pts):
                    print(f"[DEBUG] → Ajout sous-box {j} shape {sub.shape}")
                    boxes.append(sub.astype(int))
            else:
                print(f"[WARN] Shape non gérée: {pts.shape}")
        else:
            print(f"[WARN] Box #{i} ignoré, type inattendu:", type(item))

    return boxes, scores if scores else None


# --------------------------
# Charger modèle MultiHead
# --------------------------
def load_rec_model(cfg_path, ckpt_path):
    import paddle

    # 🔹 Forcer CPU
    paddle.set_device("gpu")

    cfg = load_config(cfg_path)
    cfg["Global"]["pretrained_model"] = ckpt_path

    # Compter les caractères
    with open(cfg["Global"]["character_dict_path"], encoding="utf-8") as f:
        num_chars = len(f.readlines())
    if cfg["Global"].get("use_space_char", False):
        num_chars += 1

    out_channels_list = {
        "CTCLabelDecode": num_chars,
        "SARLabelDecode": num_chars + 1
    }
    print("[DEBUG] out_channels_list =", out_channels_list)
    cfg["Architecture"]["Head"]["out_channels_list"] = out_channels_list

    # Charger modèle + poids (sans map_location)
    model = build_model(cfg["Architecture"])
    state_dict = paddle.load(ckpt_path + ".pdparams")   # ✅ corrigé
    model.set_state_dict(state_dict)
    model.eval()

    # Décodeurs de sortie
    post = {
        "CTCLabelDecode": CTCLabelDecode(
            character_dict_path=cfg["Global"]["character_dict_path"],
            use_space_char=cfg["Global"].get("use_space_char", False)
        ),
        "SARLabelDecode": SARLabelDecode(
            character_dict_path=cfg["Global"]["character_dict_path"],
            max_text_length=cfg["Global"]["max_text_length"],
            use_space_char=cfg["Global"].get("use_space_char", False)
        )
    }

    return model, post

def preprocess_crop(crop, target_h=48, target_w=320):
    h, w = crop.shape[:2]; scale = target_h / h
    new_w = int(w * scale)
    resized = cv2.resize(crop, (new_w, target_h), interpolation=cv2.INTER_LANCZOS4)
    if new_w >= target_w: return resized[:, :target_w, :]
    canvas = np.ones((target_h,target_w,3),dtype=np.uint8)*255
    canvas[:, :new_w, :] = resized
    return canvas

def infer_crop(model, post, crop):
    crop = preprocess_crop(crop)
    debug_dir = "/workspace/debug_crops"
    os.makedirs(debug_dir, exist_ok=True)
    cv2.imwrite(os.path.join(debug_dir, f"crop_{np.random.randint(1e6)}.png"), crop)

    img = crop.astype("float32")/255.
    img = img.transpose((2,0,1))[np.newaxis,:]
    img = paddle.to_tensor(img)
    with paddle.no_grad():
        preds = model(img)

    # Forcer uniquement CTC
    if isinstance(preds, dict) and "ctc" in preds:
        return post["CTCLabelDecode"](preds["ctc"])[0][0]
    else:
        return post["CTCLabelDecode"](preds)[0][0]

def load_gt_bboxes(json_path):
    data = json.load(open(json_path, encoding="utf-8"))
    bboxes = []
    for c in data.get("cells", []):
        if "bbox" in c and c["bbox"]:
            x, y, w, h = c["bbox"]
            bboxes.append((x, y, x+w, y+h, c.get("text","")))
    return bboxes

# --------------------------
# OCR complet d'une page
# --------------------------
def ocr_page(det_model, rec_model, rec_post, img_path):
    original_img = cv2.imread(img_path)
    if original_img is None:
        raise FileNotFoundError(img_path)

    # 🔹 prédiction PaddleOCR
    results = det_model.predict(img_path, batch_size=1)

    preds = []
    for res in results:
        for poly in res.res["dt_polys"]:
            x_min, y_min = np.min(poly[:,0]), np.min(poly[:,1])
            x_max, y_max = np.max(poly[:,0]), np.max(poly[:,1])
            crop = original_img[int(y_min):int(y_max), int(x_min):int(x_max)]
            if crop.size == 0:
                continue
            txt_ctc = infer_crop(rec_model, rec_post, crop)
            preds.append((y_min, x_min, txt_ctc))

    preds.sort()
    return " ".join([f"[CTC:{p[2]}]" for p in preds])

# --------------------------
# Main
# --------------------------
if __name__=="__main__":
    det_infer_dir = "/workspace/pretrain_models/PP-OCRv5_server_det_infer"
    rec_cfg = "/workspace/config/latin_PP-OCRv3_rec.multihead.yml"
    rec_ckpt = "./output/rec_ppocr_v3_latin/latest"
    
    pages_dir = "/workspace/img"     # dossier avec images
    json_dir  = "/workspace/anno"      # JSON avec les GT
    gt_dir    = "/workspace/gt"

    print(f"[INFO] pages_dir={pages_dir} exists={Path(pages_dir).exists()}")
    print(f"[INFO] json_dir={json_dir} exists={Path(json_dir).exists()}")

    det_model, det_post = load_det_model(det_infer_dir)
    rec_model, rec_post = load_rec_model(rec_cfg, rec_ckpt)

    results_csv = "/workspace/eval/eval_pages.csv"
    Path(os.path.dirname(results_csv)).mkdir(parents=True, exist_ok=True)

    total_cer_paddle, total_wer_paddle, total_cer_tess, total_wer_tess = [], [], [], []

    all_pages = []
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.tif", "*.tiff"]:
        all_pages.extend(Path(pages_dir).glob(ext))

    with open(results_csv,"w",newline="",encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["page","ref","paddle","tesseract","cer_paddle","wer_paddle","cer_tess","wer_tess"])

        count = 0
        for page_file in sorted(all_pages):
            print(f"[PAGE] Processing {page_file.name}")
            gt_file = ensure_gt(page_file, gt_dir, json_dir)
            if not gt_file or not gt_file.exists():
                print(f"[SKIP] Pas de GT pour {page_file.name}")
                continue

            ref = open(gt_file,encoding="utf-8").read().strip()
            if not ref:
                print(f"[SKIP] GT vide pour {page_file.name}")
                continue

            pred_paddle = ocr_page(det_model, det_post, rec_model, rec_post, str(page_file))
            pred_tess   = pytesseract.image_to_string(cv2.imread(str(page_file)), lang="eng").strip()

            print(f"[DEBUG] ref='{ref[:30]}...' pred_paddle='{pred_paddle[:30]}...'")

            cer_p, wer_p = cer(ref,pred_paddle), wer(ref,pred_paddle)
            cer_t, wer_t = cer(ref,pred_tess), wer(ref,pred_tess)

            total_cer_paddle.append(cer_p); total_wer_paddle.append(wer_p)
            total_cer_tess.append(cer_t); total_wer_tess.append(wer_t)

            writer.writerow([page_file.name, ref, pred_paddle, pred_tess, cer_p, wer_p, cer_t, wer_t])
            count += 1

    print(f"[SUMMARY] Pages traitées: {count}")
    print("=== Résumé global ===")
    print(f"CER Paddle   : {np.mean(total_cer_paddle) if total_cer_paddle else 'VIDE'}")
    print(f"WER Paddle   : {np.mean(total_wer_paddle) if total_wer_paddle else 'VIDE'}")
    print(f"CER Tesseract: {np.mean(total_cer_tess) if total_cer_tess else 'VIDE'}")
    print(f"WER Tesseract: {np.mean(total_wer_tess) if total_wer_tess else 'VIDE'}")
    print(f"Détails → {results_csv}")
