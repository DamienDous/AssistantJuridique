#!/bin/bash
set -e

OUTPUT_DIR=/workspace/exported_models
mkdir -p $OUTPUT_DIR

if [ -f "$OUTPUT_DIR/ch_PP-OCRv5_det_server_infer/inference.pdmodel" ]; then
  echo "✅ Modèle déjà exporté, rien à faire."
  exit 0
fi

cd PaddleOCR

# Install deps
pip install -r requirements.txt

# Télécharge le bon checkpoint (server)
mkdir -p pretrain_models/ch_PP-OCRv5_det_server
wget -nc -O /tmp/ch_PP-OCRv5_det_server_infer.tar \
  https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_server_det_infer.tar
tar -xf /tmp/ch_PP-OCRv5_det_server_infer.tar -C pretrain_models/ch_PP-OCRv5_det_server --strip-components=1

# Export du modèle (produira .pdmodel + .pdiparams + .yml)
python3 tools/export_model.py \
  -c configs/det/PP-OCRv5/PP-OCRv5_server_det.yml \
  -o Global.pretrained_model=./pretrain_models/ch_PP-OCRv5_det_server/best_accuracy \
  -o Global.save_inference_dir=$OUTPUT_DIR/ch_PP-OCRv5_det_server_infer

# Vérifie que tout est bien exporté
echo "✅ Modèle exporté dans $OUTPUT_DIR/ch_PP-OCRv5_det_server_infer"
ls -lh $OUTPUT_DIR/ch_PP-OCRv5_det_server_infer
