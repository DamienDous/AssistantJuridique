#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, cv2, csv, json, paddle, yaml, math
import numpy as np
from pathlib import Path
import pytesseract
from Levenshtein import distance as lev_dist
from tools.program import load_config
from ppocr.modeling.architectures import build_model
from ppocr.postprocess import DBPostProcess
from ppocr.postprocess import build_post_process
from ppocr.utils.save_load import load_model
from ppocr.postprocess.rec_postprocess import CTCLabelDecode
from ppocr.data import create_operators

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

def load_rec_model(cfg_path, ckpt_path):
    cfg = load_config(cfg_path)
    dict_path = cfg["Global"]["character_dict_path"]
    nb_chars = sum(1 for _ in open(dict_path, "r", encoding="utf-8"))
    if cfg["Global"].get("use_space_char", False):
        nb_chars += 1

    ctc_classes  = nb_chars + 1
    sar_classes  = 0
    nrtr_classes = nb_chars + 4

    post_process_class = build_post_process(cfg["PostProcess"])

    if cfg["Architecture"]["Head"]["name"] == "MultiHead":
        out_channels_list = {
            "CTCLabelDecode": ctc_classes,
            "SARLabelDecode": sar_classes,
            "NRTRLabelDecode": nrtr_classes
        }
        cfg["Architecture"]["Head"]["out_channels_list"] = out_channels_list
        print(f"[DEBUG] out_channels_list forcé → {out_channels_list}")

        print("[DEBUG] nb_chars:", nb_chars)
        print("[DEBUG] CTC out_channels:", ctc_classes)
        print("[DEBUG] SAR out_channels:", sar_classes)
        print("[DEBUG] NRTR out_channels:", nrtr_classes)
        print("[DEBUG] cfg[Head][out_channels_list]:", cfg["Architecture"]["Head"]["out_channels_list"])

    model = build_model(cfg["Architecture"])
    load_model(cfg, model, model_type='rec')
    model.eval()

    return model, post_process_class

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

def build_rec_preprocess(config_path):
    cfg = load_config(config_path)

    ops = create_operators(cfg["Eval"]["dataset"]["transforms"], global_config=cfg.get("Global", {}))
    return ops

def resize_norm_img_rec(img, image_shape=(3, 32, 320), padding=True):
    """
    Prétraitement des crops pour la reconnaissance OCR (rec_model).
    - Redimensionne en gardant le ratio hauteur/largeur
    - Normalise en [-1, 1]
    - Ajoute du padding à droite si nécessaire
    - Retourne un tableau float32 (C, H, W)
    """
    imgC, imgH, imgW = image_shape

    h, w = img.shape[0:2]
    ratio = w / float(h)

    # nouvelle largeur
    if math.ceil(imgH * ratio) > imgW:
        resized_w = imgW
    else:
        resized_w = int(math.ceil(imgH * ratio))

    # resize
    resized_image = cv2.resize(img, (resized_w, imgH))

    # normalisation [0,255] → [-1,1]
    resized_image = resized_image.astype("float32") / 255.
    resized_image -= 0.5
    resized_image /= 0.5

    if padding:
        # padding si la largeur < imgW
        padding_im = np.zeros((imgH, imgW, imgC), dtype=np.float32)
        padding_im[:, 0:resized_w, :] = resized_image
    else:
        padding_im = resized_image

    # HWC → CHW
    padding_im = padding_im.transpose((2, 0, 1))

    return padding_im

def infer_batch(rec_model, rec_post, crops):
    if len(crops) == 0:
        return []

    try:
        imgs = []
        for i, crop in enumerate(crops):
            im = resize_norm_img_rec(crop)
            imgs.append(im)

        x = np.stack(imgs)
        x = paddle.to_tensor(x, dtype="float32")
        preds = rec_model(x)
        results = rec_post(preds)
        texts = []
        for i, res in enumerate(results):
            if isinstance(res, tuple):
                txt, score = res
            else:
                txt, score = res, None
            texts.append(txt)

        return texts

    except Exception as e:
        print(f"[ERROR] infer_batch failed: {e}")
        import traceback; traceback.print_exc()
        return []

def load_gt_bboxes(json_path):
    data = json.load(open(json_path, encoding="utf-8"))
    bboxes = []
    for c in data.get("cells", []):
        if "bbox" in c and c["bbox"]:
            x, y, w, h = c["bbox"]
            bboxes.append((x, y, x+w, y+h, c.get("text","")))
    return bboxes

