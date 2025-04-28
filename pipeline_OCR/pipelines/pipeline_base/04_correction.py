# -*- coding: utf-8 -*-
from pathlib import Path
import os
import re
import language_tool_python

def corriger_texte(texte, tool, lexique):
    # Découper en phrases pour éviter les blocages
    phrases = re.split(r'(?<=[.!?])\s+', texte)
    result = ""
    # Préparer le pattern du lexique (OR de tous les termes)
    pattern = None
    if lexique:
        pattern = re.compile(
            r'\b(' + '|'.join(map(re.escape, lexique)) + r')\b',
            flags=re.IGNORECASE
        )

    for phrase in phrases:
        phrase = phrase.strip()
        if not phrase:
            continue

        # 1) Corrections LanguageTool
        matches = tool.check(phrase)
        corr = language_tool_python.utils.correct(phrase, matches)

        # 2) Application du lexique métier
        if pattern:
            def repl(m):
                # On retrouve le terme "canonique" dans lexique
                return next(orig for orig in lexique if orig.lower() == m.group(0).lower())
            corr = pattern.sub(repl, corr)

        result += corr + " "

    return result.strip()

def main():
    workdir = os.environ.get("WORKDIR")
    if not workdir:
        print("❌ Erreur : la variable WORKDIR n'est pas définie.")
        exit(1)

    # trouver le dossier *_txt
    text_dir = None
    for root, dirs, _ in os.walk(workdir):
        for d in dirs:
            if d.endswith("_txt") and not d.endswith("_txt_corrige"):
                text_dir = os.path.join(root, d)
                break
        if text_dir:
            break

    if not text_dir:
        print(f"❌ Aucun dossier '*_txt' trouvé sous {workdir}")
        exit(1)

    target_dir = text_dir.replace("_txt", "_txt_corrige")
    os.makedirs(target_dir, exist_ok=True)

    tool = language_tool_python.LanguageTool("fr")

    # Chargement du lexique métier (un terme par ligne, en minuscules)
    lexique = []
    lexique_path = '/app/dico_juridique.txt'
    if os.path.exists(lexique_path):
        with open(lexique_path, encoding='utf-8') as f:
            lexique = [l.strip() for l in f if l.strip()]

    # Traiter chaque .txt
    for filename in os.listdir(text_dir):
        if not filename.endswith(".txt"):
            continue
        input_path = os.path.join(text_dir, filename)
        output_path = os.path.join(target_dir, filename)

        with open(input_path, "r", encoding="utf-8", errors="ignore") as fin:
            raw = fin.read()

        corrected = corriger_texte(raw, tool, lexique)

        with open(output_path, "w", encoding="utf-8") as fout:
            fout.write(corrected)

        print(f"✅ Corrigé : {output_path}")

if __name__ == "__main__":
    main()
