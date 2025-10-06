#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, cv2, csv, json, paddle, yaml
import unicodedata, regex as re
import numpy as np
from pathlib import Path
import pytesseract
from Levenshtein import distance as lev_dist
from tools.program import load_config
from ppocr.modeling.architectures import build_model
from ppocr.postprocess import DBPostProcess
from ppocr.postprocess import build_post_process
from ppocr.utils.save_load import load_model
from ppocr.data import create_operators

# --------------------------
# Metrics
# --------------------------

def normalize_text(txt):
    """
    Normalise le texte OCR et GT avant calcul des métriques :
    - NFKC Unicode (évitent les variantes de même caractère)
    - guillemets / tirets / apostrophes uniformisés
    - ligatures œ → oe, æ → ae
    - collapse des espaces
    - suppression des césures ("-\n")
    """
    if not txt:
        return ""
    # Unicode standardisation
    txt = unicodedata.normalize("NFKC", txt)

    # Guillemets / apostrophes / tirets
    txt = txt.replace("’", "'").replace("‘", "'")
    txt = txt.replace("“", '"').replace("”", '"')
    txt = txt.replace("–", "-").replace("—", "-")

    # Ligatures
    txt = txt.replace("œ", "oe").replace("Œ", "Oe")
    txt = txt.replace("æ", "ae").replace("Æ", "Ae")

    # Hyphénation (fin de ligne)
    txt = re.sub(r"-\s*\n", "", txt)

    # Collapse espaces
    txt = re.sub(r"\s+", " ", txt.strip())

    # Lowercase (ou désactive si tu veux garder la casse)
    txt = txt.lower()

    return txt

def cer(ref, hyp):
    ref = normalize_text(ref)
    hyp = normalize_text(hyp)
    return lev_dist(ref, hyp) / max(1, len(ref))

def tokenize_words(txt):
    """Découpage français : garde les apostrophes internes (ex: l'avocat)"""
    return re.findall(r"[0-9\p{L}]+(?:'[0-9\p{L}]+)*", txt, flags=re.UNICODE)

def wer(ref, hyp):
    ref_tokens = tokenize_words(normalize_text(ref))
    hyp_tokens = tokenize_words(normalize_text(hyp))
    import numpy as np
    dp = np.zeros((len(ref_tokens)+1, len(hyp_tokens)+1), dtype=int)
    for i in range(len(ref_tokens)+1):
        dp[i,0]=i
    for j in range(len(hyp_tokens)+1):
        dp[0,j]=j
    for i in range(1,len(ref_tokens)+1):
        for j in range(1,len(hyp_tokens)+1):
            cost = 0 if ref_tokens[i-1]==hyp_tokens[j-1] else 1
            dp[i,j]=min(dp[i-1,j]+1, dp[i,j-1]+1, dp[i-1,j-1]+cost)
    return dp[len(ref_tokens),len(hyp_tokens)]/max(1,len(ref_tokens))

# --------------------------
# Chargement Modèles
# --------------------------
def load_det_model(cfg_path, ckpt_path):
    print(f"[INFO] Chargement modèle inference depuis {ckpt_path}")
    model = paddle.jit.load(ckpt_path)
    model.eval()
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    det_post = DBPostProcess(**cfg["PostProcess"], global_config=cfg["Global"])
    return model, det_post

def load_rec_model(cfg_path):
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

def load_rec_infer_model(cfg_path):
    cfg = load_config(cfg_path)
    model_prefix = cfg["Global"]["pretrained_model"]
    """
    Charge un modèle de reconnaissance inference (pdmodel + pdiparams)
    + son post-process (CTC, SAR, NRTR…)
    
    cfg_path : chemin vers le YAML (ex: rec_ch_PP-OCRv4.yaml)
    model_prefix : chemin vers le modèle (ex: /workspace/models/rec_infer/inference)
    """
    print(f"[INFO] Chargement modèle inference depuis {model_prefix}.pdmodel / .pdiparams")

    # 1. Charger le modèle (réseau)
    model = paddle.jit.load(model_prefix)
    model.eval()

    # 2. Charger la config YAML
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 3. Construire le post-process
    # (nb_classes = taille du dictionnaire + 1 pour CTC blank)
    post_process_class = build_post_process(cfg["PostProcess"], cfg["Global"])

    return model, post_process_class

