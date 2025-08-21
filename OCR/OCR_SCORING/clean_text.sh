#!/bin/bash
set -euo pipefail

# Usage: clean_text.sh input.txt output.txt
input="$1"
output="$2"
tmp1="${output%.txt}_step1.txt"
tmp2="${output%.txt}_step2.txt"

# 1) Retirer les césures (hyphénations) en fin de ligne
sed -E ':a; s/([[:alnum:]])-\n([[:alnum:]])/\1\2/; ta' \
  "$input" > "$tmp1"

# 2) Joindre les lignes d’un même paragraphe
awk '
  # si ligne vide → paragraphe terminé
  NF==0 { print ""; next }
  # sinon concatène les lignes
  { printf "%s ", $0 }
  END { print "" }
' "$tmp1" > "$tmp2"

# 3) Supprimer entêtes / pieds de page
# Ajoute ici tes regex pour repérer les formules récurrentes :
if [ -f regex_headers.txt ]; then
  grep -v -Ef regex_headers.txt "$tmp2" > "$output"
else
  # pas de filtre headers, on passe tel quel
  cp "$tmp2" "$output"
fi

# Cleanup
rm -f "$tmp1" "$tmp2"

echo "✅ Nettoyage post-OCR terminé : $output"