def load_gt_from_json(json_path, sort_by_position=True):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Les textes sont dans "cells"
    cells = data.get("cells", [])
    if not isinstance(cells, list):
        return ""

    items = []
    for cell in cells:
        text = cell.get("text", "").strip()
        bbox = cell.get("bbox", [])
        if text:
            if sort_by_position and bbox and len(bbox) >= 2:
                x, y = bbox[0], bbox[1]
                items.append((y, x, text))
            else:
                items.append((0, 0, text))

    # Tri par Y puis X
    if sort_by_position:
        items.sort(key=lambda t: (t[0], t[1]))

    full_text = " ".join([it[2] for it in items])
    return full_text.strip()

def resize_img(img, max_side_len=960):
    """Resize l'image tout en gardant le ratio et en limitant le côté max à max_side_len"""
    h, w, _ = img.shape
    ratio = 1.0
    if max(h, w) > max_side_len:
        ratio = float(max_side_len) / max(h, w)
    resize_h = int(h * ratio)
    resize_w = int(w * ratio)

    resize_h = max(32, int(round(resize_h / 32) * 32))
    resize_w = max(32, int(round(resize_w / 32) * 32))

    img = cv2.resize(img, (resize_w, resize_h))
    ratio_h = resize_h / float(h)
    ratio_w = resize_w / float(w)

    return img, (ratio_h, ratio_w)

def prepare_det_input(img):
    """Prépare une image pour le modèle de détection PaddleOCR"""
    # Resize
    img, ratio = resize_img(img)

    # Normalisation [0,1]
    img = img.astype("float32")
    img = img / 255.0

    # Normalisation avec mean/std comme dans PaddleOCR
    mean = np.array([0.485, 0.456, 0.406]).reshape((1, 1, 3)).astype("float32")
    std = np.array([0.229, 0.224, 0.225]).reshape((1, 1, 3)).astype("float32")
    img = (img - mean) / std

    # HWC -> CHW
    img = img.transpose((2, 0, 1))

    # Ajout batch dimension
    img = np.expand_dims(img, axis=0)

    # Conversion Paddle tensor
    img = paddle.to_tensor(img)

    return img, ratio

def resize_norm_img_det(img, limit_side_len=960, limit_type='min'):
    """
    Prétraitement officiel PP-OCR pour la détection.
    Redimensionne l'image à une taille compatible (multiple de 32).
    """
    h, w, _ = img.shape
    if limit_type == 'min':
        ratio = float(limit_side_len) / min(h, w)
    else:
        ratio = float(limit_side_len) / max(h, w)

    resize_h = int(round(h * ratio / 32) * 32)
    resize_w = int(round(w * ratio / 32) * 32)

    img = cv2.resize(img, (resize_w, resize_h))

    # normalisation
    img = img.astype('float32')
    img = img / 255.
    img -= np.array([0.485, 0.456, 0.406], dtype=np.float32)
    img /= np.array([0.229, 0.224, 0.225], dtype=np.float32)

    img = img.transpose((2, 0, 1))  # HWC → CHW
    return img, (resize_h, resize_w)

def get_dt_boxes(det_model, det_post, img):
    img_resized, (resize_h, resize_w) = resize_norm_img_det(img)
    x = np.expand_dims(img_resized, axis=0)  # [1, C, H, W]
    x = paddle.to_tensor(x, dtype="float32")

    pred = det_model(x)

    outs_dict = {}
    if isinstance(pred, (list, tuple)):
        outs_dict['maps'] = pred[0]
    else:
        outs_dict['maps'] = pred

    src_h, src_w = img.shape[:2]
    ratio_h = float(resize_h) / src_h
    ratio_w = float(resize_w) / src_w
    shape_list = [(src_h, src_w, ratio_h, ratio_w)]

    result = det_post(outs_dict, shape_list)

    boxes = []
    for i, item in enumerate(result):
        if isinstance(item, dict) and "points" in item:
            for pts in item["points"]:
                boxes.append(np.array(pts, dtype=np.float32))
        elif isinstance(item, (list, np.ndarray)):
            boxes.append(np.array(item, dtype=np.float32))

    return boxes

