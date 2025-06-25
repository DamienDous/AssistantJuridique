import sys
import os
from PIL import Image
import numpy as np

def is_blank_line(pixels, min_white_ratio=0.9):
    """Détermine si une ligne contient principalement du blanc"""
    white_pixels = np.sum(pixels > 245)
    ratio = white_pixels / len(pixels)
    return ratio >= min_white_ratio

def find_cut_lines(im_array, slice_height=900, step=100, min_blank_ratio=1):
    """Cherche les meilleures lignes de découpe en détectant les bandes blanches"""
    height = im_array.shape[0]
    cut_positions = [0]
    y = 0

    while y + slice_height < height:
        best_cut = y + slice_height
        found = False
        for dy in range(-step, step + 1, 80):
            scan_y = y + slice_height + dy
            if scan_y >= height or scan_y <= y:
                continue
            line = im_array[scan_y, :]
            if is_blank_line(line, min_blank_ratio):
                best_cut = scan_y
                found = True
                break
        cut_positions.append(best_cut)
        y = best_cut

    cut_positions.append(height)
    return cut_positions

def crop_and_save_slices(img, cut_positions, out_prefix):
    for i in range(len(cut_positions) - 1):
        top = cut_positions[i]
        bottom = cut_positions[i + 1]
        cropped = img.crop((0, top, img.width, bottom))
        out_path = f"{out_prefix}_{str(i).zfill(3)}.png"
        cropped.save(out_path)

def main():
    if len(sys.argv) < 3:
        print("Usage: python read_and_crop.py <image_path> <output_prefix> [crop_width]")
        sys.exit(1)

    input_path = sys.argv[1]
    out_prefix = sys.argv[2]
    crop_width = int(sys.argv[3]) if len(sys.argv) >= 4 else None

    if not os.path.exists(input_path):
        print(f"❌ Fichier introuvable : {input_path}")
        sys.exit(1)

    print(f"📥 Lecture : {input_path}")
    img = Image.open(input_path).convert("L")  # niveaux de gris pour détection blanche

    if crop_width:
        left = 10
        right = min(img.width, left + crop_width)
        img = img.crop((left, 0, right, img.height))
        print(f"📐 Recadrage horizontal appliqué : x={left} à {right}")

    im_array = np.array(img)

    print("🔎 Détection intelligente des lignes blanches…")
    cut_positions = find_cut_lines(im_array, slice_height=880, step=100, min_blank_ratio=1)
    print(f"✂️ {len(cut_positions) - 1} segments détectés")

    img_rgb = Image.open(input_path).convert("RGB")
    if crop_width:
        img_rgb = img_rgb.crop((left, 0, right, img_rgb.height))

    crop_and_save_slices(img_rgb, cut_positions, out_prefix)
    print("✅ Découpe terminée.")

if __name__ == "__main__":
    main()
