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
	@mkdir -p $(OUTPUT_DIR)
	MSYS_NO_PATHCONV=1 docker run --rm \
		-v language_tool_cache:/root/.cache/language_tool_python \
		$(IMAGE_NAME) \
		pipeline_OCR/pipelines/pipeline_base/pipeline_reconnaissance_text_pdf.sh \
		$(INPUT_DIR)/$(FILE) \
		$(OUTPUT_DIR)/temp_$(basename $(FILE) .pdf)

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