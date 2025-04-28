#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, json, sys

# Usage: structure_juridique.py clean.txt result.json
txt = open(sys.argv[1], encoding='utf-8').read()

# 1) Extraire n° de dossier
num = re.search(r'Permis de construire n[°º]?\s*([0-9A-Z]+)', txt, re.I)
numero = num.group(1) if num else ""

# 2) Extraire date (JJ mois AAAA)
date = ""
m = re.search(r'(\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4})', txt, re.I)
if m:
    # transformer en ISO
    import locale, datetime
    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
    date_obj = datetime.datetime.strptime(m.group(1), '%d %B %Y')
    date = date_obj.date().isoformat()

# 3) Découper sections par titres
sections = {}
for titre in ('Faits', 'Procédure', 'Dispositif', 'Motifs', 'Discussion'):
    pat = re.compile(rf'{titre}\s*\n', re.I)
    parts = pat.split(txt)
    if len(parts)>=2:
        # texte après le titre jusqu’au prochain titre ou fin
        reste = re.split(r'^(?:'+'|'.join(sections.keys())+r')\s*$', parts[1], flags=re.M|re.I)[0]
        sections[titre.lower()] = reste.strip()

# 4) Tout le texte
sections['texte_integral'] = txt.strip()
sections['numero'] = numero
sections['date'] = date

json.dump(sections, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f"✅ Structuration JSON générée : {sys.argv[2]}")
