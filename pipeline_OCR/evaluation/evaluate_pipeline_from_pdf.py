#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
from pathlib import Path
import pandas as pd
from jiwer import wer
from Levenshtein import distance as levenshtein_distance
import difflib

# 📁 Répertoires
BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PDF_DIR = BASE_DIR / "evaluation" / "input_pdf"
REFERENCE_TXT_DIR = BASE_DIR / "evaluation" / "reference_txt"
LOG_DIR = BASE_DIR / "evaluation" / "logs"
TEMP_DIR = BASE_DIR / "evaluation" / "temp_evaluation"

# 🛠 Scripts du pipeline
PIPELINE_SH = BASE_DIR / "pipeline_OCR" / "pipelines" / "pipeline_base" / "pipeline_reconnaissance_text_pdf.sh"
CLEAN_SH    = BASE_DIR / "clean_text.sh"
CORR_PY     = BASE_DIR / "pipeline_OCR" / "pipelines" / "pipeline_base" / "04_correction.py"

# 📊 Fonctions d'évaluation
def punctuation_accuracy(ref, pred):
    import string
    ref_punct = ''.join([c for c in ref if c in string.punctuation])
    pred_punct = ''.join([c for c in pred if c in string.punctuation])
    return difflib.SequenceMatcher(None, ref_punct, pred_punct).ratio()

def evaluate_file(ref_path, pred_path):
    ref = ref_path.read_text(encoding="utf-8")
    pred = pred_path.read_text(encoding="utf-8")
    score_lev = levenshtein_distance(ref, pred) / max(len(ref), 1)
    score_wer = wer(ref, pred)
    score_punct = punctuation_accuracy(ref, pred)
    return {
        "filename": ref_path.name,
        "levenshtein": score_lev,
        "wer": score_wer,
        "punctuation": score_punct
    }

def main():
    # Prep dirs
    for d in (INPUT_PDF_DIR, REFERENCE_TXT_DIR, LOG_DIR, TEMP_DIR):
        d.mkdir(parents=True, exist_ok=True)

    results = []

    for pdf_path in sorted(INPUT_PDF_DIR.glob("*.pdf")):
        stem = pdf_path.stem
        workdir = TEMP_DIR / stem
        # 1) lancer le pipeline OCR → extraction .txt brut
        print(f"▶️ OCR + extraction pour {stem}")
        subprocess.run([
            "bash", str(PIPELINE_SH),
            str(pdf_path), str(workdir)
        ], check=True)

        # chemins intermediaires
        raw_txt = workdir / f"{stem}_traitement" / f"{stem}.txt"
        clean_txt = workdir / f"{stem}_clean.txt"
        corr_dir  = workdir / f"{stem}_corrige"
        corr_txt  = corr_dir / f"{stem}.txt"

        # 2) nettoyage post-OCR
        print(f"🧹 Nettoyage post-OCR pour {stem}")
        subprocess.run([
            "bash", str(CLEAN_SH),
            str(raw_txt), str(clean_txt)
        ], check=True)

        # 3) correction LanguageTool + dictionnaire
        print(f"🧠 Correction linguistique pour {stem}")
        subprocess.run([
            "python3", str(CORR_PY),
            str(clean_txt), str(corr_dir)
        ], check=True)

        # 4) évaluation si on a bien le ref et la sortie corrigée
        ref_txt = REFERENCE_TXT_DIR / f"{stem}.txt"
        if corr_txt.exists() and ref_txt.exists():
            metrics = evaluate_file(ref_txt, corr_txt)
            results.append(metrics)
        else:
            print(f"⚠️ Fichiers manquants : {corr_txt} ou {ref_txt}")

    # 5) agrégation et rapport
    if results:
        df = pd.DataFrame(results)
        df["score_global"] = 1 - (df["levenshtein"] + df["wer"]) / 2
        out_csv = LOG_DIR / "scores_evaluation.csv"
        df.to_csv(out_csv, index=False)
        print(f"✅ Scores écrits dans {out_csv}")
        print(df)
    else:
        print("❌ Aucune métrique calculée, vérifie les sorties.")

if __name__ == "__main__":
    main()
