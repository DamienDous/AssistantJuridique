import json
import difflib
import pytesseract
from pathlib import Path
import re
import spacy
from pdf2image import convert_from_path

# Chargement du modèle spaCy français
nlp = spacy.load("fr_core_news_sm")

def nettoyer_texte(texte):
    texte = texte.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    texte = texte.replace("«", '"').replace("»", '"')
    return re.sub(r"\s+", " ", texte).strip()

def decouper_phrases_spacy(texte):
    doc = nlp(texte)
    return [sent.text.strip() for sent in doc.sents]

def trouver_meilleur_match(cible, phrases, max_concat=4, seuil=0.7):
    cible_norm = nettoyer_texte(cible.lower())
    meilleur, meilleur_score = None, 0
    for i in range(len(phrases)):
        for j in range(i + 1, min(i + max_concat + 1, len(phrases))):
            concat = " ".join(phrases[i:j])
            score = difflib.SequenceMatcher(None, cible_norm, nettoyer_texte(concat.lower())).ratio()
            if score > meilleur_score:
                meilleur, meilleur_score = concat, score
            if score == 1.0:
                return concat, 1.0
    if meilleur_score >= seuil:
        return meilleur, meilleur_score
    return None, meilleur_score

def chercher_sous_phrase(cible, phrases):
    cible_norm = nettoyer_texte(cible.lower())
    for phrase in phrases:
        if nettoyer_texte(phrase.lower()) in cible_norm:
            return phrase
    return None

def extraire_texte_ocr(pdf_file):
    print(f"🛠 OCR de {pdf_file.name}")
    contenu = ""
    images = convert_from_path(str(pdf_file))
    for image in images:
        contenu += pytesseract.image_to_string(image, lang="fra") + "\n"
    print("✅ OCR terminé.")
    return contenu

def construire_datasets_par_json(pdf_folder, json_folder, output_folder):
    output_folder.mkdir(parents=True, exist_ok=True)

    for json_file in json_folder.glob("*.json"):
        pdf_file = pdf_folder / (json_file.stem + ".pdf")
        if not pdf_file.exists():
            print(f"⚠️ PDF manquant pour : {json_file.name}")
            continue

        print(f"🔍 Traitement : {json_file.name} + {pdf_file.name}")

        output_jsonl = output_folder / f"{json_file.stem}_mistral_training.jsonl"

        try:
            texte_ocr = extraire_texte_ocr(pdf_file)
            phrases_ocr = decouper_phrases_spacy(nettoyer_texte(texte_ocr))

            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)

            with open(output_jsonl, "w", encoding="utf-8") as out:
                for section in ["Faits", "Problématique", "Règles", "Analyse", "Solution"]:
                    contenu = data.get(section, [])
                    if isinstance(contenu, str):
                        contenu = [contenu]
                    for phrase in contenu:
                        match, score = trouver_meilleur_match(phrase, phrases_ocr)
                        if match:
                            out.write(json.dumps({"phrase": match, "label": section, "source": "match"}, ensure_ascii=False) + "\n")
                        else:
                            sous_phrase = chercher_sous_phrase(phrase, phrases_ocr)
                            if sous_phrase:
                                out.write(json.dumps({"phrase": sous_phrase, "label": section, "source": "submatch"}, ensure_ascii=False) + "\n")
                            else:
                                out.write(json.dumps({"phrase": phrase, "label": "Autre", "source": "original"}, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"❌ Erreur avec {json_file.name} : {e}")

        print(f"✅ Fichier exporté : {output_jsonl}")

if __name__ == "__main__":
    pdf_folder = Path("./json_processor/pdf")
    json_folder = Path("./json_processor/json")
    output_folder = Path("./json_processor/json_out")

    construire_datasets_par_json(pdf_folder, json_folder, output_folder)
