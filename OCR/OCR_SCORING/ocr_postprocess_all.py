import sys
import re
import requests
from collections import Counter
from spellchecker import SpellChecker
from pathlib import Path
import os

# 1. Chargement d'un dictionnaire CSV externe pour le mapping OCR
def load_mapping_from_csv(csv_path="ocr_mapping.csv"):
    mapping = []
    if Path(csv_path).is_file():
        with open(csv_path, encoding="utf-8") as f:
            for line in f:
                if ',' in line:
                    src, tgt = line.strip().split(',', 1)
                    mapping.append((src, tgt))
    return mapping

# 2. Nettoyage typographique rapide
def correct_typo(text):
    rules = [
        (r"[’‘]", "'"),
        (r'[“”«»]', '"'),
        (r'…', '...'),
        (r'–|—', '-'),
        (r'\boe\b', 'œ'),
        (r'\s+', ' '),
    ]
    for pattern, repl in rules:
        text = re.sub(pattern, repl, text)
    return text.strip()

# 3. Mapping OCR courant (CSV + interne)
DEFAULT_OCR_MAPPING = [
    (r"\ba'est\b", "c'est"),
    (r"\baride\b", "article"),
    (r"\bun'a\b", "n'a"),
    (r"\bmaïs\b", "mais"),
    (r"\ba'agir\b", "s'agit"),
    (r"\bde'à\b", "de à"),
    (r"\bpeureux\b", "Peureux"),
    (r"\bRERREEREEMEE\b", "ERREUR"),
    (r"\bsafran, graisse\b", "exemple"),
    (r"\bje peureux\b", "je peux"),
    (r"\ba'il\b", "s'il"),
    (r"\ba'est-à-dire\b", "c'est-à-dire"),
]
def apply_ocr_mapping(text, custom_mapping=None):
    mapping = DEFAULT_OCR_MAPPING.copy()
    if custom_mapping:
        mapping.extend(custom_mapping)
    for pattern, repl in mapping:
        text = re.sub(pattern, repl, text)
    return text

# 4. Bruit contextuel massif (menus, pubs, emails, HTML, signatures, @, etc.)
BRUIT_PATTERNS = [
    r"^accéder au cours",
    r"^recommandé pour toi",
    r"^plus de :",
    r"^document[ :]",
    r"^tableau comparatif",
    r"^exercices > séance",
    r"^fiche d'arrêt",
    r"^résumé poétique",
    r"^contact & aide",
    r"^questions-?cours",
    r"^offres d'emplois",
    r"^mentions légales",
    r"^politique de confidentialité",
    r"@studocu",
    r"^(\d{1,2}%|\d{1,2} \%)$",
    r"^=+$",  # lignes de = seulement
    r"^\s*-+\s*$",  # lignes de tirets seuls
]
BRUIT_REGEX = re.compile("|".join(BRUIT_PATTERNS), re.I)
def purge_bruit(text, dropped_path=None):
    lines = text.splitlines()
    cleaned, dropped = [], []
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        # Plus de 40% de caractères non alpha-numérique = probable bruit
        ratio_alpha = sum(c.isalpha() for c in line_stripped) / (len(line_stripped) + 1e-5)
        if ratio_alpha < 0.45 and len(line_stripped) > 16:
            dropped.append(line_stripped)
            continue
        if len(line_stripped) < 4:
            dropped.append(line_stripped)
            continue
        if BRUIT_REGEX.search(line_stripped):
            dropped.append(line_stripped)
            continue
        cleaned.append(line_stripped)
    print(f"Nombre de lignes après purge_bruit: {len(cleaned)} (supprimées: {len(dropped)})")
    if dropped_path:
        with open(dropped_path, "w", encoding="utf-8") as f:
            for l in dropped:
                f.write(l + "\n")
    return "\n".join(cleaned)


