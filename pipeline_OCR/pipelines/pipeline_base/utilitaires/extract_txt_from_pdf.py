import fitz  # PyMuPDF
from pathlib import Path

REFERENCE_PDF_DIR = Path("reference_pdf")
REFERENCE_TXT_DIR = Path("reference_txt")

REFERENCE_TXT_DIR.mkdir(exist_ok=True)

def extract_text_from_pdf(pdf_path, txt_path):
    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(full_text)

def main():
    for pdf_file in REFERENCE_PDF_DIR.glob("*.pdf"):
        txt_name = pdf_file.with_suffix(".txt").name
        txt_path = REFERENCE_TXT_DIR / txt_name
        print(f"📝 Extraction texte : {pdf_file.name} → {txt_path.name}")
        extract_text_from_pdf(pdf_file, txt_path)

if __name__ == "__main__":
    main()
