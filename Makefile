IMAGE_NAME = pipeline-ocr
INPUT_DIR = pipeline_OCR/traitement_lot/input_pdf
OUTPUT_DIR = pipeline_OCR/traitement_lot/output

build:
	docker build -t $(IMAGE_NAME) .

run:
ifndef FILE
	$(error ❌ Veuillez spécifier un nom de fichier PDF avec FILE=nom.pdf)
endif
	docker run --rm \
		-v "$$(pwd):/app" \
		-v "$$HOME/.lt_cache:/root/.cache/language_tool_python" \
		$(IMAGE_NAME) \
		bash -c "pipeline_OCR/pipelines/pipeline_base/pipeline_reconnaissance_text_pdf.sh \
		\"$(INPUT_DIR)/$(FILE)\" \
		\"$(OUTPUT_DIR)/temp_$(basename $(FILE) .pdf)\""

clean:
	docker rmi $(IMAGE_NAME) || true

run-all:
	@for file in $(INPUT_DIR)/*.pdf; do \
		name=$$(basename "$$file"); \
		echo "▶️ Traitement de $$name..."; \
		make run FILE="$$name" || exit 1; \
	done