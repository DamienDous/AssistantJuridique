#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fusionne plusieurs crops courts pour créer des "lignes longues" artificielles
compatibles avec PaddleOCR (max 100 caractères environ).
"""

import os
import random
import csv

# === paramètres ===
IN_LIST = "train_list.txt"         # ton fichier d'entrée
OUT_LONG = "train_list_long.txt"   # fichier avec crops longs
OUT_MIXED = "train_list_mixed.txt" # short + long
MAX_CHARS = 100                    # longueur max par ligne
MIN_LEN_SHORT = 3                  # seuil pour considérer un crop "court"
MAX_SHORT_GROUP = 5                # nb max de crops à fusionner

random.seed(42)

# === lecture du fichier d'entrée ===
pairs = []
with open(IN_LIST, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or "\t" not in line:
            continue
        img, text = line.split("\t", 1)
        text = text.strip()
        if text:
            pairs.append((img, text))

print(f"[INFO] {len(pairs)} lignes chargées depuis {IN_LIST}")

# === séparation des crops courts / longs ===
shorts = [(img, txt) for img, txt in pairs if len(txt) <= 15]
longs = [(img, txt) for img, txt in pairs if len(txt) > 15]

print(f"[INFO] Courts: {len(shorts)} | Longs: {len(longs)}")

# === création de nouvelles lignes longues ===
fused = []
i = 0
while i < len(shorts):
    nb = random.randint(2, MAX_SHORT_GROUP)
    group = shorts[i:i + nb]
    i += nb
    concat_text = " ".join(txt for _, txt in group).strip()
    if len(concat_text) < 10 or len(concat_text) > MAX_CHARS:
        continue
    # l'image peut être une concat virtuelle → on garde le chemin du premier
    fused.append((group[0][0], concat_text))

print(f"[INFO] {len(fused)} nouvelles lignes longues créées artificiellement")

# === écriture des fichiers de sortie ===
with open(OUT_LONG, "w", encoding="utf-8", newline="") as f:
    for img, txt in fused:
        f.write(f"{img}\t{txt}\n")

with open(OUT_MIXED, "w", encoding="utf-8", newline="") as f:
    # 80 % dataset original + 20 % crops longs synthétiques
    keep = random.sample(pairs, int(len(pairs) * 0.8))
    combined = keep + fused
    random.shuffle(combined)
    for img, txt in combined:
        f.write(f"{img}\t{txt}\n")

print(f"[OK] {OUT_LONG} ({len(fused)} lignes)")
print(f"[OK] {OUT_MIXED} (mix total {len(combined)} lignes)")