def build_eval_ops(cfg):
    transforms = []
    for op in cfg['Eval']['dataset']['transforms']:
        op_name = list(op.keys())[0]
        if 'Label' in op_name or op_name == "DecodeImage":
            continue
        if op_name == 'RecResizeImg':
            op[op_name]['infer_mode'] = True
        if op_name == 'KeepKeys':
            op[op_name]['keep_keys'] = ['image']
        transforms.append(op)
    return create_operators(transforms, cfg['Global'])

# --------------------------
# Détection
# --------------------------
def get_dt_boxes(det_model, det_post, img, img_path):

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
    
    debug_draw_boxes(img, boxes, page_name=f"{Path(img_path).stem}_detection")

    return boxes

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

def bbox_iou(boxA, boxB):
    """Calcule l'IoU entre deux quadrilatères ou rectangles."""
    boxA = np.array(boxA).reshape(-1, 2)
    boxB = np.array(boxB).reshape(-1, 2)
    xA = max(np.min(boxA[:,0]), np.min(boxB[:,0]))
    yA = max(np.min(boxA[:,1]), np.min(boxB[:,1]))
    xB = min(np.max(boxA[:,0]), np.max(boxB[:,0]))
    yB = min(np.max(boxA[:,1]), np.max(boxB[:,1]))
    interW, interH = max(0, xB-xA), max(0, yB-yA)
    inter = interW * interH
    areaA = (np.max(boxA[:,0]) - np.min(boxA[:,0])) * (np.max(boxA[:,1]) - np.min(boxA[:,1]))
    areaB = (np.max(boxB[:,0]) - np.min(boxB[:,0])) * (np.max(boxB[:,1]) - np.min(boxB[:,1]))
    return inter / (areaA + areaB - inter + 1e-6)

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

# --------------------------
# Reconnaissance
# --------------------------
def infer_batch(rec_model, rec_post, rec_ops, crops, debug_prefix):
    imgs = []
    for idx, crop in enumerate(crops):
        # Sauvegarde du crop brut
        debug_dir = "/workspace/debug_crops"
        os.makedirs(debug_dir, exist_ok=True)

        # Sauvegarde après prétraitement (remettre en 0-255 pour visualiser)
        # im_vis = crop.copy()
        # im_vis = ((im_vis - im_vis.min()) / (im_vis.max()-im_vis.min()) * 255).astype("uint8")
        # cv2.imwrite(f"{debug_dir}/{debug_prefix}_proc_{idx}.png", im_vis)

        if crop.ndim == 3 and crop.shape[0] != 3 and crop.shape[2] == 3:
            crop = crop.transpose(2,0,1)
        imgs.append(crop.astype("float32"))

    if not imgs:
        return []
    
    x = np.stack(imgs)  # [N,3,H,W]
    x = paddle.to_tensor(x, dtype="float32")
    preds = rec_model(x)
    results = rec_post(preds)
    return results

def resize_norm_img_rec(img, rec_image_shape=(3, 48, 320)):
    """
    Prétraitement officiel PaddleOCR (RecResizeImg)
    - Conserve le ratio original
    - Redimensionne la hauteur à 48
    - Étend ou tronque la largeur à 320
    - Normalise en [-1, 1]
    - Format CHW (C,H,W)
    """
    c, imgH, imgW = rec_image_shape
    h, w = img.shape[:2]
    ratio = w / float(h)
    max_wh_ratio = imgW / float(imgH)

    # Redimensionnement proportionnel
    if ratio > max_wh_ratio:
        new_w = imgW
        new_h = int(imgW / ratio)
    else:
        new_h = imgH
        new_w = int(imgH * ratio)

    img = cv2.resize(img, (new_w, new_h))

    # Normalisation
    img = img.astype('float32') / 255.
    img = (img - 0.5) / 0.5

    # Padding à droite
    padding = np.zeros((imgH, imgW, 3), dtype=np.float32)
    padding[0:new_h, 0:new_w, :] = img

    # Conversion en CHW
    img = padding.transpose((2, 0, 1))
    return img

