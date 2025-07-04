#!/bin/bash
set -uo pipefail

# Usage: ./batch_ocr_tester.sh <input_folder> <output_folder> <max_parallel>
input_folder="${1:-/data}"              # Dossier source des .png
output_folder="${2:-/data}"              # Dossier destination des .png
max_parallel="${3:-20}"                  # Nombre max de jobs en parallèle

docker_img="pipeline-ocr"               # Change le nom si besoin

shopt -s nullglob
all_files=("$input_folder"/*.png)
echo "📁 ${#all_files[@]} fichiers trouvés dans : $input_folder"
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

echo "fichier,variant,nb_fautes,nb_caracteres,ratio" > /data/out/scoring_languagetool.csv
# 2. Pour chaque fichier...
for f in "${all_files[@]}"; do
  (
    filename_noext=$(basename "$f" .png)
    # Pour chaque variante...
    for idx in "${!MAGICK_VARIANTS[@]}"; do
        variant="${MAGICK_VARIANTS[$idx]}"
        export IMAGE_MAGICK_ARGS="$variant"

        output_pdf="${output_folder}/${filename_noext}/${filename_noext}_${idx}/${filename_noext}.pdf"

        # Si déjà fait, on saute
        if [[ -f "$output_pdf" ]]; then
          echo "⏭️  Déjà traité : $output_pdf"
          continue
        fi

        mkdir -p "$output_folder/${filename_noext}/${filename_noext}_${idx}/"
        echo "🚀 OCR sur $(basename "$f") [VARIANTE $idx] : $variant"
        
        # Lancement de l'ocrisation
        IMAGE_MAGICK_ARGS="$variant" bash /tools/ocr_script.sh "$f" "$output_folder/${filename_noext}/${filename_noext}_${idx}/"

        # Récupère le fichier
        echo "⏭️  fichier cherché : $(basename "$f") idx $idx"
        variant="${MAGICK_VARIANTS[$idx]}"
        output_txt="${output_folder}/${filename_noext}/${filename_noext}_${idx}/${filename_noext}.txt"

        if [[ ! -f "$output_txt" ]]; then
          echo "⏭️  Pas trouvé : $output_txt"
          exit 0
        fi

        nb_carac=$(wc -m < "$output_txt")
        nb_fautes=$(curl -s --data-urlencode "text=$(cat "$output_txt")" \
            --data "language=fr" \
            "http://localhost:8010/v2/check" | jq '.matches | length')

        # Attention division entière en Bash, utilise bc pour float
        ratio=$(awk "BEGIN {if ($nb_carac>0) print $nb_fautes/$nb_carac; else print \"NaN\"}")
        # Utilise flock pour éviter les collisions d’écriture
        flock /data/out/scoring_languagetool.csv bash -c \
        "echo \"$(basename "$output_txt"),$variant,$nb_fautes,$nb_carac,$ratio\" >> /data/out/scoring_languagetool.csv"
    done  

    # On construit la liste des .txt pour toutes les variantes de ce fichier
    variant_txts=()
    for idx in "${!MAGICK_VARIANTS[@]}"; do
      tfile="${output_folder}/${filename_noext}/${filename_noext}_${idx}/${filename_noext}.txt"
      [[ -f "$tfile" ]] && variant_txts+=("$tfile")
    done

    # Si on a au moins deux variantes (sinon pas de vote pertinent)
    if (( ${#variant_txts[@]} >= 2 )); then
      vote_txt="${output_folder}/${filename_noext}/${filename_noext}_vote.txt"
      echo "🗳️ Vote OCR pour $filename_noext (${#variant_txts[@]} variantes)"
      python3 /tools/vote_ocr_paragraphe.py "${variant_txts[@]}" "$vote_txt"
    else
      echo "⚠️ Pas assez de variantes OCR pour $filename_noext, vote ignoré"
    fi

    vote_txt="${output_folder}/${filename_noext}/${filename_noext}_vote.txt"
    if [[ -f "$vote_txt" ]]; then
    vote_txt_clean="${output_folder}/${filename_noext}/${filename_noext}_vote_clean.txt"
      python3 /tools/ocr_postprocess_all.py "$vote_txt" "$vote_txt_clean" --languagetool --log_corrections "${output_folder}/corrections_languagetool.csv"
      cp "$vote_txt_clean" "$result_folder" # copie dans le fichier input du résultat
      nb_carac=$(wc -m < "$vote_txt_clean")
      nb_fautes=$(curl -s --data-urlencode "text=$(cat "$vote_txt_clean")" \
        --data "language=fr" \
        "http://localhost:8010/v2/check" | jq '.matches | length')
      ratio=$(awk "BEGIN {if ($nb_carac>0) print $nb_fautes/$nb_carac; else print \"NaN\"}")
      flock /data/out/scoring_languagetool.csv bash -c \
       "echo \"$filename_noext,$variant,$nb_fautes,$nb_carac,$ratio\" >> /data/out/scoring_languagetool.csv"
    fi
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
