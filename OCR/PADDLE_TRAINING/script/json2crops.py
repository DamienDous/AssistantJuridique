#!/usr/bin/env python3
import argparse, os, json, random, hashlib, time
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from concurrent.futures import ProcessPoolExecutor, as_completed

# ----------------- ARGS -----------------
def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json_dir", required=True)
    ap.add_argument("--img_dir", required=True)
    ap.add_argument("--glob_dir", required=True)
    ap.add_argument("--val_split", type=float, default=0.1, help="part de validation (par rapport au total)")
    ap.add_argument("--test_split", type=float, default=0.1, help="part de test (par rapport au total)")
    ap.add_argument("--maxlen", type=int, default=0, help="0=illimité")
    ap.add_argument("--incremental", action="store_true", help="Ne recroppe que les nouveaux/maj.")
    ap.add_argument("--force", action="store_true", help="Ignore le cache et régénère.")
    ap.add_argument("--cache_file", default=None, help="Chemin du manifest cache (json).")
    # Nouveaux
    ap.add_argument("--workers", type=int, default=0, help="0 = os.cpu_count()")
    ap.add_argument("--save_format", choices=["png","jpg"], default="png")
    ap.add_argument("--jpg_quality", type=int, default=95)
    ap.add_argument("--png_compress", type=int, default=1)  # 0..9 (1 = rapide)
    return ap.parse_args()

# ----------------- UTILS -----------------
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

# ----------------- WORKER -----------------
def process_one_image(task):
    (ip_str, jp_str, crops_dir_str, incremental, old_pairs_frozen, maxlen,
     save_format, jpg_quality, png_compress) = task

    crops_dir = Path(crops_dir_str)
    pairs = []
    created = 0
    skipped_existing = 0
    warn_empty = 0
    warn_json_bad = 0
    warn_img_bad = 0

    try:
        data = load_json(Path(jp_str))
        if not isinstance(data, dict):
            warn_json_bad += 1
            return pairs, created, skipped_existing, warn_empty, warn_json_bad, warn_img_bad
        cells = data.get("cells")
        if not isinstance(cells, list) or len(cells) == 0:
            return pairs, created, skipped_existing, warn_empty, warn_json_bad, warn_img_bad

        try:
            im = Image.open(ip_str).convert("RGB")
        except (FileNotFoundError, UnidentifiedImageError, OSError):
            warn_img_bad += 1
            return pairs, created, skipped_existing, warn_empty, warn_json_bad, warn_img_bad

        def keyfn(c):
            b = bbox_to_xyxy(c.get("bbox"))
            return (b[1], b[0]) if b else (0.0, 0.0)

        old_pairs = old_pairs_frozen
        for k, c in enumerate(sorted(cells, key=keyfn)):
            txt = c.get("text")
            if not isinstance(txt, str) or not txt.strip():
                warn_empty += 1
                continue
            bxyxy = bbox_to_xyxy(c.get("bbox"))
            if not bxyxy:
                continue

            stem = Path(ip_str).stem
            ext = ".png" if save_format == "png" else ".jpg"
            rel = f"crops/{stem}_{k:04d}{ext}"
            abs_p = crops_dir / Path(rel).name

            if incremental and ((rel, txt.strip()) in old_pairs) and abs_p.exists():
                skipped_existing += 1
                pairs.append((rel, txt.strip()))
                continue

            crop = safe_crop(im, bxyxy)
            if crop is None:
                continue

            abs_p.parent.mkdir(parents=True, exist_ok=True)
            if save_format == "png":
                crop.save(abs_p, compress_level=max(0, min(9, int(png_compress))), optimize=False)
            else:
                if crop.mode != "RGB":
                    crop = crop.convert("RGB")
                crop.save(abs_p, quality=max(1, min(100, int(jpg_quality))), subsampling=0, optimize=False)

            created += 1
            if maxlen and len(txt) > maxlen:
                txt = txt[:maxlen]
            pairs.append((rel, txt.strip()))

    except Exception:
        pass

    return pairs, created, skipped_existing, warn_empty, warn_json_bad, warn_img_bad

