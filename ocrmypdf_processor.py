import subprocess
import os
import img2pdf

def ocrmypdf_process(input_pdf, ocr_pdf):
	subprocess.run([
		"ocrmypdf",
		"--force-ocr",
		"--oversample", "300",
		"--language", "fra",
		"--tesseract-pagesegmode", "3",
		input_pdf,
		ocr_pdf
	], check=True)

if __name__ == "__main__":
	# Correction : bien séparer le chemin du dossier et le nom du fichier
	filename = "fr-document-3a-lyon-lecole-internationale-du-management-responsable-organisation-de-la-justice-td-n04-de-droit-constitutionnel.png"
	input_png = os.path.join("DB/cleaned_png_3000", filename)

	# Fichiers de sortie
	input_pdf = input_png.replace(".png", "_cleaned.pdf")
	ocr_pdf = input_png.replace(".png", "_ocr.pdf")

	print("➡️ PDF temporaire :", input_pdf)
	print("➡️ PDF OCR final :", ocr_pdf)

	# Étape 1 : conversion image -> PDF
	with open(input_pdf, "wb") as f:
		f.write(img2pdf.convert([input_png]))  # <-- liste avec un seul chemin

	# Étape 2 : OCR
	print("🔠 Étape 2 : OCR et génération PDF searchable avec ocrmypdf")
	ocrmypdf_process(input_pdf, ocr_pdf)
	print(f"✅ PDF OCR généré : {ocr_pdf}")