def get_rotate_crop_image(img, points, margin=0):
    points = np.array(points).astype(np.float32)
    w = int(np.linalg.norm(points[0] - points[1]))
    h = int(np.linalg.norm(points[0] - points[3]))
    if w < 2 or h < 2:
        raise ValueError(f"Crop trop petit: w={w}, h={h}")

    dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(points, dst)
    warped = cv2.warpPerspective(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
    return warped

def find_best_cut_region(img, max_width=320, min_width=40, search_back=80, window_size=10):
    """
    Trouve la meilleure plage blanche avant max_width pour couper entre les mots.
    - Analyse une fenêtre de 'window_size' colonnes.
    - Retourne la position de coupe (au centre de la meilleure fenêtre).
    """
    h, w = img.shape[:2]

    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
    # Densité d'encre par colonne (proportion de pixels sombres)
    ink_density = np.mean(gray < 200, axis=0)

    # Fenêtre de recherche
    start = max(min_width, max_width - search_back)
    end = min(max_width, w)

    segment = ink_density[start:end]
    seg_len = len(segment)
    if seg_len < window_size:
        return end  # pas assez de place pour chercher

    # Calculer la somme d'encre dans chaque fenêtre de `window_size`
    sums = np.convolve(segment, np.ones(window_size), mode="valid")
    # Trouver la fenêtre la plus "vide"
    best_local = np.argmin(sums)
    best_col = start + best_local + window_size // 2  # couper au centre de la fenêtre

    return best_col

# --------------------------
# 
# --------------------------
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

def split_long_crop(img, max_ratio=320/40*1.5, min_cut=40):
    """
    Combine la logique de split_long_crop (géométrique) et de split_crop_smart (visuelle).
    Découpe les lignes trop longues pour que chaque sous-image respecte w/h <= max_ratio.
    À chaque coupure, recherche la meilleure position de split dans une zone "blanche".
    """
    h, w = img.shape[:2]
    if h == 0 or w == 0:
        return []
    if w / h <= max_ratio:
        return [img]

    # Déterminer combien de sous-crops on aura théoriquement
    num_splits = int(np.ceil((w / h) / max_ratio))
    base_split_w = w // num_splits

    crops = []
    start_x = 0

    for i in range(num_splits):
        # largeur cible (sans dépasser)
        end_x = w if i == num_splits - 1 else min(start_x + base_split_w, w)

        if end_x < w:
            # Extraire la sous-zone à analyser
            sub_img = img[:, start_x:end_x, :]
            # Recherche d'une coupure intelligente proche de la limite droite
            cut_offset = find_best_cut_region(
                sub_img, max_width=sub_img.shape[1]
            )
            # Position absolue de la coupure
            cut_x = max(start_x + cut_offset, start_x + min_cut)
        else:
            cut_x = w

        # Extraire le crop final
        sub_crop = img[:, start_x:cut_x, :]
        crops.append(sub_crop)

        # Avancer au prochain
        start_x = cut_x

        # sécurité anti-boucle infinie
        if cut_x >= w - 1:
            break

    return crops

def ocr_page(det_model, det_post, rec_model, rec_post, rec_ops, img_path, type_rec):
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"Impossible de lire {img_path}")

    # 1. Détection
    dt_boxes = get_dt_boxes(det_model, det_post, img, img_path)
    if not dt_boxes:
        print(f"[WARN] Aucune box détectée pour {img_path}")
        return ""
    
    # Calcul IoU moyen entre boxes détectées et GT (si dispo)
    json_gt = Path(img_path).with_suffix(".json")
    mean_iou = None
    if json_gt.exists():
        with open(json_gt, "r", encoding="utf-8") as f:
            gt_data = json.load(f)
        gt_boxes = [np.array(c["bbox"]).reshape(-1,2) for c in gt_data.get("cells",[]) if "bbox" in c]
        ious = []
        for b in dt_boxes:
            best = 0
            for g in gt_boxes:
                i = bbox_iou(b,g)
                best = max(best,i)
            if best>0: ious.append(best)
        if ious:
            mean_iou = np.mean(ious)
            print(f"[INFO] IoU moyen des boxes détectées = {mean_iou:.3f}")

    # 2. Crops + coordonnées
    items = []
    success, failed = 0, 0
    nb = 0
    for box in dt_boxes:
        try:
            crop = get_rotate_crop_image(img, box)
            crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            sub_crops = split_long_crop(crop)

            cpt = 0
            for cr in sub_crops:
                debug_dir = "/workspace/debug_crops"
                os.makedirs(debug_dir, exist_ok=True)
                cv2.imwrite(f"{debug_dir}/{Path(img_path).stem}_{nb}_{cpt}.png", cv2.cvtColor(cr, cv2.COLOR_RGB2BGR))
                cpt += 1

            texts = ''
            for i, sub_crop in enumerate(sub_crops):
                if type_rec == "tesseract":
                    texts += pytesseract.image_to_string(
                        sub_crop, lang="eng", config="--oem 1 --psm 7"
                    ).strip()
                elif type_rec == "paddle":
                    norm_crop  = resize_norm_img_rec(sub_crop)
                    t = infer_batch(rec_model, rec_post, rec_ops, [norm_crop ], f"{Path(img_path).stem}_{nb}_{i}")
                    if t[0][0]:
                        success += 1
                        texts += " "
                        texts += t[0][0]
                    else:
                        failed += 1
                else:
                    print("[ERROR: rec model not found]")
            
            x, y = np.min(box[:,0]), np.min(box[:,1])
            items.append((y, x, texts))
            nb += 1
        except Exception as e:
            print(f"[WARN] crop raté pour box={box}: {e}")

    print(f"[DEBUG][ocr_page] crops success={success}, failed={failed}, total={len(dt_boxes)}")

    if not items:
        return ""

    # 3. Tri Y puis X
    items.sort(key=lambda t: (t[0], t[1]))

    # 4. Regroupement en lignes
    lines = []
    current_line = []
    last_y = None
    # seuil dynamique basé sur la médiane de la hauteur des boxes
    heights = [np.linalg.norm(b[0]-b[3]) for b in dt_boxes]
    y_threshold = np.median(heights)*0.6 if heights else 15
    print(f"[DEBUG] y_threshold dynamique = {y_threshold:.1f}")

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

