#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, os, cv2, sys, hashlib

CACHE_VERSION = "PIPELINE_NORMALIZE_VERSION=v3"  # bump si la logique change

# ----------------------------
# Utilitaires
# ----------------------------
def split_line(line: str):
    line = line.rstrip('\r\n')
    if not line:
        return None
    if '\t' in line:
        p, lab = line.split('\t', 1)
        return p.strip(), lab.strip()
    parts = line.split()
    if len(parts) < 2:
        return None
    path = parts[0]
    label = line[len(path):].strip()
    return path, label

def ensure_bgr(img):
    if img is None:
        return None
    if len(img.shape) == 2:  # GRAY
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if len(img.shape) == 3 and img.shape[2] == 1:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if len(img.shape) == 3 and img.shape[2] >= 3:
        return img[:, :, :3]
    return None

# ----------------------------
# Fingerprint / cache
# ----------------------------
def sha256_file(path, chunk=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def make_fingerprint(base, out_base, config_path=None):
    """
    Hash global basé sur:
      - out_base/train.txt, out_base/val.txt, out_base/charset.txt (si existent)
      - tous les .png sous base/crops/
      - config YAML (si fourni)
      - constante CACHE_VERSION
    """
    candidates = []

    for name in ("train.txt", "val.txt", "charset.txt"):
        p = os.path.join(out_base, name)
        if os.path.isfile(p):
            candidates.append(p)

    crops_dir = os.path.join(base, "crops")
    if os.path.isdir(crops_dir):
        for root, _, files in os.walk(crops_dir):
            for fn in files:
                if fn.lower().endswith(".png"):
                    candidates.append(os.path.join(root, fn))

    if config_path and os.path.isfile(config_path):
        candidates.append(config_path)

    agg = hashlib.sha256()
    agg.update(CACHE_VERSION.encode("utf-8"))

    # ordre stable
    items = sorted([os.path.abspath(p) for p in candidates])

    for p in items:
        try:
            fh = sha256_file(p)
        except FileNotFoundError:
            continue
        agg.update(p.encode("utf-8")); agg.update(b"\0")
        agg.update(fh.encode("utf-8")); agg.update(b"\0")

    return agg.hexdigest()

NORMALIZE_MAP = {
    "−": "-",
    "‐": "-",
    "‒": "-",
    "-": "-",
    "⁄": "/",
    "∗": "*",
    "…": "...",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "≥": ">=",
    "≤": "<=",
    "≈": "~",
    "÷": "/",
    "×": "x",
    "©": "(c)",
    "®": "(R)",
    "♯": "#",
    "●": "*",
    "•": "*",
    "⦁": "*",
    "☐": "[ ]",
    "☒": "[x]",
    "✓": "v",
    "▶": ">",
    "∑": "SUM",
    "Σ": "SUM",
    "π": "pi",
    "λ": "lambda",
    "γ": "gamma",
    "ν": "nu",
    "η": "eta",
    "φ": "phi",
    "Δ": "Delta",
    "Λ": "Lambda",
    "–": "-",   # en-dash
    "—": "-",   # em-dash
    "¨": "",    # tréma isolé → supprime
    "Ø": "O",   # O barré → O
    "¼": "1/4",
    "½": "1/2",
    "¾": "3/4",
}

def normalize_text(text):
    out = []
    for ch in text:
        if ch in NORMALIZE_MAP:
            out.append(NORMALIZE_MAP[ch])
        elif (0xE000 <= ord(ch) <= 0xF8FF) or ord(ch) < 32:  # caractères privés ou de contrôle
            continue  # on supprime
        elif '\u4e00' <= ch <= '\u9fff' or '\u3040' <= ch <= '\u30ff':
            continue  # chinois/japonais → DROP si modèle latin
        else:
            out.append(ch)
    return "".join(out)

# ----------------------------
# Normalisation d'un split
# ----------------------------
def process_split(base, split, max_len, expect_width, hstride, drop_too_long, charset, out_base=None):
    out_base = out_base or base
    path_txt_in  = os.path.join(out_base, f'{split}.txt')
    path_txt_out = os.path.join(out_base, f'{split}.txt')

    if not os.path.isfile(path_txt_in):
        print(f"[WARN] missing {path_txt_in}", file=sys.stderr)
        return

    max_timesteps = max(1, expect_width // max(1, hstride)) - 2
    limit = max_timesteps if drop_too_long else max_len

    out = []
    kept = dropped = fixed = oov = 0

    with open(path_txt_in, 'r', encoding='utf-8', errors='ignore') as f:
        for lineno, raw in enumerate(f, 1):
            sp = split_line(raw)
            if not sp:
                print(f"[DEBUG-{split}] ligne {lineno}: vide ou mal formée → DROP")
                dropped += 1
                continue
            p, lab = sp
            if not lab:
                print(f"[DEBUG-{split}] ligne {lineno}: label vide → DROP")
                dropped += 1
                continue

            if max_len and len(lab) > max_len:
                print(f"[DEBUG-{split}] ligne {lineno}: label trop long ({len(lab)}) → tronqué à {max_len}")
                lab = lab[:max_len]

            if len(lab) > limit:
                if drop_too_long:
                    print(f"[DEBUG-{split}] ligne {lineno}: label {len(lab)} > {limit} (timesteps) → DROP")
                    dropped += 1
                    continue
                else:
                    print(f"[DEBUG-{split}] ligne {lineno}: tronqué à {limit} (timesteps)")
                    lab = lab[:limit]
            
            lab = normalize_text(lab)

            if charset is not None:
                bad_chars = [c for c in lab if c not in charset]
                if bad_chars:
                    print(f"[DEBUG-{split}] ligne {lineno}: caractères OOV {bad_chars} → DROP")
                    oov += 1
                    continue

            abs_p = p if os.path.isabs(p) else os.path.join(base, p)
            img = cv2.imread(abs_p, cv2.IMREAD_UNCHANGED)
            img = ensure_bgr(img)
            if img is None or img.size == 0:
                print(f"[DEBUG-{split}] ligne {lineno}: image introuvable/corrompue {abs_p} → DROP")
                dropped += 1
                continue

            cv2.imwrite(abs_p, img)

            rel = os.path.relpath(abs_p, base)
            out.append(f"{rel}\t{lab}")
            kept += 1
            fixed += 1

    with open(path_txt_out, 'w', encoding='utf-8') as f:
        f.write("\n".join(out) + ("\n" if out else ""))

    if charset is None:
        print(f"[OK] {split}: kept={kept}, dropped={dropped}, fixed_imgs={fixed}, "
              f"limit={limit} (timesteps), OOV=SKIPPED(no charset)")
    else:
        print(f"[OK] {split}: kept={kept}, dropped={dropped}, fixed_imgs={fixed}, "
              f"OOV_dropped={oov}, limit={limit} (timesteps)")

# ----------------------------
# Main
# ----------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True, help="Répertoire dataset brut (avec crops/)")
    ap.add_argument('--out_base', required=False, default=None,
                    help="Répertoire de sortie (train.txt, val.txt, cache). Défaut = base")
    ap.add_argument('--char', required=True, help="charset.txt")
    ap.add_argument('--config', default=None, help="Chemin YAML à inclure dans le fingerprint (optionnel)")
    ap.add_argument('--max_len', type=int, default=256)
    ap.add_argument('--expect_width', type=int, default=320)
    ap.add_argument('--hstride', type=int, default=4)
    ap.add_argument('--drop_too_long', action='store_true', default=True)
    args = ap.parse_args()

    base = os.path.abspath(args.base)
    out_base = os.path.abspath(args.out_base) if args.out_base else base

    os.makedirs(out_base, exist_ok=True)
    cache_dir = os.path.join(out_base, '.cache')
    os.makedirs(cache_dir, exist_ok=True)
    hash_file = os.path.join(cache_dir, 'norm.sha256')

    charset = None
    if os.path.isfile(args.char):
        try:
            with open(args.char, 'r', encoding='utf-8') as f:
                charset = set(ch.rstrip('\r\n') for ch in f if ch.strip() != "")
            charset.add(" ")
        except Exception as e:
            print(f"[WARN] Impossible de lire charset.txt ({e}) -> filtre OOV désactivé.", file=sys.stderr)

    new_hash = make_fingerprint(base=base, out_base=out_base, config_path=args.config)
    old_hash = None
    if os.path.isfile(hash_file):
        try:
            with open(hash_file, 'r', encoding='utf-8') as f:
                old_hash = f.read().strip()
        except Exception:
            old_hash = None

    if old_hash and old_hash == new_hash:
        print("[CACHE] Normalisation inchangée, on skippe l'étape.")
        return

    print("▶ Normalisation & validation dataset (rebuild)")
    for split in ('train', 'val'):
        process_split(
            base=base,
            split=split,
            max_len=args.max_len,
            expect_width=args.expect_width,
            hstride=args.hstride,
            drop_too_long=args.drop_too_long,
            charset=charset,
            out_base=out_base
        )

    try:
        with open(hash_file, 'w', encoding='utf-8') as f:
            f.write(new_hash + "\n")
    except Exception as e:
        print(f"[WARN] impossible d'écrire {hash_file}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
