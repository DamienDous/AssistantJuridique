import sys
import os
import tempfile
import subprocess
import re
from collections import Counter
import requests
from concurrent.futures import ThreadPoolExecutor
from functools import partial

def split_sentences(text):
    import nltk
    try:
        nltk.data.find('tokenizers/punkt')
    except Exception:
        nltk.download('punkt')
    return nltk.sent_tokenize(text, language='french')

def split_words(text):
    # Découpe un texte en mots (simple split par espace, peut être amélioré si besoin)
    import re
    # On enlève les doubles espaces, on coupe sur tout ce qui n'est pas une lettre ou un tiret
    words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    return words

def write_fasta(txt_files, fasta_path):
    fasta = ""
    for i, fname in enumerate(txt_files):
        with open(fname, encoding="utf-8") as f:
            txt = f.read()
            words = split_words(txt)
            fasta += f">OCR{i+1}\n"
            # On colle les mots avec un séparateur (ici |)
            fasta += "|".join(w.strip().replace("|", " ") for w in words if w.strip()) + "\n"
    with open(fasta_path, "w", encoding="utf-8") as fout:
        fout.write(fasta)

def run_clustal(fasta_path, aln_path):
    cmd = [
        "clustalo",
        "-i", fasta_path,
        "-o", aln_path,
        "--outfmt=clu",
        "--force"
    ]
    subprocess.run(cmd, check=True)

def parse_alignment(aln_path):
    seqs = {}
    with open(aln_path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r'^(OCR\d+)\s+(.+)$', line)
            if m:
                name, seqpart = m.groups()
                seqs.setdefault(name, "")
                seqs[name] += seqpart.replace(" ", "")
    return [seq for _, seq in sorted(seqs.items())]

def alignment_to_consensus(seqs, sep="|"):
    # Convertit chaque séquence en liste de tokens
    all_tokens = [seq.split(sep) for seq in seqs]
    # Fait un vote colonne par colonne
    consensus = []
    for columns in zip(*all_tokens):
        tokens = [c for c in columns if c and c != '-']
        if not tokens:
            continue
        best, _ = Counter(tokens).most_common(1)[0]
        consensus.append(best)
    return consensus

def nb_fautes_languagetool(word, lang="fr", cache={}):
    # Utilise un cache pour ne pas refaire 1000x la même requête
    if word in cache:
        return cache[word]
    try:
        resp = requests.post(
            "http://localhost:8010/v2/check",
            data={"text": word, "language": lang},
            timeout=3
        )
        n = len(resp.json().get("matches", []))
    except Exception:
        n = 99
    cache[word] = n
    return n

from concurrent.futures import ThreadPoolExecutor
from functools import partial

def reconstruct_text_from_clustal(clustal_file):
    consensus = []
    with open(clustal_file, encoding="utf-8") as f:
        lines = f.readlines()
    tokens_by_seq = {}
    for line in lines:
        if not line.strip() or line.startswith("CLUSTAL") or line[0].isspace():
            continue
        parts = line.strip().split()
        if len(parts) < 2: continue
        seqname, token = parts[0], parts[1]
        tokens_by_seq.setdefault(seqname, []).append(token)
    all_tokens = list(tokens_by_seq.values())
    nb_cols = min(len(seq) for seq in all_tokens)
    cols = [
        [seq[i] for seq in all_tokens if i < len(seq) and seq[i] != '-']
        for i in range(nb_cols)
    ]
    cache = {}
    def vote_col_lt(col, cache):
        if not col:
            return None
        return min(set(col), key=lambda w: nb_fautes_languagetool(w, cache=cache))
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(partial(vote_col_lt, cache=cache), cols))
        consensus_tokens = [r for r in results if r]
    text = " ".join(consensus_tokens)
    return text

def pipes_to_text_amelioré(output_txt, output_path):
    txt = output_txt.replace('|', ' ')
    txt = re.sub(r' +', ' ', txt)
    txt = re.sub(r'([.?!]) ([a-z])', lambda m: m.group(1) + '\n' + m.group(2), txt)
    # On supprime les débris OCR classiques, à adapter selon ton corpus
    txt = re.sub(r'(\w)-\s+(\w)', r'\1\2', txt)  # fusionne mot coupé par tiret
    txt = re.sub(r'(\s|^)-(\s|$)', ' ', txt)    # tirets isolés
    txt = re.sub(r"([.?!;])\s*", r"\1\n", txt)
    with open(output_path, "w", encoding="utf-8") as fout:
        fout.write(txt.strip())

def main():
    txt_files = sys.argv[1:-1]
    output_path = sys.argv[-1]
    with tempfile.TemporaryDirectory() as tempdir:
        fasta_path = os.path.join(tempdir, "ocr_seqs.fasta")
        aln_path = os.path.join(tempdir, "ocr_seqs.aln")
        write_fasta(txt_files, fasta_path)
        run_clustal(fasta_path, aln_path)
        output_txt = reconstruct_text_from_clustal(aln_path)
        pipes_to_text_amelioré(output_txt, output_path)
    print(f"✅ Consensus écrit dans {output_path}")

if __name__ == "__main__":
    main()