def diff_lines(ref, hyp, out_path):
    """Compare ligne par ligne et écrit un rapport simple des différences."""
    ref_lines = normalize_text(ref).splitlines()
    hyp_lines = normalize_text(hyp).splitlines()
    maxlen = max(len(ref_lines), len(hyp_lines))
    report = []
    for i in range(maxlen):
        gt = ref_lines[i] if i < len(ref_lines) else ""
        pr = hyp_lines[i] if i < len(hyp_lines) else ""
        if gt != pr:
            report.append(f"--- Ligne {i+1} ---\nGT : {gt}\nPR : {pr}\n")
    if report:
        Path(out_path).write_text("\n".join(report), encoding="utf-8")
        print(f"[INFO] Rapport d'écarts écrit dans {out_path}")

# --------------------------
# Main
# --------------------------
if __name__=="__main__":
    det_cfg = "/workspace/config/ch_PP-OCRv4_det_infer.yml"
    det_ckpt = "/workspace/models/ch_PP-OCRv4_det_infer/inference"
    rec_cfg = "/workspace/config/en_PP-OCRv4_rec.yml"

    # Infos supplémentaires
    model_name = "rec_ppocr_v4_1M_en_200K_fr_9_epochs"
    epochs = 9   # à mettre à jour selon ton entraînement

    pages_dir = "/workspace/img"
    json_dir  = "/workspace/anno"
    gt_dir    = "/workspace/gt"

    print(f"[INFO] pages_dir={pages_dir} exists={Path(pages_dir).exists()}")
    print(f"[INFO] json_dir={json_dir} exists={Path(json_dir).exists()}")

    det_model, det_post = load_det_model(det_cfg, det_ckpt)
    rec_model, rec_post = load_rec_model(rec_cfg)
    # rec_model, rec_post = load_rec_infer_model(rec_cfg)
    cfg = load_config(rec_cfg)
    rec_ops = build_eval_ops(cfg)
    print("[DEBUG] eval ops =", [list(op.keys())[0] for op in cfg['Eval']['dataset']['transforms']])
    results_csv = "/workspace/eval/eval_pages.csv"
    Path(os.path.dirname(results_csv)).mkdir(parents=True, exist_ok=True)

    total_cer_paddle, total_wer_paddle, total_cer_tess, total_wer_tess = [], [], [], []
    total_cer_det_paddle, total_wer_det_paddle = [], []

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

        # 1️⃣ Détection Paddle + Reconnaissance Paddle
        pred_det_paddle = ""
        try:
            pred_det_paddle = ocr_page(det_model, det_post, rec_model, rec_post, rec_ops, str(page_file), "paddle")
        except Exception as e:
            print(f"[WARN] échec OCR Paddle sur {page_file.name}: {e}")

        # 2️⃣ Détection Paddle + Tesseract
        pred_det_tess = ""
        try:
            pred_det_tess = ocr_page(det_model, det_post, rec_model, rec_post, rec_ops, str(page_file), "tesseract")
        except Exception as e:
            print(f"[WARN] échec Det+Tess sur {page_file.name}: {e}")

        # 3️⃣ Tesseract (page entière)
        pred_tess = pytesseract.image_to_string(cv2.imread(str(page_file)), lang="eng").strip()

        # Normalisation
        ref_full = normalize_text(ref_full)
        pred_det_paddle = normalize_text(pred_det_paddle)
        pred_det_tess = normalize_text(pred_det_tess)
        pred_tess = normalize_text(pred_tess)

        # Scores
        cer_det_paddle = cer(ref_full, pred_det_paddle)
        wer_det_paddle = wer(ref_full, pred_det_paddle)
        cer_det_tess = cer(ref_full, pred_det_tess)
        wer_det_tess = wer(ref_full, pred_det_tess)
        cer_t, wer_t = cer(ref_full, pred_tess), wer(ref_full, pred_tess)

        if cer_det_tess > 0.2 or wer_det_tess > 0.3:
            diff_lines(ref_full, pred_det_tess, f"/workspace/eval/diff_{page_file.stem}.txt")

        total_cer_det_paddle.append(cer_det_paddle)
        total_wer_det_paddle.append(wer_det_paddle)
        total_cer_paddle.append(cer_det_tess)
        total_wer_paddle.append(wer_det_tess)
        total_cer_tess.append(cer_t)
        total_wer_tess.append(wer_t)
        print(f"[INFO] cer_det_paddle {cer_det_paddle} wer_det_paddle {wer_det_paddle}")
        print(f"[INFO] cer_det_tess {cer_det_tess} wer_det_tess {wer_det_tess}")
        print(f"[INFO] cer_tess {cer_t} wer_tess {wer_t}")

        count += 1
        if count >= 10:
            break

    mean_cer_det_paddle = sum(total_cer_det_paddle) / len(total_cer_det_paddle) if total_cer_det_paddle else 1.0
    mean_wer_det_paddle = sum(total_wer_det_paddle) / len(total_wer_det_paddle) if total_wer_det_paddle else 1.0
    mean_cer_paddle = sum(total_cer_paddle) / len(total_cer_paddle) if total_cer_paddle else 1.0
    mean_wer_paddle = sum(total_wer_paddle) / len(total_wer_paddle) if total_wer_paddle else 1.0
    mean_cer_tess = sum(total_cer_tess) / len(total_cer_tess) if total_cer_tess else 1.0
    mean_wer_tess = sum(total_wer_tess) / len(total_wer_tess) if total_wer_tess else 1.0

    # ⬇️ On ajoute model_name et epochs
    with open(results_csv, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if csvfile.tell() == 0:
            writer.writerow([
                "model_name", "epochs", "nb_pages",
                "mean_cer_det_paddle", "mean_wer_det_paddle",
                "mean_cer_det_tess", "mean_wer_det_tess",
                "mean_cer_tess", "mean_wer_tess"
            ])
        writer.writerow([
            model_name, epochs, count,
            mean_cer_det_paddle, mean_wer_det_paddle,
            mean_cer_paddle, mean_wer_paddle,
            mean_cer_tess, mean_wer_tess
])

    print(f"[OK] Statistiques globales enregistrées dans {results_csv}")

    print(f"[SUMMARY] Model={model_name}, Epochs={epochs}")
    print(f"[SUMMARY] Pages traitées: {count}")
    print("=== Résumé global ===")
    print(f"CER Det+Paddle     : {mean_cer_det_paddle:.3f}")
    print(f"WER Det+Paddle     : {mean_wer_det_paddle:.3f}")
    print(f"CER Det+Tesseract  : {mean_cer_paddle:.3f}")
    print(f"WER Det+Tesseract  : {mean_wer_paddle:.3f}")
    print(f"CER Tesseract      : {mean_cer_tess:.3f}")
    print(f"WER Tesseract      : {mean_wer_tess:.3f}")
    print(f"Détails → {results_csv}")