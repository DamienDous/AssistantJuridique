IMAGE_NAME = pipeline-ocr
INPUT_DIR = pipeline_OCR/traitement_lot/input_pdf
OUTPUT_DIR = pipeline_OCR/traitement_lot/output
SCRIPT = pipeline_OCR/pipelines/pipeline_base/pipeline_reconnaissance_text_pdf.sh

build:
	docker build -t $(IMAGE_NAME) .

run:
ifndef FILE
	$(error ❌ Veuillez spécifier un nom de fichier PDF avec FILE=nom.pdf)
endif
	docker run --rm -v "$$(pwd):/app" $(IMAGE_NAME) \
		bash $(SCRIPT) \
		$(INPUT_DIR)/$(FILE) \
		$(OUTPUT_DIR)/temp_$(basename $(FILE) .pdf)

clean:
	docker rmi $(IMAGE_NAME) || true