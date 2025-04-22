from pathlib import Path
from PIL import Image

INPUT_TIFF_DIR = Path("input_tiff")
OUTPUT_PDF_DIR = Path("input_pdf")

OUTPUT_PDF_DIR.mkdir(exist_ok=True)

def convert_tiff_to_pdf(tiff_path, pdf_path):
    with Image.open(tiff_path) as img:
        rgb_img = img.convert("RGB")
        rgb_img.save(pdf_path, "PDF", resolution=300.0)

def main():
    for tiff_file in INPUT_TIFF_DIR.glob("*.tif"):
        pdf_file = OUTPUT_PDF_DIR / (tiff_file.stem + ".pdf")
        print(f"🌀 Conversion : {tiff_file.name} → {pdf_file.name}")
        convert_tiff_to_pdf(tiff_file, pdf_file)

if __name__ == "__main__":
    main()