# 5. Clean OCR + doublons + paragraphes bizarres + capitalisation automatique
def clean_ocr_text(text):
    text = re.sub(r'(\w)-\s+(\w)', r'\1\2', text)
    text = re.sub(r'(\s|^)-(\s|$)', ' ', text)
    lines = text.split('\n')
    cleaned = [line.strip() for line in lines if line.strip()]
    text = " ".join(cleaned)
    text = re.sub(r'([.!?])\s+', r"\1\n", text)
    # Capitalise la première lettre après . ! ?
    text = re.sub(r'([.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text)
    paragraphs = text.split('\n')
    unique_paragraphs = []
    seen = set()
    for p in paragraphs:
        p_stripped = p.strip()
        if not p_stripped or p_stripped in seen:
            continue
        chars = len(p_stripped)
        if chars == 0:
            continue
        alphanum = sum(c.isalnum() for c in p_stripped)
        if alphanum / chars < 0.5 and chars > 12:
            continue  # bruit symboles
        if len(p_stripped) < 5:
            continue
        seen.add(p_stripped)
        unique_paragraphs.append(p_stripped)
    print(f"Nombre de paragraphes restants: {len(unique_paragraphs)}")
    return "\n".join(unique_paragraphs)

# 6. Détection mots rares (non stopwords, 1 occurrence)
STOPWORDS = {
    "le", "la", "et", "de", "du", "en", "à", "les", "des", "un", "une", "dans",
    "au", "pour", "par", "sur", "avec", "ou", "se", "ce", "il", "elle", "nous", "vous", "je", "tu", "ils", "elles",
    "son", "sa", "ses", "leur", "leurs", "plus", "a", "est", "que", "qui", "ne", "pas", "mais", "comme", "aussi"
}
def detect_rare_words(text, min_count=2, stopwords=STOPWORDS):
    words = re.findall(r"\w+", text.lower())
    freq = Counter(words)
    rare = {w for w, c in freq.items() if c < min_count and w not in stopwords}
    print(f"Rare words trouvés: {sorted(rare)}")
    return rare

# 7. Correction ortho simple (remplace par LanguageTool si possible)
def full_spellcheck(text, rare_words_only=False, rare_words_set=None):
    spell = SpellChecker(language='fr')
    def repl(m):
        w = m.group(0)
        if rare_words_only and rare_words_set is not None and w.lower() not in rare_words_set:
            return w
        c = spell.correction(w)
        return c if c and c != w else w
    return re.sub(r'\b\w+\b', repl, text)

# 8. Correction contextuelle LanguageTool + log auto-corrections pour mapping
def correct_with_languagetool(text, api_url="http://localhost:8010/v2/check", language="fr", log_path=None):
    import os
    result_lines = []
    corrections_log = []
    already_logged = set()
    # Charge le fichier de log existant pour ne garder que les corrections inédites
    if log_path and os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                already_logged.add(line.strip())
    for paragraph in text.split('\n'):
        if not paragraph.strip():
            continue
        payload = {
            "text": paragraph,
            "language": language
        }
        try:
            resp = requests.post(api_url, data=payload, timeout=10)
            if resp.status_code == 200:
                res = resp.json()
                corrected = paragraph
                matches = res.get('matches', [])
                # 1. D'abord on log TOUTES les corrections inédites et pertinentes
                for match in matches:
                    if match['replacements']:
                        orig = corrected[match['offset']:match['offset'] + match['length']].strip()
                        replacement = match['replacements'][0]['value'].strip()
                        # Filtre les cas inutiles
                        if not orig or not replacement:
                            continue
                        if orig == replacement:
                            continue
                        if all(c in {'.', ',', ';', ' ', '}', ']', '[', '{', ')', '('} for c in orig):
                            continue
                        if all(c in {'.', ',', ';', ' ', '}', ']', '[', '{', ')', '('} for c in replacement):
                            continue
                        logline = f"{orig.lower()},{replacement.lower()}"
                        if logline not in already_logged:
                            corrections_log.append((orig, replacement))
                            already_logged.add(logline)
                # 2. Puis on applique les suggestions sur le texte (ordre inverse)
                for match in sorted(matches, key=lambda m: m['offset'], reverse=True):
                    if match['replacements']:
                        start = match['offset']
                        end = start + match['length']
                        replacement = match['replacements'][0]['value']
                        corrected = corrected[:start] + replacement + corrected[end:]
                result_lines.append(corrected)
            else:
                result_lines.append(paragraph)
        except Exception as e:
            result_lines.append(paragraph)
    # Toujours append (et pas écraser) les corrections inédites
    if log_path and corrections_log:
        with open(log_path, "a", encoding="utf-8") as f:  # append mode
            for orig, rep in corrections_log:
                f.write(f"{orig},{rep}\n")
    return "\n".join(result_lines)


# 9. Scoring global du fichier (qualité brute)
def compute_text_stats(text):
    chars = len(text)
    words = len(re.findall(r'\w+', text))
    lines = len(text.splitlines())
    alpha = sum(c.isalpha() for c in text)
    print(f"Score: {chars} chars, {words} mots, {lines} lignes, {alpha/chars if chars else 0:.2%} lettres alpha")
    return {"chars": chars, "words": words, "lines": lines, "alpha_ratio": alpha/chars if chars else 0}

def split_long_lines(text, maxlen=800):
    """Découpe les lignes trop longues en phrases pour éviter de tout perdre à l'étape purge."""
    out = []
    for line in text.splitlines():
        l = line.strip()
        if len(l) > maxlen:
            # Découpe sur . ! ? suivis d’espace ou fin de ligne
            out.extend(re.split(r'(?<=[.!?])\s+', l))
        else:
            out.append(l)
    return "\n".join([s for s in out if s.strip()])

# Dédoublonnage global (après tout)
def deduplicate_paragraphs(text):
    lines = text.split('\n')
    seen = set()
    result = []
    for l in lines:
        s = l.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        result.append(s)
    return "\n".join(result)

# 10. Main workflow
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file")
    parser.add_argument("output_file")
    parser.add_argument("--only_rare", action="store_true")
    parser.add_argument("--languagetool", action="store_true")
    parser.add_argument("--mapping", default="/data/out/ocr_mapping.csv")
    parser.add_argument("--log_corrections", default="/data/out/corrections_languagetool.csv")
    parser.add_argument("--dropped_lines", default="/data/out/dropped_lines.txt")
    args = parser.parse_args()

    print(f"Lecture fichier : {args.input_file}")
    with open(args.input_file, encoding="utf-8") as f:
        text = f.read()
    compute_text_stats(text)

    text = correct_typo(text)
    custom_mapping = load_mapping_from_csv(args.mapping)
    text = apply_ocr_mapping(text, custom_mapping)
    text = split_long_lines(text, maxlen=1000)  # NOUVEAU !
    lines = text.splitlines()
    for i, line in enumerate(lines[:10]):  # log que les 10 premières pour debug rapide
        print(f"Ligne {i} : {len(line)} caractères : {repr(line[:100])}")

    text = purge_bruit(text, dropped_path=args.dropped_lines)
    compute_text_stats(text)

    text = clean_ocr_text(text)
    compute_text_stats(text)

    rare = detect_rare_words(text)
    with open(args.output_file.replace('.txt', '_rare.txt'), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(rare)))

    if args.languagetool:
        print("→ Correction contextuelle LanguageTool...")
        text_corr = correct_with_languagetool(text, log_path=args.log_corrections)
    else:
        text_corr = full_spellcheck(text, rare_words_only=args.only_rare, rare_words_set=rare if args.only_rare else None)

    text_corr = deduplicate_paragraphs(text_corr)

    compute_text_stats(text_corr)
    with open(args.output_file, "w", encoding="utf-8") as f:
        f.write(text_corr)

    print("=== Echantillon du texte nettoyé :")
    print(text_corr[:800])
    print(f"✅ Fichier propre : {args.output_file}")
    print(f"({len(rare)} mots rares enregistrés dans {args.output_file.replace('.txt', '_rare.txt')})")

    # Log warning si texte final très court (piège de purge trop agressive)
    if len(text_corr) < 800:
        print("⚠️ Texte final très court, vérifie la configuration des motifs de bruit !")

if __name__ == "__main__":
    main()
