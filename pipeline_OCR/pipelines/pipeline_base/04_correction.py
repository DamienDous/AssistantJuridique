# -*- coding: utf-8 -*-
import sys
import os
import re
import language_tool_python
import threading

LT_PORTS = [8010, 8011, 8012, 8013, 8014, 8015, 8016, 8017]
_next_port = [0]
_port_lock = threading.Lock()

def get_next_server_url():
    with _port_lock:
        idx = _next_port[0]
        _next_port[0] = (_next_port[0] + 1) % len(LT_PORTS)
    return f"http://localhost:{LT_PORTS[idx]}"

def check_on_next_server(phrase):
    url = get_next_server_url()
    tool = language_tool_python.LanguageTool("fr", remote_server=url)
    matches = tool.check(phrase)
    return language_tool_python.utils.correct(phrase, matches)

def corriger_texte(texte, lexique):
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

        # 1) Corrections LanguageTool (round-robin)
        corr = check_on_next_server(phrase)

        # 2) Application du lexique métier
        if pattern:
            def repl(m):
                # On retrouve le terme "canonique" dans lexique
                return next(orig for orig in lexique if orig.lower() == m.group(0).lower())
            corr = pattern.sub(repl, corr)

        result += corr + " "

    return result.strip()

def main():
    # -->> ICI : on attend 2 arguments <input.txt> <output.txt>
    if len(sys.argv) < 3:
        print("Usage: 04_correction.py <input.txt> <output.txt>")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    # Chargement du lexique métier (un terme par ligne, en minuscules)
    lexique = []
    lexique_path = '/app/dico_juridique.txt'
    if os.path.exists(lexique_path):
        with open(lexique_path, encoding='utf-8') as f:
            lexique = [l.strip() for l in f if l.strip()]

    with open(input_path, "r", encoding="utf-8", errors="ignore") as fin:
        raw = fin.read()

    corrected = corriger_texte(raw, lexique)

    with open(output_path, "w", encoding="utf-8") as fout:
        fout.write(corrected)

    # print(f"✅ Corrigé : {output_path}")

if __name__ == "__main__":
    main()
