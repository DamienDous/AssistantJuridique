import spacy
import re
from pathlib import Path
from collections import deque

nlp = spacy.load("fr_core_news_sm")

INDICES_LEXICAUX = [
    r"\b(etude du cas|cas pratique|exemple)\b",
    r"\b(Monsieur|Madame|M\.|Mme)\s+[A-ZÉÈÀ][a-z]+\b",
    r"\b(loué|fonds|location-gérance|commerce|immeuble)\b"
]

def nettoyer_texte(texte):
    texte = re.sub(r"[’‘]", "'", texte)
    texte = re.sub(r'[“”«»]', '"', texte)
    texte = re.sub(r"\s+", " ", texte)
    return texte.strip()

def phrase_a_indices(phrase):
    texte = phrase.text.lower()
    return any(re.search(motif, texte) for motif in INDICES_LEXICAUX)

def nouvelles_entites_personnes(phrase, entites_courantes):
    personnes = set(ent.text for ent in phrase.ents if ent.label_ == "PER")
    nouvelles = personnes - entites_courantes
    return nouvelles, personnes

def segmenter_texte_avance(texte, taille_bloc_min=5, taille_bloc_max=10, seuil_changement=2, overlap=2):
    doc = nlp(texte)
    phrases = list(doc.sents)
    segments, bloc_courant = [], []
    entites_courantes = set()

    i = 0
    while i < len(phrases):
        bloc = phrases[i:i+taille_bloc_max]
        changement_score = 0

        # Compter indices lexicaux dans le bloc
        indices_lexicaux_bloc = sum(phrase_a_indices(p) for p in bloc)

        # Compter nouvelles entités
        nouvelles_personnes, personnes_bloc = set(), set()
        for phrase in bloc:
            nouvelles, personnes = nouvelles_entites_personnes(phrase, entites_courantes)
            nouvelles_personnes |= nouvelles
            personnes_bloc |= personnes

        changement_score += bool(nouvelles_personnes)
        changement_score += indices_lexicaux_bloc >= 2

        # Déclenchement de la segmentation
        if len(bloc_courant) >= taille_bloc_min and changement_score >= seuil_changement:
            # Sauvegarde avec overlap
            segments.append(" ".join(bloc_courant + [p.text for p in bloc[:overlap]]).strip())
            bloc_courant = [p.text for p in bloc[-overlap:]]
            entites_courantes = personnes_bloc
            i += taille_bloc_max - overlap
        else:
            bloc_courant.extend(p.text for p in bloc)
            entites_courantes |= personnes_bloc
            i += taille_bloc_max

    if bloc_courant:
        segments.append(" ".join(bloc_courant).strip())

    return segments

def segmenter_fichier(input_path, output_dir):
    output_dir.mkdir(exist_ok=True, parents=True)
    texte = nettoyer_texte(Path(input_path).read_text(encoding="utf-8"))
    segments = segmenter_texte_avance(texte)

    for idx, segment in enumerate(segments, 1):
        fichier_sortie = output_dir / f"{input_path.stem}_segment_{idx}.txt"
        fichier_sortie.write_text(segment, encoding="utf-8")
        print(f"✅ Segment {idx} enregistré : {fichier_sortie}")

# Exécution
if __name__ == "__main__":
    input_file = Path("./json_processor/pdf_test/ecole-nationale-de-commerce-et-de-gestion-settat-droit-commercial-cas-pratique-1-droit-commercial-s4-27-avril-2022.ocr.txt")
    output_dir = Path("./json_processor/cas_sep")
    segmenter_fichier(input_file, output_dir)
