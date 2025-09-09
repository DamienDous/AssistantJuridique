#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, os, cv2, sys, hashlib

CACHE_VERSION = "PIPELINE_NORMALIZE_VERSION=v2"  # bump si la logique change

# ----------------------------
# Utilitaires
# ----------------------------
def split_line(line: str):
    """Parses a line as: <path>\t<label> (prioritaire) sinon <path><space>label..."""
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
    """Force l'image en BGR 3 canaux (convertit GRAY/BGRA si besoin)."""
    if img is None:
        return None
    if len(img.shape) == 2:  # GRAY
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if len(img.shape) == 3 and img.shape[2] == 1:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if len(img.shape) == 3 and img.shape[2] >= 3:
        return img[:, :, :3]  # BGRA -> BGR
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

def make_fingerprint(base, config_path=None):
    """
    Hash global basé sur:
      - base/train.txt, base/val.txt, base/charset.txt (si existent)
      - tous les .png sous base/crops/
      - --config (si fourni)
      - constante CACHE_VERSION
    """
    candidates = []

    for name in ("train.txt", "val.txt", "charset.txt"):
        p = os.path.join(base, name)
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

    base_norm = os.path.abspath(base)
    items = []
    for p in candidates:
        try:
            rel = os.path.relpath(os.path.abspath(p), base_norm)
        except ValueError:
            rel = os.path.abspath(p)  # hors base
        items.append((rel, p))
    items.sort(key=lambda x: x[0])

    for rel, p in items:
        try:
            fh = sha256_file(p)
        except FileNotFoundError:
            continue
        agg.update(rel.encode("utf-8")); agg.update(b"\0")
        agg.update(fh.encode("utf-8"));   agg.update(b"\0")

    return agg.hexdigest()

# ----------------------------
# Normalisation d'un split
# ----------------------------
def process_split(base, split, max_len, expect_width, hstride, drop_too_long, charset):
    """
    - Coupe "dure" à max_len
    - Contrainte CTC: len(label) <= time_steps ~ expect_width/hstride - 2
    - Filtre OOV: drop si un char du label n'est pas dans charset (si charset fourni)
    - Force BGR 3 canaux sur disque
    - Réécrit <split>.txt proprement
    """
    path_txt = os.path.join(base, f'{split}.txt')
    if not os.path.isfile(path_txt):
        print(f"[WARN] missing {path_txt}", file=sys.stderr)
        return

    max_timesteps = max(1, expect_width // max(1, hstride)) - 2
    limit = max_timesteps if drop_too_long else max_len

    out = []
    kept = dropped = fixed = oov = 0

    with open(path_txt, 'r', encoding='utf-8', errors='ignore') as f:
        for raw in f:
            sp = split_line(raw)
            if not sp:
                dropped += 1
                continue
            p, lab = sp
            if not lab:
                dropped += 1
                continue

            # Couper d'abord à max_len (sécurité)
            if max_len and len(lab) > max_len:
                lab = lab[:max_len]

            # Contrainte CTC
            if len(lab) > limit:
                if drop_too_long:
                    dropped += 1
                    continue
                else:
                    lab = lab[:limit]

            # Filtre OOV si charset disponible
            if charset is not None:
                bad_chars = [c for c in lab if c not in charset]
                if bad_chars:
                    oov += 1
                    continue

            # Normalisation image
            abs_p = p if os.path.isabs(p) else os.path.join(base, p)
            img = cv2.imread(abs_p, cv2.IMREAD_UNCHANGED)
            img = ensure_bgr(img)
            if img is None or img.size == 0:
                dropped += 1
                continue
            # garantit BGR 3 canaux sur disque
            cv2.imwrite(abs_p, img)

            rel = os.path.relpath(abs_p, base)
            out.append(f"{rel}\t{lab}")
            kept += 1
            fixed += 1

    with open(path_txt, 'w', encoding='utf-8') as f:
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
    ap.add_argument('--base', required=True, help="Répertoire dataset (avec train.txt, val.txt, crops/)")
    ap.add_argument('--char', required=True, help="charset.txt")
    ap.add_argument('--config', default=None, help="Chemin YAML à inclure dans le fingerprint (optionnel)")
    ap.add_argument('--max_len', type=int, default=256)
    ap.add_argument('--expect_width', type=int, default=320)
    ap.add_argument('--hstride', type=int, default=4)  # CRNN ~ /4 en largeur
    ap.add_argument('--drop_too_long', action='store_true', default=True)
    args = ap.parse_args()

    base = os.path.abspath(args.base)
    cache_dir = os.path.join(base, '.cache')
    os.makedirs(cache_dir, exist_ok=True)
    hash_file = os.path.join(cache_dir, 'norm.sha256')

    # Charger charset (si présent)
    charset_path = args.char
    charset = None
    if os.path.isfile(charset_path):
        try:
            with open(charset_path, 'r', encoding='utf-8') as f:
                charset = set(ch.rstrip('\r\n') for ch in f if ch.strip() != "")
            # ✅ Autoriser aussi l'espace si use_space_char est activé
            charset.add(" ")
        except Exception as e:
            print(f"[WARN] Impossible de lire charset.txt ({e}) -> filtre OOV désactivé.", file=sys.stderr)
            charset = None

    # --- Cache check ---
    new_hash = make_fingerprint(base=base, config_path=args.config)
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

    # --- Normalisation ---
    print("▶ Normalisation & validation dataset (rebuild)")
    for split in ('train', 'val'):
        process_split(
            base=base,
            split=split,
            max_len=args.max_len,
            expect_width=args.expect_width,
            hstride=args.hstride,
            drop_too_long=args.drop_too_long,
            charset=charset
        )

    # --- Écrit le nouveau hash ---
    try:
        with open(hash_file, 'w', encoding='utf-8') as f:
            f.write(new_hash + "\n")
    except Exception as e:
        print(f"[WARN] impossible d'écrire {hash_file}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
