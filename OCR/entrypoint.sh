#!/bin/bash
set -euo pipefail

# 1. Lance LanguageTool server en arrière-plan
echo "🧠 Démarrage LanguageTool serveur..."
java -cp /tools/lt/LanguageTool-6.4/languagetool-server.jar org.languagetool.server.HTTPServer --port 8010 --allow-origin '*' &
LT_PID=$!

# 2. Attend que le serveur démarre
sleep 2

# 3. Lance ton batch OCR (adapte cette ligne à ton cas)
echo "🚀 Lancement du batch OCR sur /data"

ls /data/*.png | xargs -P 20 -I {} bash /tools/ocr_script.sh {}

# 4. (optionnel) Attend la fin et arrête LanguageTool proprement
kill $LT_PID
