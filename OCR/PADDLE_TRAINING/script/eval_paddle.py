#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, cv2, csv, json, paddle, yaml
import numpy as np
from pathlib import Path
import pytesseract
from Levenshtein import distance as lev_dist
from tools.program import load_config
from ppocr.modeling.architectures import build_model
from ppocr.postprocess import DBPostProcess
from ppocr.postprocess import build_post_process
from ppocr.utils.save_load import load_model

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
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(img_path)

    h, w = img.shape[:2]
    scale = target_size / max(h, w)
    new_h, new_w = int(h * scale), int(w * scale)
    resized = cv2.resize(img, (new_w, new_h))

    # Canvas carré blanc
    canvas = np.ones((target_size, target_size, 3), dtype=np.float32) * 255
    canvas[:new_h, :new_w] = resized

    # Normalisation simple [0,1]
    canvas = canvas.astype("float32") / 255.0

    return canvas, (h, w, scale, scale)
# --------------------------
# Charger modèle DBNet
# --------------------------
def load_det_model(cfg_path, ckpt_path):
    print(f"[INFO] Chargement modèle inference depuis {ckpt_path}")
    model = paddle.jit.load(ckpt_path)
    model.eval()
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    det_post = DBPostProcess(**cfg["PostProcess"], global_config=cfg["Global"])
    return model, det_post

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
        preds = model(tensor)

    if isinstance(preds, dict):
        preds = preds.get("maps", list(preds.values())[0])
        print("[DEBUG] dict output, shape:", preds.shape)
    else:
        print("[DEBUG] raw Tensor, shape:", preds.shape)

    result = post({"maps": preds}, np.array([shape_list], dtype=np.float32))
    print(f"[DEBUG] post() returned {type(result)}, len {len(result)}")

    boxes = []
    for i, item in enumerate(result):
        if isinstance(item, dict) and "points" in item:
            pts_array = np.array(item["points"])
            print(f"[DEBUG] item[{i}] contient {pts_array.shape[0]} boxes")
            for pts in pts_array:
                boxes.append(pts.astype(int))

    return boxes, None

# --------------------------
# Charger modèle Reconnaissance (CTC only)
# --------------------------
def load_rec_model(config_path, ckpt_path):
    # Charger la config YAML
    cfg = load_config(config_path)

    # Postprocess (pour connaître nb de caractères)
    post_process = build_post_process(cfg["PostProcess"], global_config=cfg.get("Global", {}))
    char_num = len(post_process.character) if hasattr(post_process, "character") else 0
    print(f"[INFO] nb chars (dictionnaire): {char_num}")

    # Patch MultiHead ou simple Head
    if cfg["Architecture"]["Head"]["name"] == "MultiHead":
        out_channels_list = {
            "CTCLabelDecode": char_num,
            "SARLabelDecode": char_num + 2,
            "NRTRLabelDecode": char_num + 3,
        }
        cfg["Architecture"]["Head"]["out_channels_list"] = out_channels_list
        print("[INFO] MultiHead détecté → out_channels_list ajusté:", out_channels_list)
    else:
        cfg["Architecture"]["Head"]["out_channels"] = char_num

    # Construire le modèle
    model = build_model(cfg["Architecture"])

    # Charger les poids
    load_model(config=cfg, model=model, optimizer=None, model_type="rec")

    model.eval()
    return model, post_process

def preprocess_crop(crop, target_h=48, target_w=320):
    h, w = crop.shape[:2]; scale = target_h / h
    new_w = int(w * scale)
    resized = cv2.resize(crop, (new_w, target_h), interpolation=cv2.INTER_LANCZOS4)
    if new_w >= target_w: return resized[:, :target_w, :]
    canvas = np.ones((target_h,target_w,3),dtype=np.uint8)*255
    canvas[:, :new_w, :] = resized
    return canvas

def safe_decode(post_func, preds):
    out = post_func(preds, None)
    if isinstance(out, tuple):
        texts, scores = out
    else:
        texts, scores = out, None
    if texts and isinstance(texts[0], (list, tuple)):
        texts = [t[0] for t in texts]
    return texts, scores

def infer_crop(rec_model, post_ctc, crop):
    import cv2, paddle

    img = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (320, 48)).astype("float32") / 255.0
    img = img.transpose(2,0,1)

    mean = np.array([0.5,0.5,0.5], dtype=np.float32).reshape(3,1,1)
    std  = np.array([0.5,0.5,0.5], dtype=np.float32).reshape(3,1,1)
    img = (img - mean) / std

    img = paddle.to_tensor(img).unsqueeze(0)

    preds = rec_model(img)

    txt_ctc = ""
    if isinstance(preds, dict) and "ctc" in preds:
        texts, _ = safe_decode(post_ctc, preds["ctc"])
        if texts: txt_ctc = texts[0]
    elif isinstance(preds, paddle.Tensor):
        texts, _ = safe_decode(post_ctc, preds)
        if texts: txt_ctc = texts[0]

    return txt_ctc

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
def ocr_page(det_model, det_post, rec_model, rec_post, img_path):
    original_img = cv2.imread(img_path)
    if original_img is None:
        raise FileNotFoundError(img_path)

    img, shape_list = preprocess_page(img_path)
    boxes, scores = detect_text_boxes(det_model, det_post, img, shape_list)
    debug_draw_boxes(original_img, boxes, Path(img_path).stem)

    preds = []
    print(f"[DEBUG] boxes type={type(boxes)} len={len(boxes) if hasattr(boxes,'__len__') else 'NA'}")

    for i, box in enumerate(boxes):
        box = np.array(box)
        if box.ndim != 2 or box.shape[1] != 2:
            print(f"[WARN] Box #{i} ignorée, shape inattendue: {box.shape}")
            continue

        x_min, y_min = np.min(box[:, 0]), np.min(box[:, 1])
        x_max, y_max = np.max(box[:, 0]), np.max(box[:, 1])

        crop = original_img[int(y_min):int(y_max), int(x_min):int(x_max)]
        if crop.size == 0:
            print(f"[WARN] Box #{i} → crop vide")
            continue

        txt_ctc = infer_crop(rec_model, rec_post, crop)
        preds.append((y_min, x_min, txt_ctc))

    preds.sort()
    print(preds)
    return " ".join([f"[CTC:{p[2]}]" for p in preds])


# --------------------------
# Main
# --------------------------
if __name__=="__main__":
    det_cfg = "/workspace/config/ch_PP-OCRv4_det_infer.yml"
    det_ckpt = "/workspace/models/ch_PP-OCRv4_det_infer/inference"
    rec_cfg = "/workspace/config/latin_PP-OCRv3_rec.multihead.yml"
    rec_ckpt = "/workspace/output/rec_ppocr_v3_latin/latest.pdparams"
    
    pages_dir = "/workspace/img"     # dossier avec images
    json_dir  = "/workspace/anno"      # JSON avec les GT
    gt_dir    = "/workspace/gt"

    print(f"[INFO] pages_dir={pages_dir} exists={Path(pages_dir).exists()}")
    print(f"[INFO] json_dir={json_dir} exists={Path(json_dir).exists()}")

    det_model, det_post = load_det_model(det_cfg, det_ckpt)
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
