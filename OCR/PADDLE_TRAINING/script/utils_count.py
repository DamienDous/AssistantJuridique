#!/usr/bin/env python3
from pathlib import Path

def compute_global_count(img_dir, json_dir, img_fr_dir):
    """
    Compte le nombre de fichiers pertinents dans les dossiers du dataset :
      - Images dans img_dir
      - JSON dans json_dir
      - Images dans img_fr_dir
      - +1 si img_fr_dir/labels.json existe
    """
    img_dir = Path(img_dir)
    json_dir = Path(json_dir)
    img_fr_dir = Path(img_fr_dir)

    # img/
    nb_imgs = len(list(img_dir.glob("*.jpg"))) + len(list(img_dir.glob("*.png")))

    # anno/
    nb_jsons = len(list(json_dir.glob("*.json")))

    # img_fr/
    nb_imgs_fr = len(list(img_fr_dir.glob("*.jpg"))) + len(list(img_fr_dir.glob("*.png")))
    nb_labels = 1 if (img_fr_dir / "labels.json").is_file() else 0

    return nb_imgs + nb_jsons + nb_imgs_fr + nb_labels


def should_skip(out_dir, nb_total, process):
    """
    Vérifie si on peut réutiliser le cache :
      - compare le compteur actuel avec l’ancien
      - vérifie l’existence de train/val/test.txt
    """
    count_file = Path(out_dir) / f"{process}_files_count.txt"

    old_count = None
    if count_file.exists():
        try:
            old_count = int(count_file.read_text().strip())
        except Exception:
            old_count = None

    same_count = old_count is not None and old_count == nb_total
    files_exist = all((Path(out_dir)/f).exists() for f in ["train.txt","val.txt","test.txt"])

    if same_count and files_exist:
        print(f"[CACHE] Unchanged inputs, skip. (count={nb_total})")
        return True

    # mettre à jour le compteur si on doit rebuild
    count_file.write_text(str(nb_total))
    return False
