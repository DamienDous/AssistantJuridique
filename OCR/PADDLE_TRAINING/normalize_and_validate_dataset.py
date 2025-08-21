import argparse, os, cv2, sys, string

def split_line(line):
    line = line.rstrip('\r\n')
    if not line: return None
    if '\t' in line:
        p, lab = line.split('\t', 1)
        return p.strip(), lab.strip()
    parts = line.split()
    if len(parts) < 2: return None
    path = parts[0]
    label = line[len(path):].strip()
    return path, label

def ensure_bgr(img):
    if img is None: return None
    if len(img.shape) == 2:  # GRAY→BGR
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if len(img.shape) == 3 and img.shape[2] == 1:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if len(img.shape) == 3 and img.shape[2] >= 3:
        return img[:, :, :3]  # BGRA→BGR
    return None

def process_split(base, split, max_len, expect_width, hstride, drop_too_long=True):
    path_txt = os.path.join(base, f'{split}.txt')
    if not os.path.isfile(path_txt):
        print(f"[WARN] missing {path_txt}", file=sys.stderr); return

    max_timesteps = max(1, expect_width // max(1, hstride)) - 2
    limit = max_timesteps if drop_too_long else max_len

    out = []
    kept = dropped = fixed = 0
    with open(path_txt, 'r', encoding='utf-8', errors='ignore') as f:
        for raw in f:
            sp = split_line(raw)
            if not sp: dropped += 1; continue
            p, lab = sp
            if not lab: dropped += 1; continue

            # Coupe “dure” à max_len d'abord (sécurité)
            if max_len and len(lab) > max_len:
                lab = lab[:max_len]

            # Contrainte CTC: label_length <= time_steps
            if len(lab) > limit:
                # soit on drop, soit on tronque
                if drop_too_long:
                    dropped += 1; continue
                else:
                    lab = lab[:limit]

            abs_p = p if os.path.isabs(p) else os.path.join(base, p)
            img = cv2.imread(abs_p, cv2.IMREAD_UNCHANGED)
            img = ensure_bgr(img)
            if img is None or img.size == 0:
                dropped += 1; continue
            cv2.imwrite(abs_p, img)  # garantit BGR 3 canaux
            rel = os.path.relpath(abs_p, base)
            out.append(f"{rel}\t{lab}")
            kept += 1; fixed += 1

    with open(path_txt, 'w', encoding='utf-8') as f:
        f.write("\n".join(out) + ("\n" if out else ""))
    print(f"[OK] {split}: kept={kept}, dropped={dropped}, fixed_imgs={fixed}, limit={limit} (timesteps)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--max_len', type=int, default=256)
    ap.add_argument('--expect_width', type=int, default=320)
    ap.add_argument('--hstride', type=int, default=4)  # CRNN ~ /4 en largeur
    ap.add_argument('--drop_too_long', action='store_true', default=True)
    args = ap.parse_args()
    for split in ('train','val'):
        process_split(args.base, split, args.max_len, args.expect_width, args.hstride, args.drop_too_long)

if __name__ == "__main__":
    main()