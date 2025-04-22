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

INPUT_PDF_DIR = BASE_DIR / "evaluation/input_pdf"
REFERENCE_TXT_DIR = BASE_DIR / "evaluation/reference_txt"
LOG_DIR = BASE_DIR / "evaluation/logs"
TEMP_DIR = BASE_DIR / "processed_files/temp_evaluation"
SCRIPT_PATH = BASE_DIR / "pipelines/pipeline_base/pipeline_reconnaissance_text_pdf.sh"

# 📊 Fonctions d'évaluation
def punctuation_accuracy(ref, pred):
    import string
    ref_punct = ''.join([c for c in ref if c in string.punctuation])
    pred_punct = ''.join([c for c in pred if c in string.punctuation])
    return difflib.SequenceMatcher(None, ref_punct, pred_punct).ratio()

def evaluate_file(reference_path, generated_path):
    with open(reference_path, "r", encoding="utf-8") as f:
        ref_text = f.read()
    with open(generated_path, "r", encoding="utf-8") as f:
        gen_text = f.read()

    score_lev = levenshtein_distance(ref_text, gen_text) / max(len(ref_text), 1)
    score_wer = wer(ref_text, gen_text)
    score_punct = punctuation_accuracy(ref_text, gen_text)

    return {
        "filename": reference_path.name,
        "levenshtein": score_lev,
        "wer": score_wer,
        "punctuation": score_punct
    }

# 🚀 Main script
def main():
    print("Répertoire courant :", os.getcwd())
    print("📂 Lancement du script :", SCRIPT_PATH)
    print("📄 Existe :", SCRIPT_PATH.exists())
    print("🛠️  Est exécutable :", os.access(SCRIPT_PATH, os.X_OK))

    # Création automatique des répertoires nécessaires
    (INPUT_PDF_DIR).mkdir(parents=True, exist_ok=True)
    (REFERENCE_TXT_DIR).mkdir(parents=True, exist_ok=True)
    (LOG_DIR).mkdir(parents=True, exist_ok=True)
    (TEMP_DIR).mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "processed_files").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "results").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "docs").mkdir(parents=True, exist_ok=True)

    LOG_DIR.mkdir(exist_ok=True)
    TEMP_DIR.mkdir(exist_ok=True)
    REFERENCE_TXT_DIR.mkdir(exist_ok=True)

    results = []

    for pdf_path in sorted(INPUT_PDF_DIR.glob("*.pdf")):
        pdf_name = pdf_path.stem
        workdir = TEMP_DIR / pdf_name
        output_txt = workdir / f"{pdf_name}_traitement" / f"{pdf_name}_txt_corrige" / f"{pdf_name}.txt"
        ref_txt = REFERENCE_TXT_DIR / f"{pdf_name}.txt"

        print(f"▶️ Traitement de {pdf_name}...")

        # ✅ Appel de bash avec chemin absolu
        subprocess.run(["bash", str(SCRIPT_PATH.resolve()), str(pdf_path), str(workdir)], check=True)

        if output_txt.exists() and ref_txt.exists():
            metrics = evaluate_file(ref_txt, output_txt)
            results.append(metrics)
        else:
            print(f"⚠️ Fichier manquant pour comparaison : {pdf_name}")

    df = pd.DataFrame(results)
    if not df.empty:
        df["score_global"] = 1 - (df["levenshtein"] + df["wer"]) / 2
        df.to_csv(LOG_DIR / "scores_from_pdf.csv", index=False)
        print(df)
    else:
        print("❌ Aucun résultat à évaluer : vérifie les fichiers de sortie et de référence.")
        print(df)

if __name__ == "__main__":
    main()
