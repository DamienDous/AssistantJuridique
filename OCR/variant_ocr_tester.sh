#!/bin/bash
set -uo pipefail

# Usage: ./batch_ocr_tester.sh <input_folder> <output_folder> <max_parallel>
input_folder="${1:-/data}"               # Dossier source des .png
output_folder="${2:-/data}"              # Dossier destination des .png
max_parallel="${3:-20}"                  # Nombre max de jobs en parallèle
# Dossier où sont stockés les TXT de référence générés à partir des JSON
ref_dir="${4:-/data/ref}"   # Par défaut /data/ref ou passe-le en argument

docker_img="pipeline-ocr"               # Change le nom si besoin

shopt -s nullglob

result_folder="/data/result"
mkdir -p "$result_folder"

# 1. Liste de variantes à tester (tableau bash)
MAGICK_VARIANTS=(	# "-resize 200% -colorspace Gray -normalize -lat 240x240+8%"
	# "-resize 200% -colorspace Gray -normalize -equalize -auto-threshold Otsu"
	# "-resize 200% -colorspace Gray -enhance -lat 240x240+8%"
	"-resize 200% -colorspace Gray -normalize -background white -flatten"
	"-resize 200% -colorspace Gray -normalize -auto-threshold Otsu"
	"-resize 200% -colorspace Gray -normalize -sharpen 0x1 -auto-threshold Otsu"
	"-resize 200% -colorspace Gray -contrast-stretch 0.3%x0.3% -auto-threshold Otsu"
	"-resize 200% -colorspace Gray -normalize -sharpen 0x2 -despeckle -auto-threshold Otsu"
	"-resize 200% -colorspace Gray -deskew 40% -normalize -auto-threshold Otsu"
	"-resize 200% -colorspace Gray -white-threshold 80% -normalize -auto-threshold Otsu"
	"-resize 200% -colorspace Gray -normalize -enhance"
    "-resize 200% -colorspace Gray -auto-level -sharpen 0x1"
    "-resize 200% -colorspace Gray -blur 1x1 -auto-threshold Otsu"
    "-resize 200% -colorspace Gray -median 3 -normalize"
    "-resize 200% -colorspace Gray -normalize -auto-threshold Triangle"
    "-resize 200% -colorspace Gray -auto-gamma -auto-threshold Otsu"
    "-resize 200% -colorspace Gray -normalize -adaptive-sharpen 0x2 -auto-threshold Otsu"
    "-resize 200% -colorspace Gray -normalize -deskew 40% -auto-threshold Otsu"
    "-resize 200% -colorspace Gray -auto-level -normalize -auto-threshold Otsu"
)
active_jobs=0

# for pdf in "$input_folder"/*.pdf; do
#   # Nom de base sans extension
#   base=$(basename "$pdf" .pdf)
#   # Conversion : 1 image PNG par page, nommé base-pageNUM.png
#   pdftoppm -png -r 300 "$pdf" "$input_folder/${base}"
#   echo "✔️ $pdf converti"
# done

all_files=("$input_folder"/*.png)
echo "📁 ${#all_files[@]} fichiers trouvés dans : $input_folder"
selected_files=($(printf "%s\n" "${all_files[@]}" | shuf | head -n 100))

csv_file="/data/out/score_final.csv"
if [ ! -f "$csv_file" ]; then
	cat <<EOF > "$csv_file"
fichier,cat,cer,jacc_multi,ratios_mean,parametres_traitement
EOF
fi

# 2. Pour chaque fichier...
for f in "${selected_files[@]}"; do
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

		ref_txt="$ref_dir/${filename_noext}.txt"
		cat_txt="$ref_dir/${filename_noext}_cat.txt"
		json="$ref_dir/${filename_noext}.json"
		echo "⏭️  fichier json : $json"
		if [[ -f "$json" ]]; then
			python3 -c "import json; d=json.load(open('$json', encoding='utf-8')); open('$ref_txt','w',encoding='utf-8').write('\n'.join(cell['text'] for cell in d.get('cells',[]) if cell.get('text'))); open('$cat_txt','w',encoding='utf-8').write(d.get('metadata',{}).get('doc_category','unknown'))"
		else
			echo "⏭️  Pas de json trouvée pour $filename_noext"
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
		if [[ -f "$output_txt" && -f "$ref_txt" ]]; then
			python3 /tools/score_ocr.py "$output_txt" "$ref_txt" "$cat_txt"| \
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
