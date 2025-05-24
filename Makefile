IMAGE_NAME = pipeline-ocr
INPUT_DIR = pipeline_OCR/traitement_lot/input_png
OUTPUT_DIR = pipeline_OCR/traitement_lot/output


# Détection de l'environnement Windows avec Git Bash pour support de pwd -W
# ifdef ComSpec
# 	PWD_HOST := $(shell cd)
# else
# 	PWD_HOST := pwd
# endif

.PHONY: build
build:
	docker build -t $(IMAGE_NAME) .

# debug-path:
# 	@echo "PWD_HOST = $(PWD_HOST)"
# 	@echo "CURDIR = $(CURDIR)"
	
# Étape 1 : on récupère le nom complet du PNG utilisateur
# Étape 2 : on enlève l’extension pour obtenir BASE
# Étape 3 : on “sanitise” BASE en CLEAN (ASCII, underscores)
# Étape 4 : on copie le PNG source vers INPUT_DIR/CLEAN.png
# Étape 5 : on exécute le pipeline OCR dans le container sur CLEAN.png
# Étape 6 : on renomme la sortie CLEAN_final_corrige.png en BASE_final_corrige.png
# Étape 7 : on supprime le PNG temporaire CLEAN.png et le dossier temp_CLEAN
run:
ifndef FILE
	$(error ❌ Veuillez spécifier un nom de fichier PNG avec FILE=nom.png)
endif
	docker run --rm \
		-v "$(CURDIR):/app" \
		-v language_tool_cache:/root/.cache/language_tool_python \
		-w /app $(IMAGE_NAME) \
		sh -c '\
			ORIG="$$1"; \
			ORIG="$$(basename "$${ORIG}")"; \
			BASE="$${ORIG%.png}"; \
			CLEAN="$$(echo "$${BASE}" | iconv -f UTF-8 -t ASCII//TRANSLIT | sed -E "s/[^[:alnum:]]+/_/g")"; \
			mkdir -p "pipeline_OCR/traitement_lot/input_png/$${CLEAN}"; \
			cp "pipeline_OCR/traitement_lot/input_png/$${ORIG}" \
			   "pipeline_OCR/traitement_lot/input_png/$${CLEAN}/image.png"; \
			pipeline_OCR/pipelines/pipeline_base/pipeline_reconnaissance_text_pdf.sh \
			   "pipeline_OCR/traitement_lot/input_png/$${CLEAN}" \
			   "pipeline_OCR/traitement_lot/output/$${CLEAN}"; \
			rm -rf "pipeline_OCR/traitement_lot/input_png/$${CLEAN}"; \
			rm -rf "pipeline_OCR/traitement_lot/output/$${CLEAN}" \
		' _ "$(FILE)"

run-safe:
	@if [ "$$MSYSTEM" = "MINGW64" ] || [ "$$MSYSTEM" = "MSYS" ]; then \
		echo "❌ ERREUR : Ne pas exécuter ce Makefile depuis Git Bash. Utilise PowerShell ou CMD pour que Docker monte les volumes correctement."; \
		exit 1; \
	else \
		$(MAKE) run FILE="$(FILE)"; \
	fi
	
clean:
	docker rmi $(IMAGE_NAME) || true

run-all:
	@cmd /V:ON /C "for %%f in ($(INPUT_DIR)\*.png) do ( \
		echo ▶️ Traitement de %%~nxf... && \
		$(MAKE) run FILE=%%~nxf || exit /b 1 \
	)"
run-all-safe:
	@if [ "$$MSYSTEM" = "MINGW64" ] || [ "$$MSYSTEM" = "MSYS" ]; then \
		echo "❌ ERREUR : Ne pas exécuter ce Makefile depuis Git Bash. Utilise PowerShell ou CMD pour que Docker monte les volumes correctement."; \
		exit 1; \
	else \
		$(MAKE) run-all; \
	fi

# Lancer le scraping Studocu (CSV obligatoire)
.PHONY: scrape-studocu
scrape-studocu:
	env MSYS_NO_PATHCONV=1 docker run --rm \
		-v "$(PWD_HOST):/app" \
		-w /app $(IMAGE_NAME) \
		python studocu_scraper.py

# Lancer le scraping Studocu + OCR pour tous les liens du CSV (optionnel, à personnaliser)
.PHONY: scrape-studocu-all
scrape-studocu-all:
	env MSYS_NO_PATHCONV=1 docker run --rm \
		-v "$(PWD_HOST):/app" \
		-w /app $(IMAGE_NAME) \
		python studocu_scraper.py --all