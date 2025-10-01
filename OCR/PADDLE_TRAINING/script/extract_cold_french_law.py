import spacy
from datasets import load_dataset
from tqdm import tqdm
import random

# Charger modèle français pour découpage en phrases
nlp = spacy.load("fr_core_news_sm")

# Charger dataset COLD French Law
dataset = load_dataset("harvard-lil/cold-french-law", split="train")

TARGET_SIZE = 600_000
sentences = []

print("Extraction en cours...")

for entry in tqdm(dataset):
    text = entry["article_contenu_text"] or ""
    if not text.strip():
        continue
    doc = nlp(text)
    for sent in doc.sents:
        s = sent.text.strip()
        if 20 < len(s) < 300:  # filtres basiques
            sentences.append(s)
    if len(sentences) >= TARGET_SIZE:
        break

random.shuffle(sentences)
sentences = sentences[:TARGET_SIZE]

with open("corpus_juridique_600k.txt", "w", encoding="utf-8") as f:
    for s in sentences:
        f.write(s + "\n")

print(f"✅ Corpus créé avec {len(sentences)} phrases")
