#!/usr/bin/env python3
import argparse, os, json, random, hashlib, time
from pathlib import Path
from PIL import Image

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json_dir", required=True)
    ap.add_argument("--img_dir", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--val_split", type=float, default=0.1)
    ap.add_argument("--maxlen", type=int, default=0, help="0=illimité")
    # === CACHE / INCRÉMENTAL ===
    ap.add_argument("--incremental", action="store_true", help="Ne recroppe que les nouveaux/maj.")
    ap.add_argument("--force", action="store_true", help="Ignore le cache et régénère.")
    ap.add_argument("--cache_file", default=None, help="Chemin du manifest cache (json).")
    return ap.parse_args()

def file_sig(p: Path):
    try:
        st = p.stat()
        return f"{p.name}:{int(st.st_mtime)}:{st.st_size}"
    except Exception:
        return f"{p.name}:NA:NA"

def dir_digest(paths):
    h = hashlib.sha1()
    for p in sorted(paths):
        h.update(p.encode("utf-8"))
    return h.hexdigest()

def build_inputs_digest(img_dir: Path, json_dir: Path):
    img_exts = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp")
    imgs = sorted([str(p) for p in img_dir.rglob("*") if p.suffix.lower() in img_exts])
    jsons = sorted([str(p) for p in json_dir.glob("*.json")])
    sigs = []
    for s in imgs + jsons:
        sigs.append(file_sig(Path(s)))
    return dir_digest(sigs), imgs, jsons

def load_json(fp):
    try:
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def norm_stem(name: str) -> str:
    stem = Path(name).stem
    if len(stem) > 5 and stem[-5] == "_" and stem[-4:].isdigit():
        return stem[:-5]
    return stem

def index_json(json_dir: Path):
    idx_by_jsonstem = {}
    idx_by_origstem = {}
    idx_by_pagehash = {}
    for jp in json_dir.glob("*.json"):
        idx_by_jsonstem[jp.stem] = jp
        d = load_json(jp)
        if not isinstance(d, dict):
            continue
        meta = d.get("metadata") or d.get("meta") or {}
        orig = str(meta.get("original_filename") or "").strip()
        if orig:
            idx_by_origstem[Path(orig).stem] = jp
        ph = str(meta.get("page_hash") or "").strip()
        if ph:
            idx_by_pagehash[ph] = jp
    return idx_by_jsonstem, idx_by_origstem, idx_by_pagehash

def find_json_for_image(img_path: Path, idx_jsonstem, idx_origstem, idx_ph):
    stem = img_path.stem
    nstem = norm_stem(stem)
    if stem in idx_jsonstem: return idx_jsonstem[stem]
    if nstem in idx_jsonstem: return idx_jsonstem[nstem]
    if stem in idx_origstem: return idx_origstem[stem]
    if nstem in idx_origstem: return idx_origstem[nstem]
    if stem in idx_ph: return idx_ph[stem]
    if nstem in idx_ph: return idx_ph[nstem]
    return None

def bbox_to_xyxy(b):
    if not isinstance(b, (list, tuple)) or len(b) < 4:
        return None
    x1, y1, a, b2 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
    if a > 0 and b2 > 0 and (x1 + a) > x1 and (y1 + b2) > y1:
        return (x1, y1, x1 + a, y1 + b2)
    return (x1, y1, a, b2)

def safe_crop(im: Image.Image, box):
    w, h = im.size
    x1 = max(0, min(w, int(round(box[0]))))
    y1 = max(0, min(h, int(round(box[1]))))
    x2 = max(0, min(w, int(round(box[2]))))
    y2 = max(0, min(h, int(round(box[3]))))
    if x2 <= x1 or y2 <= y1:
        return None
    return im.crop((x1, y1, x2, y2))

def read_cache(cache_file: Path):
    if not cache_file.exists(): return None
    try:
        return json.load(open(cache_file, "r", encoding="utf-8"))
    except Exception:
        return None

def write_cache(cache_file: Path, payload: dict):
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def main():
    args = parse_args()
    json_dir = Path(args.json_dir)
    img_dir  = Path(args.img_dir)
    out_dir  = Path(args.out_dir)
    crops_dir = out_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    cache_file = Path(args.cache_file) if args.cache_file else (out_dir / ".cache/json2crops.manifest.json")

    # === CACHE CHECK ===
    digest_now, imgs_list, jsons_list = build_inputs_digest(img_dir, json_dir)
    cache = read_cache(cache_file)
    if (not args.force) and cache and cache.get("inputs_digest") == digest_now and \
       (out_dir/"train.txt").exists() and (out_dir/"val.txt").exists():
        print(f"[CACHE] Unchanged inputs, skip json2crops. (digest={digest_now[:12]})")
        print(f"        train/val existants : {out_dir/'train.txt'} ; {out_dir/'val.txt'}")
        return

    # Index JSON
    idx_jsonstem, idx_origstem, idx_ph = index_json(json_dir)

    # Images candidates
    img_exts = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp")
    imgs = [Path(p) for p in imgs_list if Path(p).suffix.lower() in img_exts]

    # Si incrémental, on lit l’ancien manifest pour connaître les crops déjà générés
    old_pairs = set()
    if args.incremental and cache and isinstance(cache.get("pairs"), list):
        for p in cache["pairs"]:
            if isinstance(p, list) and len(p) == 2:
                old_pairs.add(tuple(p))

    pairs = []  # (rel_path, text)
    warn_missing = warn_empty = 0
    created = skipped_existing = 0
    print(len(imgs))
    for ip in imgs:
        jp = find_json_for_image(ip, idx_jsonstem, idx_origstem, idx_ph)
        if jp is None:
            print(f"[WARN] JSON introuvable pour {ip.name}")
            warn_missing += 1
            continue

        data = load_json(jp)
        if not isinstance(data, dict):
            print(f"[WARN] JSON illisible: {jp.name}")
            continue

        cells = data.get("cells")
        if not isinstance(cells, list) or len(cells) == 0:
            print(f"[WARN] pas de 'cells' dans {jp.name}")
            continue

        try:
            im = Image.open(ip).convert("RGB")
        except (FileNotFoundError, PIL.UnidentifiedImageError, OSError) as e:
            print(f"[WARN] image illisible {ip}: {e}")
            continue

        def keyfn(c):
            b = bbox_to_xyxy(c.get("bbox"))
            return (b[1], b[0]) if b else (0.0, 0.0)

        for k, c in enumerate(sorted(cells, key=keyfn)):
            txt = c.get("text")
            if not isinstance(txt, str) or not txt.strip():
                warn_empty += 1
                continue
            bxyxy = bbox_to_xyxy(c.get("bbox"))
            if not bxyxy:
                continue
            rel = f"crops/{ip.stem}_{k:04d}.png"
            # Incrémental: si déjà dans old_pairs ET le fichier existe, on garde
            if args.incremental and ((rel, txt.strip()) in old_pairs) and (out_dir / rel).exists():
                skipped_existing += 1
                pairs.append((rel, txt.strip()))
                continue
            crop = safe_crop(im, bxyxy)
            if crop is None:
                continue
            (out_dir / "crops").mkdir(exist_ok=True)
            crop.save(out_dir / rel)
            created += 1
            if args.maxlen and len(txt) > args.maxlen:
                txt = txt[:args.maxlen]
            pairs.append((rel, txt.strip()))

    if not pairs:
        print("[FATAL] Aucun pair crop/texte généré.")
        exit(2)

    random.shuffle(pairs)
    n = len(pairs)
    nv = max(1, int(round(n * args.val_split)))
    val = pairs[:nv]
    train = pairs[nv:]

    with open(out_dir / "train.txt", "w", encoding="utf-8") as f:
        for p, t in train: f.write(f"{p}\t{t}\n")
    with open(out_dir / "val.txt", "w", encoding="utf-8") as f:
        for p, t in val:   f.write(f"{p}\t{t}\n")

    # Écrit le cache
    payload = {
        "inputs_digest": digest_now,
        "ts": int(time.time()),
        "pairs": pairs,  # pour l'incrémental
        "counts": {"train": len(train), "val": len(val), "created": created, "skipped_existing": skipped_existing},
    }
    write_cache(cache_file, payload)

    print(f"[CROPS] train:{len(train)}  val:{len(val)}  created:{created}  skipped_existing:{skipped_existing} "
          f"warn_missing_json:{warn_missing} warn_empty_text:{warn_empty}")
    print(f"      → {out_dir/'train.txt'} ; {out_dir/'val.txt'} ; crops={out_dir/'crops'}")

if __name__ == "__main__":
    main()
