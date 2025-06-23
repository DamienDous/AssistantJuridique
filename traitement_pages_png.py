import os
import numpy as np
from PIL import Image

# === CONFIGURATION ===
WHITE_THRESHOLD    = 250    # pixel ≥ ce seuil est “blanc”
MIN_BAND_HEIGHT    = 1      # hauteur min (px) d’une bande sans blanc
MIN_LAST_PAGE_FRAC = 0.3    # fraction de la hauteur moyenne pour garder la dernière page
INPUT_DIR          = "pipeline_OCR/traitement_lot/input_png"  # dossier contenant vos PNG
OUTPUT_DIR  = "pipeline_OCR/traitement_lot/outputs"  # dossier où seront enregistrés les PDFs

def find_black_bands(gray, white_thresh, min_height):
    h, _     = gray.shape
    has_white = np.any(gray >= white_thresh, axis=1)
    no_white  = ~has_white

    runs = []
    in_run = False
    for y, v in enumerate(no_white):
        if v and not in_run:
            start = y
            in_run = True
        elif not v and in_run:
            end = y
            if (end - start) >= min_height:
                runs.append((start, end))
            in_run = False
    if in_run and (h - start) >= min_height:
        runs.append((start, h))
    return runs

def process_image_to_pdf(image_path, pdf_path):
    # ouvrir et convertir en gris
    img   = Image.open(image_path)
    gray  = np.array(img.convert("L"))
    h, w  = gray.shape

    # repérer les bandes sans blanc, ignorer marge haute & pied bas
    runs = find_black_bands(gray, WHITE_THRESHOLD, MIN_BAND_HEIGHT)
    runs = [(s, e) for (s, e) in runs if s > 0 and e < h]
    runs.sort(key=lambda x: x[0])

    # découper en segments (entre prev_end et start, puis fin)
    segments = []
    prev_end = 0
    for (s, e) in runs:
        if s > prev_end:
            segments.append(img.crop((0, prev_end, w, s)))
        prev_end = e
    if prev_end < h:
        segments.append(img.crop((0, prev_end, w, h)))

    # supprimer la dernière page si trop petite
    if len(segments) > 1:
        heights = [s.height for s in segments]
        avg_h   = sum(heights[:-1]) / (len(heights) - 1)
        if heights[-1] < avg_h * MIN_LAST_PAGE_FRAC:
            segments.pop()

    # assembler en PDF via PIL
    rgb_segs = [s.convert("RGB") for s in segments]
    rgb_segs[0].save(
        pdf_path,
        "PDF",
        resolution=150,
        save_all=True,
        append_images=rgb_segs[1:]
    )

    print(f"✅ {os.path.basename(pdf_path)} créé avec {len(segments)} pages")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for fn in sorted(os.listdir(INPUT_DIR)):
        if not fn.lower().endswith(".png"):
            continue
        in_path  = os.path.join(INPUT_DIR, fn)
        base     = os.path.splitext(fn)[0]
        out_path = os.path.join(OUTPUT_DIR, base + ".pdf")

        print(f"\n--- Traitement de {fn}")
        process_image_to_pdf(in_path, out_path)

if __name__ == "__main__":
    main()
