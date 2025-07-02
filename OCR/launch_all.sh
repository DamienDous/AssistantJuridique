#!/bin/bash
set -uo pipefail
set -x

# 1. Lancer LanguageTool
echo "🧠 Démarrage LanguageTool serveur..."
for port in {8010..8017}; do
  java -cp /tools/lt/LanguageTool-6.4/languagetool-server.jar org.languagetool.server.HTTPServer --port $port --allow-origin '*' &
done

LT_PID=""
cleanup() {
    echo "⏹️ Arrêt LanguageTool..."
    [ -n "$LT_PID" ] && kill $LT_PID
    kill $LT_PID 2>/dev/null || true
}
trap cleanup EXIT

# Attendre que LanguageTool soit prêt
for i in {1..20}; do
    if curl -s http://localhost:8010/v2/languages >/dev/null; then
        echo "✅ LanguageTool est prêt."
        break
    fi
    sleep 1
done

# 2. Lancer ton batch OCR (qui NE lance PLUS LanguageTool !)
bash /tools/batch_ocr_tester.sh "$@"

# 3. Stopper LanguageTool proprement
echo "⏹️ Arrêt LanguageTool..."
kill $LT_PID
