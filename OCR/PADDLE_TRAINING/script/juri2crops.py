#!/usr/bin/env python3
import argparse, random, json
from pathlib import Path
from PIL import Image
from utils_count import compute_global_count, should_skip

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img_dir", required=True, help="Dossier images du corpus juridique")
    ap.add_argument("--labels", required=True, help="Fichier labels.txt")
    ap.add_argument("--glob_dir", required=True, help="Base dataset (où créer output/ et crops/)")
    ap.add_argument("--val_split", type=float, default=0.1)
    ap.add_argument("--test_split", type=float, default=0.1)
    return ap.parse_args()

def main():
    args = parse_args()
    img_dir = Path(args.img_dir)
    labels_file = Path(args.labels)
    glob_dir = Path(args.glob_dir)
    out_dir = glob_dir / "output"
    crops_dir = glob_dir / "crops"

    out_dir.mkdir(parents=True, exist_ok=True)
    crops_dir.mkdir(parents=True, exist_ok=True)

    nb_total = compute_global_count(img_dir="img", json_dir="anno", img_fr_dir="img_fr")

    if should_skip(out_dir, nb_total, "juri"):
        return

    # === Lecture labels ===
    with open(labels_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    labels = data.get("labels", {})
    pairs = []
    for key, txt in labels.items():
        # Nettoyage du texte
        txt_clean = txt.replace("\t", " ").replace("\n", " ").replace("\r", " ").strip()
        if not txt_clean:
            continue

        # Associer l’image
        img_name = f"{key}.jpg"   # ou .png selon ton dataset
        abs_img = img_dir / img_name
        if not abs_img.is_file():
            print(f"[WARN] Image manquante: {abs_img}")
            continue

        # Copier dans crops/
        out_p = crops_dir / abs_img.name
        if not out_p.exists():
            try:
                im = Image.open(abs_img).convert("RGB")
                im.save(out_p)
            except Exception as e:
                print(f"[WARN] Impossible de copier {abs_img}: {e}")
                continue

        # Ajouter le couple chemin/label
        pairs.append((f"crops/{abs_img.name}", txt_clean))

    if not pairs:
        print("[FATAL] Aucun couple image/texte valide trouvé.")
        return

    # Shuffle et split train/val/test
    random.shuffle(pairs)
    n = len(pairs)
    n_val = max(1, int(round(n * args.val_split)))
    n_test = max(1, int(round(n * args.test_split)))
    n_train = n - n_val - n_test

    train = pairs[:n_train]
    val   = pairs[n_train:n_train+n_val]
    test  = pairs[n_train+n_val:]

    splits = {
        "train": train,
        "val": val,
        "test": test,
    }

    # Écriture des fichiers
    for name, subset in splits.items():
        out_file = out_dir / f"{name}.txt"
        with open(out_file, "w", encoding="utf-8") as f:
            for p, t in subset:
                if not p or not t:
                    continue
                f.write(f"{p}\t{t}\n")

    print(f"[JURI2CROPS] total:{n} train:{len(train)} val:{len(val)} test:{len(test)}")
    print(f"      → {out_dir/'train.txt'} ; {out_dir/'val.txt'} ; {out_dir/'test.txt'} ; crops={crops_dir}")


if __name__ == "__main__":
    main()