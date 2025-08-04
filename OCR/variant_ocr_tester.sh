#!/bin/bash
set -uo pipefail

# Usage: ./batch_ocr_tester.sh <input_folder> <output_folder> <max_parallel>
input_folder="${1:-/data}"               # Dossier source des .png
output_folder="${2:-/data}"              # Dossier destination des .png
max_parallel="${3:-20}"                  # Nombre max de jobs en parallèle

docker_img="pipeline-ocr"               # Change le nom si besoin

shopt -s nullglob

result_folder="/data/result"
mkdir -p "$result_folder"

# 1. Liste de variantes à tester (tableau bash)
MAGICK_VARIANTS=(
    "-resize 200% -colorspace Gray -normalize -auto-threshold Otsu"
    "-resize 200% -colorspace Gray -sharpen 0x4 -auto-threshold Otsu"
    "-resize 200% -colorspace Gray -sharpen 0x0.2 -auto-threshold Otsu"
    "-resize 200% -colorspace Gray -normalize -contrast -auto-threshold Otsu"
    "-resize 200% -colorspace Gray -despeckle -auto-threshold Otsu"
    "-resize 200% -colorspace Gray -blur 1x1 -auto-threshold Otsu"
    "-resize 200% -colorspace Gray -auto-gamma -auto-threshold Otsu"
    "-resize 200% -colorspace Gray -auto-level -lat 240x240+8% -normalize"
)
active_jobs=0

for pdf in "$input_folder"/*.pdf; do
  # Nom de base sans extension
  base=$(basename "$pdf" .pdf)
  # Conversion : 1 image PNG par page, nommé base-pageNUM.png
  pdftoppm -png -r 300 "$pdf" "$input_folder/${base}"
  echo "✔️ $pdf converti"
done

all_files=("$input_folder"/*.png)
echo "📁 ${#all_files[@]} fichiers trouvés dans : $input_folder"

cat <<EOF > /data/out/score_final.csv
fichier,wer,cer,nb_mots_ref,nb_mots_ocr,ratio_mots,nb_paragraphes_ref,nb_paragraphes_ocr,ratio_paragraphes,\
nb_maj_ref,nb_maj_ocr,ratio_maj,nb_points_ref,nb_points_ocr,ratio_points,nb_exclam_ref,nb_exclam_ocr,ratio_exclam,\
nb_quest_ref,nb_quest_ocr,ratio_quest,ratio_punct_ref,ratio_punct_ocr,ratio_punct_ratio,score_global,parametres_traitement
EOF

# 2. Pour chaque fichier...
for f in "${all_files[@]}"; do
  (
    filename_noext=$(basename "$f" .png)
    # Pour chaque variante...
    for idx in "${!MAGICK_VARIANTS[@]}"; do
        variant="${MAGICK_VARIANTS[$idx]}"
        export IMAGE_MAGICK_ARGS="$variant"

        output_txt="${output_folder}/${filename_noext}/${filename_noext}_${idx}/${filename_noext}.txt"

        # Si déjà fait, on saute
        if [[ -f "$output_txt" ]]; then
          echo "⏭️  Déjà traité : $output_txt"
          continue
        fi

        mkdir -p "$output_folder/${filename_noext}/${filename_noext}_${idx}/"
        echo "🚀 OCR sur $(basename "$f") [VARIANTE $idx] : $variant"
        
        # Lancement de l'ocrisation
        IMAGE_MAGICK_ARGS="$variant" bash /tools/ocr_script.sh "$f" "$output_folder/${filename_noext}/${filename_noext}_${idx}/"

        # Récupère le fichier
        echo "⏭️  fichier cherché : $(basename "$f") idx $idx"
        variant="${MAGICK_VARIANTS[$idx]}"

        # Comparaison avec le texte de référence
        ref_txt="/data/reference/${filename_noext}.txt"
        if [[ -f "$output_txt" && -f "$ref_txt" ]]; then
            python3 /tools/score_ocr.py "$output_txt" "$ref_txt" | \
            awk -v variant="$variant" '{print $0 "," variant}' >> /data/out/score_final.csv
        else
            echo  "$ref_txt non trouvé"
        fi
    done
  ) &
  ((active_jobs++))
  if (( active_jobs >= max_parallel )); then
    wait -n
    ((active_jobs--))
  fi
done
wait
echo "✅ OCR Voting terminé pour tous les fichiers."
echo "✅ Tous les fichiers ont été traités."
