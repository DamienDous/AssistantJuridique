#!/bin/bash
set -euo pipefail

# Usage: clean_text.sh input.txt output.txt
in="$1"
out="$2"
tmp1="${out%.txt}_step1.txt"
tmp2="${out%.txt}_step2.txt"

# 1) Retirer les césures
sed -E ':a; s/([[:alnum:]])-\n([[:alnum:]])/\1\2/; ta' "$in" > "$tmp1"

# 2) Joindre les lignes d’un même paragraphe, en préservant
#    les fins de phrase (., !, ?) et en évitant les titres trop courts.
awk '
  NF==0 { print ""; next }
  prev=$0
  if (substr(prev, length(prev), 1) ~ /[.!?…]/ || NF(prev)<3) {
    print prev
  } else {
    printf "%s ", prev
  }
  END { print "" }
' "$tmp1" > "$tmp2"

# 3) Supprimer EN-TÊTES / PIEDS DE PAGE
#    chargez ici un fichier regex_headers.txt listant toutes vos formules à ignorer
grep -v -Ef regex_headers.txt "$tmp2" > "$out"

rm -f "$tmp1" "$tmp2"
echo "✅ Nettoyage post-OCR terminé : $out"
