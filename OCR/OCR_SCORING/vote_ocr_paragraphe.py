import sys
import re
from difflib import SequenceMatcher

def split_sentences(text):
    # # Simple tokenizer, peut être remplacé par nltk.sent_tokenize
    # return re.split(r'(?<=[.!?])\s+|\n+', text)
    import nltk
    return nltk.sent_tokenize(text, language='french')

def align_pairwise(seq1, seq2, gap_score=-2, match_score=2, mismatch_score=-1, min_ratio=0.8):
    # Needleman-Wunsch modifié pour phrases/strings
    n, m = len(seq1), len(seq2)
    score = [[0] * (m+1) for _ in range(n+1)]
    path = [[None] * (m+1) for _ in range(n+1)]

    # Init
    for i in range(1, n+1):
        score[i][0] = score[i-1][0] + gap_score
        path[i][0] = (i-1, 0)
    for j in range(1, m+1):
        score[0][j] = score[0][j-1] + gap_score
        path[0][j] = (0, j-1)

    # DP
    for i in range(1, n+1):
        for j in range(1, m+1):
            sim = SequenceMatcher(None, seq1[i-1], seq2[j-1]).ratio()
            s = match_score if sim >= min_ratio else mismatch_score
            scores = [
                (score[i-1][j-1] + s, (i-1, j-1)),   # match/mismatch
                (score[i-1][j] + gap_score, (i-1, j)), # gap seq2
                (score[i][j-1] + gap_score, (i, j-1))  # gap seq1
            ]
            score[i][j], path[i][j] = max(scores, key=lambda x: x[0])

    # Traceback
    i, j = n, m
    aligned1, aligned2 = [], []
    while i > 0 or j > 0:
        pi, pj = path[i][j]
        if pi == i-1 and pj == j-1:
            aligned1.append(seq1[i-1])
            aligned2.append(seq2[j-1])
        elif pi == i-1 and pj == j:
            aligned1.append(seq1[i-1])
            aligned2.append('')
        else:
            aligned1.append('')
            aligned2.append(seq2[j-1])
        i, j = pi, pj
    return aligned1[::-1], aligned2[::-1]

def vote_column(columns):
    # columns: liste de versions de la même “phrase” de chaque OCR, gaps = ''
    # Ici: on choisit la version la plus fréquente, ou la moins “bruitée” (peut améliorer)
    texts = [c for c in columns if c and c.strip()]
    if not texts:
        return ''
    # Variante : ici, le plus long (= moins OCRisé), ou vote par correction orthographique
    # Ici: majorité, ou la version la plus "complète"
    from collections import Counter
    most_common, count = Counter(texts).most_common(1)[0]
    return most_common

def align_multiple(texts):
    # textes: liste de listes de phrases
    aligned = texts[0]
    for i in range(1, len(texts)):
        a1, a2 = align_pairwise(aligned, texts[i])
        # Étendre les alignements sur tous les textes précédents
        new_aligned = []
        idx = 0
        for aa, bb in zip(a1, a2):
            # Si on a inséré un gap, il faut le rajouter sur tout le consensus aligné précédent
            if aa == '' and idx < len(aligned):
                # Insérer un gap dans toutes les séquences précédentes
                for j in range(len(new_aligned)):
                    new_aligned[j].append('')
            elif aa != '':
                if idx >= len(new_aligned):
                    # Première fois, crée la colonne
                    new_aligned.append([aa])
                else:
                    new_aligned[idx].append(aa)
                idx += 1
        # On n’utilise ici que la colonne majoritaire (vote)
        aligned = [vote_column(cols) for cols in zip(a1, a2)]
    return aligned

def remove_substring_duplicates(phrases, min_overlap_ratio=0.7):
    result = []
    for i, phr in enumerate(phrases):
        to_add = True
        for j in range(len(result)):
            p = result[j]
            # Overlap de tokens
            set1 = set(phr.split())
            set2 = set(p.split())
            intersection = set1 & set2
            overlap1 = len(intersection) / max(1, len(set1))
            overlap2 = len(intersection) / max(1, len(set2))
            if overlap1 > min_overlap_ratio or overlap2 > min_overlap_ratio:
                # Si la nouvelle phrase est plus longue, on remplace
                if len(phr) > len(p):
                    result[j] = phr
                to_add = False
                break
        if to_add:
            result.append(phr)
    return result

def main():
    files = sys.argv[1:-1]
    output = sys.argv[-1]
    textes = []
    for fname in files:
        with open(fname, encoding="utf-8") as f:
            raw = f.read()
            sentences = [s.strip() for s in split_sentences(raw) if s.strip()]
            textes.append(sentences)
    result = align_multiple(textes)
    result = remove_substring_duplicates(result, min_overlap_ratio=0.7)
    with open(output, "w", encoding="utf-8") as fout:
        fout.write("\n\n".join([s for s in result if s.strip()]))

if __name__ == "__main__":
    main()
