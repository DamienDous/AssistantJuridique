import json
import difflib
import pytesseract
from PIL import Image
import fitz  # PyMuPDF
import io
from pathlib import Path
import subprocess

def find_closest_match(target, corpus, threshold=0.90):
	match = difflib.get_close_matches(target, corpus, n=1, cutoff=threshold)
	return match[0] if match else None

def nettoyer_json(json_file, pdf_file, output_file=None):
	with open(json_file, "r", encoding="utf-8") as f:
		original = json.load(f)

	txt_path = "/DB/mon_fichier.txt"

	subprocess.run(
		["pdftotext", "-layout", str(pdf_file), str(txt_path)], 
		check=True)

	ocr_sentences = ""
	with open(txt_path, "r", encoding="utf-8") as f:
		ocr_sentences = f.read()
	ocr_sentences = ocr_sentences.replace("\n", " ").split(".") 

	cleaned = {}
	for section in ["Faits", "Problématique", "Règles", "Analyse", "Solution"]:
		data = original.get(section)
		if isinstance(data, list):
			cleaned[section] = [match for phrase in data if (match := find_closest_match(phrase, ocr_sentences))]
		elif isinstance(data, str):
			match = find_closest_match(data, ocr_sentences)
			cleaned[section] = match if match else ""
		else:
			cleaned[section] = data

	if not output_file:
		output_file = Path(json_file).with_stem(Path(json_file).stem + "_nettoye")

	with open(output_file, "w", encoding="utf-8") as f:
		json.dump(cleaned, f, indent=2, ensure_ascii=False)

	print(f"✅ JSON nettoyé enregistré dans : {output_file}")

if __name__ == "__main__":
    dossier = "/DB"  # 🔁 à adapter selon ton arborescence
    dossier_path = Path(dossier)
    json_files = list(dossier_path.glob("*.json"))

    for json_file in json_files:
        pdf_file = json_file.with_suffix(".pdf")
        if pdf_file.exists():
            print(f"🔍 Traitement : {json_file.name} + {pdf_file.name}")
            try:
                nettoyer_json(json_file, pdf_file)
            except Exception as e:
                print(f"❌ Erreur pour {json_file.name} : {e}")
        else:
            print(f"⚠️ PDF manquant pour : {json_file.name}")