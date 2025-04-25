IMAGE_NAME = pipeline-ocr
INPUT_DIR = pipeline_OCR/traitement_lot/input_pdf
OUTPUT_DIR = pipeline_OCR/traitement_lot/output

# Détection de l'environnement Windows avec Git Bash pour support de pwd -W
ifdef ComSpec
	PWD_CMD := pwd -W
else
	PWD_CMD := pwd
endif

.PHONY: build
build:
	MSYS_NO_PATHCONV=1 docker build -t $(IMAGE_NAME) .

run:
ifndef FILE
	$(error ❌ Veuillez spécifier un nom de fichier PDF avec FILE=nom.pdf)
endif
# Étape 1 : on récupère le nom complet du PDF utilisateur
# Étape 2 : on enlève l’extension pour obtenir BASE
# Étape 3 : on “sanitise” BASE en CLEAN (ASCII, underscores)
# Étape 4 : on copie le PDF source vers INPUT_DIR/CLEAN.pdf
# Étape 5 : on exécute le pipeline OCR dans le container sur CLEAN.pdf
# Étape 6 : on renomme la sortie CLEAN_final_corrige.pdf en BASE_final_corrige.pdf
# Étape 7 : on supprime le PDF temporaire CLEAN.pdf et le dossier temp_CLEAN
	MSYS_NO_PATHCONV=1 docker run --rm \
		-v "$$($(PWD_CMD)):/app" \
		-v language_tool_cache:/root/.cache/language_tool_python \
		-w /app $(IMAGE_NAME) \
		sh -c '\
			ORIG="$$1"; \
			BASE="$${ORIG%.pdf}"; \
			CLEAN="$$(echo "$${BASE}" \
				| iconv -f UTF-8 -t ASCII//TRANSLIT \
				| sed -E "s/[^[:alnum:]]+/_/g")"; \
			cp "pipeline_OCR/traitement_lot/input_pdf/$${ORIG}" \
			   "pipeline_OCR/traitement_lot/input_pdf/$${CLEAN}.pdf"; \
			pipeline_OCR/pipelines/pipeline_base/pipeline_reconnaissance_text_pdf.sh \
				"pipeline_OCR/traitement_lot/input_pdf/$${CLEAN}.pdf" \
				"pipeline_OCR/traitement_lot/output/temp_$${CLEAN}"; \
			mv "pipeline_OCR/traitement_lot/output/$${CLEAN}_final_corrige.pdf" \
			   "pipeline_OCR/traitement_lot/output/$${BASE}_final_corrige.pdf"; \
			rm -f "pipeline_OCR/traitement_lot/input_pdf/$${CLEAN}.pdf"; \
			rm -rf  "pipeline_OCR/traitement_lot/output/temp_$${CLEAN}" \
		' _ "$(FILE)"

run-safe:
	@if [ "$$MSYSTEM" = "MINGW64" ] || [ "$$MSYSTEM" = "MSYS" ]; then \
		echo "❌ ERREUR : Ne pas exécuter ce Makefile depuis Git Bash. Utilise PowerShell ou CMD pour que Docker monte les volumes correctement."; \
		exit 1; \
	else \
		$(MAKE) run FILE="$(FILE)"; \
	fi
	
clean:
	MSYS_NO_PATHCONV=1 docker rmi $(IMAGE_NAME) || true

run-all:
	@for file in $(INPUT_DIR)/*.pdf; do \
		name=$$(basename "$$file"); \
		echo "▶️ Traitement de $$name..."; \
		make run FILE="$$name" || exit 1; \
	done

run-all-safe:
	@if [ "$$MSYSTEM" = "MINGW64" ] || [ "$$MSYSTEM" = "MSYS" ]; then \
		echo "❌ ERREUR : Ne pas exécuter ce Makefile depuis Git Bash. Utilise PowerShell ou CMD pour que Docker monte les volumes correctement."; \
		exit 1; \
	else \
		$(MAKE) run-all; \
	fi