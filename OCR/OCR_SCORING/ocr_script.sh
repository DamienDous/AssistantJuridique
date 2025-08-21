#!/bin/bash
set -euo pipefail
echo ">>> DEBUT ocr_script.sh avec $1" >> /tmp/ocr_debug.log

IMAGE_MAGICK_ARGS="${IMAGE_MAGICK_ARGS:-'-resize 200% -colorspace Gray -sharpen 0x1 -normalize -auto-threshold Otsu'}"
input_file="$1"
output_folder="$2"

filename_noext=$(basename "$input_file" .png)
output_pdf="${output_folder}/${filename_noext}.pdf"
output_txt="${output_folder}/${filename_noext}.txt"

{
echo "🟡 DÉBUT TRAITEMENT : $input_file → $output_pdf ($IMAGE_MAGICK_ARGS)"

if [ -f "$output_pdf" ]; then
    echo "⚠️ PDF déjà existant : $output_pdf — on saute."
    exit 0
fi

if [ ! -f "$input_file" ]; then
    echo "❌ PNG pas trouvé : $input_file — on saute."
    exit 1
else
    echo "✅ Fichier PNG trouvé : $input_file"
fi

# 1) Découpage par script Python
echo "📎 Découpage via Python..."
ini_dir="${output_folder}/ini"
mkdir -p "$ini_dir"
python3 /tools/read_and_crop.py "$input_file" "${ini_dir}/img" 1200
# Liste les fichiers générés
sliced_images=($(ls ${ini_dir}/img_*.png))

# 3) Amélioration d'image avant OCR
echo "magick version : $(magick --version)"
echo "✨ Prétraitement d'image avant OCR (contrast, sharpen, threshold)..."
improved_dir="${output_folder}/improved"
mkdir -p "$improved_dir"
improved_images=()
for img in "${sliced_images[@]}"; do
    improved_img="$improved_dir/$(basename "$img")"
    magick "$img" $IMAGE_MAGICK_ARGS "$improved_img"
    improved_images+=("$improved_img")
done

# 4) OCR sur chaque image
echo "🔤 OCR sur chaque image prétraitée..."
ocr_dir="${output_folder}/ocr"
mkdir -p "$ocr_dir"
ocr_pdfs=()
for img in "${improved_images[@]}"; do
    ocr_pdf="$ocr_dir/$(basename "${img%.png}_ocr.pdf")"
    ocrmypdf --force-ocr --image-dpi 400 --oversample 300 --tesseract-pagesegmode 6 -l fra "$img" "$ocr_pdf"
    if [ ! -f "${ocr_pdf}" ]; then
        echo "❌ PDF OCR non créé pour $img"
    fi
    ocr_pdfs+=("$ocr_pdf")
done

# 5) Assemblage des PDF OCR en un seul fichier
echo "📚 Assemblage des PDF OCR en un seul fichier..."
if [ ${#ocr_pdfs[@]} -eq 0 ]; then
    echo "❌ Aucun PDF OCR à assembler. Abandon."
    exit 3
fi
pdfunite "${ocr_pdfs[@]}" "$output_pdf"

# 6) Extraction du texte OCR depuis le PDF
raw_txt="${output_folder}/${filename_noext}_ocr.txt"
pdftotext "$output_pdf" "$raw_txt"

# 7) Nettoyage post-OCR avec clean_text.sh
clean_txt="${output_folder}/${filename_noext}_clean.txt"
echo "🧹 Étape 6 : Nettoyage post-OCR"
bash /tools/clean_text.sh "$raw_txt" "$clean_txt"

# 8) Correction avec LanguageTool
# corr_txt="${output_folder}/${filename_noext}_corr.txt"
# echo "🧠 Étape 7 : Correction avec LanguageTool"
# python3 /tools/langage_tool_correction.py "$clean_txt" "$corr_txt"

# 9) Déplacement du txt final dans le dossier out/txt
mv "$raw_txt" "$output_txt"
echo "✅ TXT final créé : $output_txt"

# Nettoyage des dossiers temporaires
# if [[ "$output_folder" == /data/out/* ]]; then
#     echo "🧹 Suppression du dossier temporaire : $output_folder"
#     rm -rf "$output_folder"
# fi
echo "🏁 OCR terminé avec succès : $output_txt"

} || {
    echo "❌ ECHEC : $output_txt"
    echo "💥 Une erreur est survenue pendant le traitement de $output_txt"
    exit 1
}

if [ ! -f "$output_pdf" ]; then
    echo "❌ PDF final manquant malgré OCR : $output_pdf"
    exit 1
fi

trap 'echo "Une erreur est survenue lors du traitement $filename" >> "$fail_log"' ERR
echo ">>> FIN ocr_script.sh avec $1" >> /tmp/ocr_debug.log