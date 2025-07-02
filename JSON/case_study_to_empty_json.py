import re
import json
from pathlib import Path
from pdf2image import convert_from_path
import pytesseract

def extraire_texte_ocr(pdf_file):
    print(f"🛠 OCR de {pdf_file.name}")
    contenu = ""
    try:
        images = convert_from_path(str(pdf_file))
        for image in images:
            contenu += pytesseract.image_to_string(image, lang="fra") + "\n"
        print("✅ OCR terminé.")
    except Exception as e:
        print(f"❌ Erreur OCR sur {pdf_file.name}: {e}")
    return contenu

def decouper_phrases(text):
    # Nettoyage de base : remplacer \r, multiples \n en 2 \n
    text = text.replace('\r', '')
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Fusionner les lignes cassées par OCR (phrase qui continue à la ligne)
    text = re.sub(r'([^\n])\n([^\n])', r'\1 \2', text)
    # Séparer sur les doubles retours à la ligne (nouveau paragraphe)
    blocs = re.split(r'\n{2,}', text)
    phrases = []
    for bloc in blocs:
        # Découpe sur fin de phrase classique
        split_phrases = re.split(r'(?<=[.?!])\s+', bloc.strip())
        for ph in split_phrases:
            if ph.strip():
                phrases.append(ph.strip())
    return phrases

# Chemins des dossiers
input_dir = Path("json_processor/pdf")
output_dir = Path("json_processor/json_to_classify")
output_dir.mkdir(exist_ok=True)

for input_pdf in input_dir.glob("*.pdf"):
    texte = extraire_texte_ocr(input_pdf)
    if not texte.strip():
        print(f"⚠️ Pas de texte extrait pour {input_pdf.name}, on saute.")
        continue
    phrases = decouper_phrases(texte)
    data = [{"phrase": p, "label": ""} for p in phrases]
    output_json = output_dir / (input_pdf.stem + ".json")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ {len(phrases)} phrases extraites de {input_pdf.name} → {output_json.name}")

print("Traitement terminé !")
