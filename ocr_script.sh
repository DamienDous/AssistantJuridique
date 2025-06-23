#!/bin/bash
set -e

filename="$1"
inputFile="/data/$filename"
filename_noext=$(basename "$filename" .png)
base="/data/out/${filename_noext}"
tempBase="${base}_temp"
output_pdf="${base}_final.pdf"
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

# Ne pas retraiter si le PDF final existe
if [ -f "$output_pdf" ]; then
    echo "⚠️ PDF déjà existant : $output_pdf — on saute."
    exit 0
fi

if [ ! -f "$inputFile" ]; then
    echo "❌ PNG pas trouvé : $inputFile — on saute."
    exit 1
else
    echo "✅ Fichier PNG trouvé : $inputFile"
fi

mkdir -p "$tempBase"

# Découpage par script Python
echo "📎 Découpage via Python..."
python3 /tools/read_and_crop.py "$inputFile" "${tempBase}/${filename_noext}" 1200

# Liste les fichiers générés
sliced_images=($(ls ${tempBase}/${filename_noext}_*.png))

# OCR sur chaque image
for img in "${sliced_images[@]}"; do
    echo "🔤 OCR sur $img..."
    ocrmypdf --force-ocr --image-dpi 200 --oversample 300 --tesseract-pagesegmode 3 -l fra+eng "$img" "${img%.png}_ocr.pdf"
done

echo "📚 Assemblage des PDF OCR en un seul fichier..."
pdfunite "${tempBase}/${filename_noext}"_*_ocr.pdf "$output_pdf"

echo "✅ PDF final créé : $output_pdf"

# Nettoyage du dossier temporaire
if [ -d "$tempBase" ]; then
    echo "🧹 Suppression du dossier temporaire : $tempBase"
    rm -rf "$tempBase"
fi

echo "🏁 OCR terminé avec succès : $filename"

} || {
    echo "❌ ECHEC : $filename" >> "$fail_log"
    echo "💥 Une erreur est survenue pendant le traitement de $filename"
    exit 1
}

# Vérification finale
if [ ! -f "$output_pdf" ]; then
    echo "❌ PDF final manquant malgré OCR : $output_pdf" | tee -a "$fail_log"
    exit 1
fi

# Nettoyage du resize temporaire s’il existe
if [[ "$inputFile" == *.tmp.png ]]; then
    echo "🧹 Suppression de l’image redimensionnée temporaire : $inputFile"
    rm -f "$inputFile"
fi