# ----------------- MAIN -----------------
def main():
    args = parse_args()
    json_dir = Path(args.json_dir)
    img_dir  = Path(args.img_dir)
    glob_dir  = Path(args.glob_dir)
    out_dir = glob_dir / "output"
    crops_dir = glob_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    cache_file = Path(args.cache_file) if args.cache_file else (crops_dir / ".cache/json2crops.manifest.json")

    # CACHE
    digest_now, imgs_list, jsons_list = build_inputs_digest(img_dir, json_dir)
    cache = read_cache(cache_file)
    if (not args.force) and cache and cache.get("inputs_digest") == digest_now and \
       (out_dir/'train.txt').exists() and (out_dir/'val.txt').exists() and (out_dir/'test.txt').exists():
        print(f"[CACHE] Unchanged inputs, skip json2crops. (digest={digest_now[:12]})")
        print(f"        train/val/test existants dans {out_dir}")
        return

    # Index JSON
    idx_jsonstem, idx_origstem, idx_ph = index_json(json_dir)

    # Liste d'images
    img_exts = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp")
    imgs = [Path(p) for p in imgs_list if Path(p).suffix.lower() in img_exts]

    # Incrémental: old_pairs
    old_pairs = set()
    if args.incremental and cache and isinstance(cache.get("pairs"), list):
        for p in cache["pairs"]:
            if isinstance(p, list) and len(p) == 2:
                old_pairs.add(tuple(p))
    old_pairs_frozen = frozenset(old_pairs)

    # Mapper image -> json
    tasks = []
    warn_missing = 0
    for ip in imgs:
        jp = find_json_for_image(ip, idx_jsonstem, idx_origstem, idx_ph)
        if jp is None:
            warn_missing += 1
            continue
        tasks.append((str(ip), str(jp), str(crops_dir),
                      bool(args.incremental), old_pairs_frozen,
                      int(args.maxlen), args.save_format,
                      int(args.jpg_quality), int(args.png_compress)))

    if not tasks:
        print("[FATAL] Aucune image éligible.")
        return

    workers = args.workers or os.cpu_count() or 1
    print(f"[INFO] Images: {len(tasks)} | workers: {workers} | fmt={args.save_format}")
    all_pairs = []
    created = skipped_existing = warn_empty = warn_json_bad = warn_img_bad = 0

    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(process_one_image, t) for t in tasks]
        for fut in as_completed(futures):
            pairs, c, s, we, wj, wi = fut.result()
            all_pairs.extend(pairs)
            created += c
            skipped_existing += s
            warn_empty += we
            warn_json_bad += wj
            warn_img_bad += wi

    if not all_pairs:
        print("[FATAL] Aucun pair crop/texte généré.")
        return

    # Shuffle & Split  train / val / test
    random.shuffle(all_pairs)
    n = len(all_pairs)
    n_val = max(1, int(round(n * args.val_split)))
    n_test = max(1, int(round(n * args.test_split)))
    n_train = n - n_val - n_test

    train = all_pairs[:n_train]
    val   = all_pairs[n_train:n_train+n_val]
    test  = all_pairs[n_train+n_val:]

    out_dir.mkdir(parents=True, exist_ok=True)
    def save_pairs(pairs, path):
        with open(path, "w", encoding="utf-8") as f:
            for p, t in pairs:
                f.write(f"{p}\t{t}\n")

    save_pairs(train, out_dir/'train.txt')
    save_pairs(val, out_dir/'val.txt')
    save_pairs(test, out_dir/'test.txt')

    payload = {
        "inputs_digest": digest_now,
        "ts": int(time.time()),
        "pairs": all_pairs,
        "counts": {
            "train": len(train),
            "val": len(val),
            "test": len(test),
            "created": created,
            "skipped_existing": skipped_existing,
            "warn_missing_json": warn_missing,
            "warn_empty_text": warn_empty,
            "warn_json_bad": warn_json_bad,
            "warn_img_bad": warn_img_bad
        },
    }
    write_cache(cache_file, payload)

    print(f"[CROPS] total:{n} train:{len(train)} val:{len(val)} test:{len(test)} "
          f"created:{created} skipped_existing:{skipped_existing} "
          f"warn_missing_json:{warn_missing} warn_json_bad:{warn_json_bad} "
          f"warn_img_bad:{warn_img_bad} warn_empty_text:{warn_empty}")
    print(f"      → {out_dir/'train.txt'} ; {out_dir/'val.txt'} ; {out_dir/'test.txt'} ; crops={crops_dir}")

if __name__ == "__main__":
    main()
