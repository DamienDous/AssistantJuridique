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
# 1) Initialisation des variables
# 2) Copie du PDF d’origine sous son nom sanitizé dans input_pdf
# 3) Création du dossier output s’il n’existe pas
# 4) Exécution du pipeline OCR dans le conteneur
# 5) Renommage du PDF final déjà créé par le pipeline
# 6) Nettoyage : suppression du PDF temporaire et du dossier temp_$$CLEAN
ifndef FILE
	$(error ❌ Veuillez spécifier un nom de fichier PDF avec FILE=nom.pdf)
endif
	MSYS_NO_PATHCONV=1 docker run --rm \
		-v "$$($(PWD_CMD)):/app" \
		-v language_tool_cache:/root/.cache/language_tool_python \
		-w /app $(IMAGE_NAME) bash -lc '\
		ORIG="$(FILE)"; \
		BASE=$$(basename "$$ORIG" .pdf); \
		CLEAN=$$(echo "$$BASE" | iconv -f UTF-8 -t ASCII//TRANSLIT | sed -e "s/[^A-Za-z0-9._-]/_/g"); \
		echo "=== DEBUG INTERNAL: ORIG=$$(echo "$$BASE")  CLEAN=$$(echo "$$CLEAN") ==="; \
		cp pipeline_OCR/traitement_lot/input_pdf/$$ORIG \
			pipeline_OCR/traitement_lot/input_pdf/$$CLEAN.pdf; \
		mkdir -p pipeline_OCR/traitement_lot/output; \
		pipeline_OCR/pipelines/pipeline_base/pipeline_reconnaissance_text_pdf.sh \
			"pipeline_OCR/traitement_lot/input_pdf/$$CLEAN.pdf" \
			"pipeline_OCR/traitement_lot/output/temp_$$CLEAN"; \
		echo "=== DEBUG INTERNAL: ORIG='$$BASE_final_corrige.pdf'  CLEAN='$$CLEAN_final_corrige.pdf' ==="; \
		mv pipeline_OCR/traitement_lot/output/$$(echo "$$CLEAN")_final_corrige.pdf \
			pipeline_OCR/traitement_lot/output/$$(echo "$$BASE")_final_corrige.pdf; \
		rm -f pipeline_OCR/traitement_lot/input_pdf/$$CLEAN.pdf; \
		rm -rf pipeline_OCR/traitement_lot/output/temp_$$CLEAN'

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