#!/usr/bin/env python3
import os, glob, csv, re, sys
from jiwer import wer, cer
from collections import Counter

def get_stats(text):
    nb_mots = len(re.findall(r'\w+', text))
    nb_paragraphes = len([p for p in text.split('\n\n') if p.strip()])
    nb_maj = len(re.findall(r'[A-ZÉÈÀÙÂÊÎÔÛÇ]', text))
    nb_points = text.count('.')
    nb_exclam = text.count('!')
    nb_quest = text.count('?')
    nb_punct = nb_points + nb_exclam + nb_quest
    ratio_punct = nb_punct / nb_mots if nb_mots > 0 else 0
    return nb_mots, nb_paragraphes, nb_maj, nb_points, nb_exclam, nb_quest, ratio_punct

def jaccard_words(a, b):
    set_a = set(re.findall(r'\w+', a.lower()))
    set_b = set(re.findall(r'\w+', b.lower()))
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union else 1.0

def jaccard_multiset(a, b):
    ca = Counter(re.findall(r'\w+', a.lower()))
    cb = Counter(re.findall(r'\w+', b.lower()))
    inter = sum((ca & cb).values())
    union = sum((ca | cb).values())
    return inter / union if union else 1.0

# Entrées
ocr_path = sys.argv[1]  # Fichier OCR
ref_path = sys.argv[2]  # Fichier de référence
cat_path = sys.argv[3]  # Fichier de référence
base = os.path.basename(ocr_path)

# Chargement des textes
with open(ocr_path, encoding="utf-8") as f:
    ocr = f.read().strip()
with open(ref_path, encoding="utf-8") as f:
    ref = f.read().strip()
with open(cat_path, encoding="utf-8") as f:
    cat = f.read().strip()

# WER/CER
w = wer(ref, ocr)
c = cer(ref, ocr)
# Jaccard bag-of-words
jacc = jaccard_words(ref, ocr)
jacc_multi = jaccard_multiset(ref, ocr)
# Structure
stats_ocr = get_stats(ocr)
stats_ref = get_stats(ref)
ratios = [ (stats_ocr[i]/stats_ref[i] if stats_ref[i] else 0) for i in range(len(stats_ref)) ]
delta_punct = stats_ocr[-1] - stats_ref[-1]
# Score global simple (à adapter à ton goût)
# Ici : moyenne de (1-WER), (1-CER), ratio_mots, ratio_paragraphes, ratio_maj, ratio_points, ratio_exclam, ratio_quest, (1-abs(delta_punct))
# Tu peux pondérer selon ce qui te paraît important !
composantes = [
    max(0, 1-w),     # plus WER bas, mieux c’est
    max(0, 1-c),     # plus CER bas, mieux c’est
    min(ratios[0], 1/ratios[0]) if ratios[0] else 0, # ratio mots (symétrique)
    min(ratios[1], 1/ratios[1]) if ratios[1] else 0, # ratio paragraphes
    min(ratios[2], 1/ratios[2]) if ratios[2] else 0, # ratio maj
    min(ratios[3], 1/ratios[3]) if ratios[3] else 0, # ratio points
    min(ratios[4], 1/ratios[4]) if ratios[4] else 0, # ratio exclam
    min(ratios[5], 1/ratios[5]) if ratios[5] else 0, # ratio quest
    max(0, 1-abs(delta_punct)), # plus delta petit, mieux c’est
]
# # Score moyen (à adapter/pondérer)
# score_global = sum(composantes)/len(composantes)

# print(
#     f"{base},{w:.4f},{c:.4f},{jacc:.4f},{jacc_multi:.4f},"
#     f"{stats_ref[0]},{stats_ocr[0]},{ratios[0]},"
#     f"{stats_ref[1]},{stats_ocr[1]},{ratios[1]},"
#     f"{stats_ref[2]},{stats_ocr[2]},{ratios[2]},"
#     f"{stats_ref[3]},{stats_ocr[3]},{ratios[3]},"
#     f"{stats_ref[4]},{stats_ocr[4]},{ratios[4]},"
#     f"{stats_ref[5]},{stats_ocr[5]},{ratios[5]},"
#     f"{stats_ref[6]},{stats_ocr[6]},{ratios[6]},"
#     f"{score_global}"
# )

ratios_mean = sum(composantes[2:7])/len(composantes[2:7])
print(
    f"{base},{cat},{c:.2f},{jacc_multi:.2f},{ratios_mean:.2f}"
)