def get_rotate_crop_image(img, points):
    points = np.array(points).astype(np.float32)
    
    w = int(np.linalg.norm(points[0] - points[1]))
    h = int(np.linalg.norm(points[0] - points[3]))
    dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)

    M = cv2.getPerspectiveTransform(points, dst)
    warped = cv2.warpPerspective(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
    return warped

# --------------------------
# OCR complet d'une page
# --------------------------
def ocr_page(det_model, det_post, rec_model, rec_post, img_path):
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"Impossible de lire {img_path}")

    # 1. Détection
    dt_boxes = get_dt_boxes(det_model, det_post, img)
    if not dt_boxes:
        print(f"[WARN] Aucune box détectée pour {img_path}")
        return ""

    # 2. Crops + coordonnées
    items = []
    success, failed = 0, 0
    for box in dt_boxes:
        try:
            crop = get_rotate_crop_image(img, box)
            text = infer_batch(rec_model, rec_post, [crop])[0]

            x, y = np.min(box[:,0]), np.min(box[:,1])
            items.append((y, x, text))

        except Exception as e:
            print(f"[WARN] crop raté pour box={box}: {e}")

    print(f"[DEBUG][ocr_page] crops réussis={success}, échecs={failed}, total={len(dt_boxes)}")

    if not items:
        return ""

    # 3. Tri Y puis X
    items.sort(key=lambda t: (t[0], t[1]))

    # 4. Regroupement en lignes
    lines = []
    current_line = []
    last_y = None
    y_threshold = 15  # tolérance verticale pour grouper les mots

    for y, x, text in items:
        if last_y is None or abs(y - last_y) < y_threshold:
            current_line.append((x, text))
            last_y = y if last_y is None else (last_y + y) / 2
        else:
            current_line.sort(key=lambda t: t[0])
            lines.append(" ".join([t[1] for t in current_line]))
            current_line = [(x, text)]
            last_y = y
    if current_line:
        current_line.sort(key=lambda t: t[0])
        lines.append(" ".join([t[1] for t in current_line]))

    final_text = "\n".join(lines)
    return final_text.strip()

# --------------------------
# Main
# --------------------------
if __name__=="__main__":
    det_cfg = "/workspace/config/ch_PP-OCRv4_det_infer.yml"
    det_ckpt = "/workspace/models/ch_PP-OCRv4_det_infer/inference"
    rec_cfg = "/workspace/output/rec_ppocr_v4/config.yml"
    rec_ckpt = "/workspace/output/rec_ppocr_v4/best_accuracy.pdparams"

    # Infos supplémentaires
    model_name = "rec_ppocr_v4_1M_en_200K_fr_9_epochs"
    epochs = 9   # à mettre à jour selon ton entraînement

    pages_dir = "/workspace/img"
    json_dir  = "/workspace/anno"
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

    count = 0
    for page_file in sorted(all_pages):
        print(f"[PAGE] Processing {page_file.name}")
        json_file = Path(json_dir) / f"{page_file.stem}.json"

        if not json_file.exists():
            print(f"[SKIP] Pas de JSON pour {page_file.name}")
            continue

        ref_full = load_gt_from_json(json_file)
        if not ref_full:
            print(f"[SKIP] GT vide pour {page_file.name}")
            continue

        pred_paddle = ocr_page(det_model, det_post, rec_model, rec_post, str(page_file))
        pred_tess = pytesseract.image_to_string(cv2.imread(str(page_file)), lang="eng").strip()

        cer_p, wer_p = cer(ref_full, pred_paddle), wer(ref_full, pred_paddle)
        cer_t, wer_t = cer(ref_full, pred_tess), wer(ref_full, pred_tess)

        total_cer_paddle.append(cer_p)
        total_wer_paddle.append(wer_p)
        total_cer_tess.append(cer_t)
        total_wer_tess.append(wer_t)

        count += 1
        if count > 30:
            break
        print(f"name: {page_file.name}  count: {count}  cer_p={cer_p:.3f}, wer_p={wer_p:.3f}")

    mean_cer_paddle = sum(total_cer_paddle) / len(total_cer_paddle) if total_cer_paddle else 1.0
    mean_wer_paddle = sum(total_wer_paddle) / len(total_wer_paddle) if total_wer_paddle else 1.0
    mean_cer_tess = sum(total_cer_tess) / len(total_cer_tess) if total_cer_tess else 1.0
    mean_wer_tess = sum(total_wer_tess) / len(total_wer_tess) if total_wer_tess else 1.0

    # ⬇️ On ajoute model_name et epochs
    with open(results_csv, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if csvfile.tell() == 0:  # écrire l'entête si fichier vide
            writer.writerow([
                "model_name", "epochs", "nb_pages",
                "mean_cer_paddle", "mean_wer_paddle",
                "mean_cer_tess", "mean_wer_tess"
            ])
        writer.writerow([
            model_name, epochs, count,
            mean_cer_paddle, mean_wer_paddle,
            mean_cer_tess, mean_wer_tess
        ])

    print(f"[OK] Statistiques globales enregistrées dans {results_csv}")

    print(f"[SUMMARY] Model={model_name}, Epochs={epochs}")
    print(f"[SUMMARY] Pages traitées: {count}")
    print("=== Résumé global ===")
    print(f"CER Paddle   : {mean_cer_paddle:.3f}")
    print(f"WER Paddle   : {mean_wer_paddle:.3f}")
    print(f"CER Tesseract: {mean_cer_tess:.3f}")
    print(f"WER Tesseract: {mean_wer_tess:.3f}")
    print(f"Détails → {results_csv}")