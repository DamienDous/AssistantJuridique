#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, os, subprocess, re, csv, time, json, hashlib, yaml
from pathlib import Path
import cv2, pytesseract, Levenshtein

# -------------------
# Utils
# -------------------
def run_eval(config, checkpoint, dict_path, val_file):
    """Lance tools/eval.py et retourne acc, norm_edit_dis"""
    cmd = [
        "python3", "tools/eval.py",
        "-c", config,
        "-o", f"Global.pretrained_model={checkpoint}",
        "-o", f"Global.character_dict_path={dict_path}",
        "-o", f"Eval.dataset.label_file_list=[\"{val_file}\"]",
        "-o", "Global.use_space_char=True"
    ]
    print("▶ Run:", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = proc.stdout + proc.stderr
    print(stdout)

    acc, ned = None, None
    for line in stdout.splitlines():
        if "acc:" in line and acc is None:
            m = re.search(r"acc:\s*([\d\.]+)", line)
            if m: acc = float(m.group(1))
        if "norm_edit_dis:" in line and ned is None:
            m = re.search(r"norm_edit_dis:\s*([\d\.]+)", line)
            if m: ned = float(m.group(1))
    return acc, ned

def cer(ref, hyp):
    return Levenshtein.distance(ref, hyp) / max(1, len(ref))

def wer(ref, hyp):
    return Levenshtein.distance(" ".join(ref.split()), " ".join(hyp.split())) / max(1, len(ref.split()))

def eval_tesseract(val_file, base):
    scores = {"cer": [], "wer": []}
    with open(val_file, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t", 1)
            if len(parts) < 2:
                continue
            rel, ref = parts
            img = os.path.join(base, rel)
            img_cv = cv2.imread(img)
            if img_cv is None: 
                continue
            hyp = pytesseract.image_to_string(img_cv, lang="eng").strip()
            scores["cer"].append(cer(ref, hyp))
            scores["wer"].append(wer(ref, hyp))
    return {k: sum(v)/len(v) if v else 1.0 for k,v in scores.items()}

# -------------------
# Main
# -------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="config multihead.yml")
    ap.add_argument("--checkpoint", required=True, help="checkpoint (ex: ./output/.../latest)")
    ap.add_argument("--dict", required=True, help="latin_dict.txt")
    ap.add_argument("--val", required=True, help="val.txt")
    ap.add_argument("--base", default="/workspace", help="dataset base dir (pour val.txt)")
    ap.add_argument("--csv", default="/workspace/eval/evaluation_results.csv", help="CSV output")
    args = ap.parse_args()

    # run multihead eval
    acc, ned = run_eval(args.config, args.checkpoint, args.dict, args.val)
    if acc is None or ned is None:
        print("❌ Impossible de parser acc/norm_edit_dis")
        return

    # parse config hash
    yml_hash = hashlib.md5(open(args.config, "r", encoding="utf-8").read().encode()).hexdigest()
    with open(args.config, "r", encoding="utf-8") as f:
        yml_content = yaml.safe_load(f)
    cfg_selected = {
        "Global": yml_content.get("Global", {}),
        "Train": yml_content.get("Train", {}),
        "Eval": yml_content.get("Eval", {}),
        "Optimizer": yml_content.get("Optimizer", {}),
        "Architecture": yml_content.get("Architecture", {}),
    }
    config_str = json.dumps(cfg_selected, ensure_ascii=False)

    # Tesseract baseline
    res_tess = eval_tesseract(args.val, args.base)

    # CSV
    header = ["date","yaml_hash","ocr","acc","norm_edit_dis","cer","wer","checkpoint","val_file","config"]
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    rows = [
        [now, yml_hash, "paddle_multihead", acc, ned, "", "", args.checkpoint, args.val, config_str],
        [now, yml_hash, "tesseract", "", "", res_tess["cer"], res_tess["wer"], "builtin", args.val, ""]
    ]

    Path(os.path.dirname(args.csv)).mkdir(parents=True, exist_ok=True)
    write_header = not os.path.exists(args.csv)
    with open(args.csv, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header: w.writerow(header)
        w.writerows(rows)

    print(f"[OK] Résultats multihead (acc/ned) + tesseract (cer/wer) ajoutés à {args.csv}")

if __name__ == "__main__":
    main()
