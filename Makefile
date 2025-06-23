IMAGE_NAME = pipeline-ocr
INPUT_DIR = pipeline_OCR/traitement_lot/input_pdf
OUTPUT_DIR = pipeline_OCR/traitement_lot/output

# détection Git Bash vs PowerShell/CMD
ifdef MSYSTEM
  # MSYS ou MINGW → Git Bash
  DOCKER_ENV     := MSYS_NO_PATHCONV=1
  DOCKER_PWD_MNT := -v "$$(pwd -W):/app"
else
  # Windows natif (PowerShell/CMD)
  DOCKER_ENV     :=
  # CURDIR est C:\Users\… ; on remplace backslash par slash
  DOCKER_PWD_MNT := -v "$(subst \,/,$(CURDIR)):/app"
endif

.PHONY: build
build:
	$(DOCKER_ENV) docker build -t $(IMAGE_NAME) .

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
	$(DOCKER_ENV) docker run --rm \
		$(DOCKER_PWD_MNT) \
		-v language_tool_cache:/root/.cache/language_tool_python \
		-w /app $(IMAGE_NAME) \
		sh -c '\
		  RAW="$$1"; \
		  case "$$RAW" in \
		    *.pdf) ORIG="$$RAW";; \
		    *)      ORIG="$$RAW.pdf";; \
		  esac; \
		  BASE="$${ORIG%.pdf}"; \
		  CLEAN="$$(echo "$${BASE}" \
		    | iconv -f UTF-8 -t ASCII//TRANSLIT \
		    | sed -E "s/[^[:alnum:]]+/_/g")"; \
		  cp "$(INPUT_DIR)/$${ORIG}" "$(INPUT_DIR)/$${CLEAN}.pdf"; \
		  pipeline_OCR/pipelines/pipeline_base/pipeline_reconnaissance_text_pdf.sh \
		    "$(INPUT_DIR)/$${CLEAN}.pdf" "$(OUTPUT_DIR)/temp_$${CLEAN}"; \
		  mv "$(OUTPUT_DIR)/$${CLEAN}_final_corrige.pdf" \
		     "$(OUTPUT_DIR)/$${BASE}_final_corrige.pdf"; \
		  rm -f "$(INPUT_DIR)/$${CLEAN}.pdf"; \
		  rm -rf  "$(OUTPUT_DIR)/temp_$${CLEAN}" \
		' _ "$(FILE)"

run-safe:
	@if [ "$$MSYSTEM" = "MINGW64" ] || [ "$$MSYSTEM" = "MSYS" ]; then \
		echo "❌ ERREUR : Ne pas exécuter ce Makefile depuis Git Bash. Utilise PowerShell ou CMD pour que Docker monte les volumes correctement."; \
		exit 1; \
	else \
		$(MAKE) run FILE="$(FILE)"; \
	fi
	
clean:
	$(DOCKER_ENV) docker rmi $(IMAGE_NAME) || true

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

# Lancer le scraping Studocu (CSV obligatoire)
.PHONY: scrape-studocu
scrape-studocu:
	$(DOCKER_ENV) docker run --rm \
		-v "$$($(PWD_CMD)):/app" \
		-w /app $(IMAGE_NAME) \
		python studocu_scraper.py

# Lancer le scraping Studocu + OCR pour tous les liens du CSV (optionnel, à personnaliser)
.PHONY: scrape-studocu-all
scrape-studocu-all:
	$(DOCKER_ENV) docker run --rm \
		-v "$$($(PWD_CMD)):/app" \
		-w /app $(IMAGE_NAME) \
		python studocu_scraper.py --all