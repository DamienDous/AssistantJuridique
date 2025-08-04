#!/usr/bin/env python3
import os, glob, csv, re, sys
from jiwer import wer, cer

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

# Entrées
ocr_path = sys.argv[1]  # Fichier OCR
ref_path = sys.argv[2]  # Fichier de référence
base = os.path.basename(ocr_path)

# Chargement des textes
with open(ocr_path, encoding="utf-8") as f:
    ocr = f.read().strip()
with open(ref_path, encoding="utf-8") as f:
    ref = f.read().strip()

# WER/CER
w = wer(ref, ocr)
c = cer(ref, ocr)
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
# Score moyen (à adapter/pondérer)
score_global = sum(composantes)/len(composantes)

print(
    f"{base},{w:.4f},{c:.4f},"
    f"{stats_ref[0]},{stats_ocr[0]},{ratios[0]},"
    f"{stats_ref[1]},{stats_ocr[1]},{ratios[1]},"
    f"{stats_ref[2]},{stats_ocr[2]},{ratios[2]},"
    f"{stats_ref[3]},{stats_ocr[3]},{ratios[3]},"
    f"{stats_ref[4]},{stats_ocr[4]},{ratios[4]},"
    f"{stats_ref[5]},{stats_ocr[5]},{ratios[5]},"
    f"{stats_ref[6]},{stats_ocr[6]},{ratios[6]},"
    f"{score_global}"
)
