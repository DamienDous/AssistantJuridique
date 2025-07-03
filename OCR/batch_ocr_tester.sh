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

# 2. Pour chaque fichier...
for f in "${all_files[@]}"; do
  # Pour chaque variante...
  for idx in "${!MAGICK_VARIANTS[@]}"; do
    variant="${MAGICK_VARIANTS[$idx]}"
    export IMAGE_MAGICK_ARGS="$variant"

    filename_noext=$(basename "$f" .png)
    output_pdf="${output_folder}/${filename_noext}_${idx}/${filename_noext}.pdf"

    # Si déjà fait, on saute
    if [[ -f "$output_pdf" ]]; then
      echo "⏭️  Déjà traité : $output_pdf"
      continue
    fi

    mkdir -p "$output_folder/${filename_noext}_${idx}/"

    echo "🚀 OCR sur $(basename "$f") [VARIANTE $idx] : $variant"
    
    # Lancement en background (parallelisation bash native)
    (IMAGE_MAGICK_ARGS="$variant" bash /tools/ocr_script.sh "$f" "$output_folder/${filename_noext}_${idx}/") &

    ((active_jobs++))
    if (( active_jobs >= max_parallel )); then
      wait -n
      ((active_jobs--))
    fi
  done
done
wait

# Attend la fin de tous les jobs restants
# wait

echo "fichier,variant,nb_fautes,nb_caracteres,ratio" > /data/out/scoring_languagetool.csv

active_jobs=0
for f in "${all_files[@]}"; do
  for idx in "${!MAGICK_VARIANTS[@]}"; do
    (
      echo "⏭️  fichier cherché : $(basename "$f") idx $idx"
      variant="${MAGICK_VARIANTS[$idx]}"
      filename_noext=$(basename "$f" .png)
      output_txt="${output_folder}/${filename_noext}_${idx}/${filename_noext}.txt"

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
      {
        echo "$(basename "$output_txt"),$variant,$nb_fautes,$nb_carac,$ratio"
      } >> /data/out/scoring_languagetool.csv

    ) &

    ((active_jobs++))
    if (( active_jobs >= max_parallel )); then
      wait -n
      ((active_jobs--))
    fi
  done
done

wait # attend la fin de tous les jobs restants
echo "✅ Comparatif LanguageTool écrit dans /data/out/scoring_languagetool.csv"

# Extraire toutes les variantes uniques
cut -d, -f2 /data/out/scoring_languagetool.csv | sort | uniq > /data/out/variantes.txt

# Extraire toutes les variantes uniques (en ignorant la première ligne d'entête)
tail -n +2 /data/out/scoring_languagetool.csv | cut -d, -f2 | sort | uniq > /data/out/variantes.txt

# Pour chaque variante, calcule la moyenne et l’écart-type du ratio sur tous les fichiers
while read variante; do
  # On sélectionne uniquement les lignes correspondant à la variante
  ratios=$(awk -F, -v v="$variante" '$2==v{print $5}' /data/out/scoring_languagetool.csv)
  n=$(echo "$ratios" | wc -l)
  moyenne=$(echo "$ratios" | awk '{sum+=$1} END{if(NR>0) print sum/NR; else print "NaN"}')
  # On calcule l'écart-type
  std=$(echo "$ratios" | awk -v m="$moyenne" '{s+=($1-m)^2} END{if(NR>1) print sqrt(s/(NR-1)); else print 0}')
  echo -e "$variante\t$n\t$moyenne\t$std"
done < /data/out/variantes.txt | sort -k4 -nr > /data/out/stats_variantes.txt

echo "### Démarrage du vote OCR par ligne/paragraphe pour chaque fichier ###"

# Pour chaque fichier source (par exemple image001.png → image001_*.txt)
for f in "${all_files[@]}"; do
  filename_noext=$(basename "$f" .png)
  # On construit la liste des .txt pour toutes les variantes de ce fichier
  variant_txts=()
  for idx in "${!MAGICK_VARIANTS[@]}"; do
    tfile="${output_folder}/${filename_noext}_${idx}/${filename_noext}.txt"
    [[ -f "$tfile" ]] && variant_txts+=("$tfile")
  done

  # Si on a au moins deux variantes (sinon pas de vote pertinent)
  if (( ${#variant_txts[@]} >= 2 )); then
    output_vote="${output_folder}/${filename_noext}_vote.txt"
    echo "🗳️ Vote OCR pour $filename_noext (${#variant_txts[@]} variantes)"
    python3 /tools/vote_ocr_clustal.py "${variant_txts[@]}" "$output_vote"
  else
    echo "⚠️ Pas assez de variantes OCR pour $filename_noext, vote ignoré"
  fi
done

for f in "${all_files[@]}"; do
  filename_noext=$(basename "$f" .png)
  output_vote="${output_folder}/${filename_noext}_vote.txt"
  if [[ -f "$output_vote" ]]; then
    nb_carac=$(wc -m < "$output_vote")
    nb_fautes=$(curl -s --data-urlencode "text=$(cat "$output_vote")" \
      --data "language=fr" \
      "http://localhost:8010/v2/check" | jq '.matches | length')
    ratio=$(awk "BEGIN {if ($nb_carac>0) print $nb_fautes/$nb_carac; else print \"NaN\"}")
    echo "${filename_noext}_vote.txt,VOTE,$nb_fautes,$nb_carac,$ratio" >> /data/out/scoring_languagetool.csv
  fi
done

echo "✅ OCR Voting terminé pour tous les fichiers."

echo "✅ Tous les fichiers ont été traités."
