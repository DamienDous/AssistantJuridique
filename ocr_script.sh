#!/bin/bash
set -euo pipefail

filename="$1"
inputFile="/data/$filename"
filename_noext=$(basename "$filename" .png)
base="/data/out/${filename_noext}"
tempBase="${base}_temp"
out_pdf_dir="/data/out/pdf"
out_txt_dir="/data/out/txt"
output_pdf="${out_pdf_dir}/${filename_noext}_final.pdf"
output_txt="${out_txt_dir}/${filename_noext}_final.txt"
mkdir -p "$out_pdf_dir" "$out_txt_dir"
log_dir="/data/logs"
mkdir -p "$log_dir"
fail_log="${log_dir}/ocr_fail.log"

{
echo "🟡 DÉBUT TRAITEMENT : $filename"
echo "filename     : $filename"
echo "inputFile    : $inputFile"
echo "base         : $base"
echo "tempBase     : $tempBase"
echo "output_pdf   : $output_pdf"
echo "output_txt   : $output_txt"

# if [ -f "$output_pdf" ]; then
#     echo "⚠️ PDF déjà existant : $output_pdf — on saute."
#     exit 0
# fi

if [ ! -f "$inputFile" ]; then
    echo "❌ PNG pas trouvé : $inputFile — on saute."
    exit 1
else
    echo "✅ Fichier PNG trouvé : $inputFile"
fi

mkdir -p "$tempBase"

# 1) Découpage par script Python
echo "📎 Découpage via Python..."
python3 /tools/read_and_crop.py "$inputFile" "${tempBase}/${filename_noext}" 1200

# 2) Liste les fichiers générés
sliced_images=($(ls ${tempBase}/${filename_noext}_*.png))

# 3) Nettoyage unpaper sur chaque image découpée
clean_dir="${tempBase}/clean"
mkdir -p "$clean_dir"
echo "🧹 Nettoyage unpaper des images découpées..."
cleaned_images=()
for img in "${sliced_images[@]}"; do
    img_clean="$clean_dir/$(basename "$img")"
    unpaper -v "$img" "$img_clean"
    cleaned_images+=("$img_clean")
done

# 3bis) Amélioration d'image avant OCR
improved_dir="${tempBase}/improved"
mkdir -p "$improved_dir"
echo "✨ Prétraitement d'image avant OCR (contrast, sharpen, threshold)..."
improved_images=()
for img in "${cleaned_images[@]}"; do
    improved_img="$improved_dir/$(basename "$img")"
    convert "$img" -resize 200% -colorspace Gray -contrast-stretch 0 -sharpen 0x1 -threshold 5% "$improved_img"
    improved_images+=("$improved_img")
done

# 4) OCR sur chaque image
echo "🔤 OCR sur chaque image prétraitée..."
for img in "${improved_images[@]}"; do
    ocrmypdf --force-ocr --image-dpi 400 --oversample 300 --tesseract-pagesegmode 6 -l fra "$img" "${img%.png}_ocr.pdf"
    if [ ! -f "${img%.png}_ocr.pdf" ]; then
        echo "❌ PDF OCR non créé pour $img"
    fi
done

# 5) Assemblage des PDF OCR en un seul fichier
echo "📚 Assemblage des PDF OCR en un seul fichier..."
ocr_pdfs=()
for img in "${sliced_images[@]}"; do
    ocr_pdf="${img%.png}_ocr.pdf"
    if [ -f "$ocr_pdf" ]; then
        ocr_pdfs+=("$ocr_pdf")
    fi
done
if [ ${#ocr_pdfs[@]} -eq 0 ]; then
    echo "❌ Aucun PDF OCR à assembler. Abandon."
    exit 3
fi
pdfunite "${ocr_pdfs[@]}" "$output_pdf"

# 6) Extraction du texte OCR depuis le PDF
raw_txt="${tempBase}/${filename_noext}_ocr.txt"
pdftotext "$output_pdf" "$raw_txt"

# 7) Nettoyage post-OCR avec clean_text.sh
clean_txt="${tempBase}/${filename_noext}_clean.txt"
echo "🧹 Étape 6 : Nettoyage post-OCR"
bash /tools/clean_text.sh "$raw_txt" "$clean_txt"

# 8) Correction avec LanguageTool
corr_txt="${tempBase}/${filename_noext}_corr.txt"
echo "🧠 Étape 7 : Correction avec LanguageTool"
python3 /tools/04_correction.py "$clean_txt" "$corr_txt"

# 9) Déplacement du txt final dans le dossier out/txt
mv "$corr_txt" "$output_txt"
echo "✅ TXT final créé : $output_txt"

# Nettoyage des dossiers temporaires
if [[ "$tempBase" == /data/out/* ]]; then
    echo "🧹 Suppression du dossier temporaire : $tempBase"
    rm -rf "$tempBase"
fi
echo "🏁 OCR terminé avec succès : $filename"

} || {
    echo "❌ ECHEC : $filename" >> "$fail_log"
    echo "💥 Une erreur est survenue pendant le traitement de $filename"
    exit 1
}

if [ ! -f "$output_pdf" ]; then
    echo "❌ PDF final manquant malgré OCR : $output_pdf" | tee -a "$fail_log"
    exit 1
fi

if [[ "$inputFile" == *.tmp.png ]]; then
    echo "🧹 Suppression de l’image redimensionnée temporaire : $inputFile"
    rm -f "$inputFile"
fi

trap 'echo "Une erreur est survenue lors du traitement $filename" >> "$fail_log"' ERR
