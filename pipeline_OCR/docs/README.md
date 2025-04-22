Structure du projet

pipeline_OCR/
  ├── scripts/
  │     ├── pipeline_reconnaissance_text_pdf.sh
  │     ├── 01_pdf_to_tiff.sh
  │     ├── 02_scantailor.sh
  │     ├── 03_ocr.sh
  │     ├── 04_correction.py
  │     ├── 05_fusion.sh
  │     ├── evaluate_pipeline_from_pdf.py
  │     ├── convert_tiff_to_pdf.py
  │     └── extract_txt_from_pdf.py
  ├── input_pdf/
  │     ├── 20130905_CIVIL_PV_GALLORO_page_1.pdf
  │     ├── 20130911_CIVIL_PV_GAWRONSKI_page_1.pdf
  │     ├── 20041102_CIVIL_dossier_impots_locaux_st_julien_page_11.pdf
  │     ├── 20200227_CIVIL_conclusions_MAE_page_1.pdf
  │     ├── 20200227_CIVIL_conclusions_MAE_page_10.pdf
  │     ├── 20210604_CIVIL_Conclusions_Thirion_page_1.pdf
  │     └── 20210604_CIVIL_Conclusions_Thirion_page_3.pdf
  ├── processed_files/
  │     ├── temp_processing/ (généré automatiquement)
  │     └── input_tiff/
  │         ├── 20200227_CIVIL_conclusions_MAE_page_10.tif
  │         ├── 20041102_CIVIL_dossier_impots_locaux_st_julien_page_11.tif
  │         ├── 20200227_CIVIL_conclusions_MAE_page_1.tif
  │         ├── 20130911_CIVIL_PV_GAWRONSKI_page_1.tif
  │         ├── 20130905_CIVIL_PV_GALLORO_page_1.tif
  │         ├── 20210604_CIVIL_Conclusions_Thirion_page_3.tif
  │         └── 20210604_CIVIL_Conclusions_Thirion_page_1.tif
  ├── reference_txt/
  │     ├── 20200227_CIVIL_conclusions_MAE_page_1.txt
  │     ├── 20041102_CIVIL_dossier_impots_locaux_st_julien_page_11.txt
  │     ├── 20200227_CIVIL_conclusions_MAE_page_10.txt
  │     ├── 20130905_CIVIL_PV_GALLORO_page_1.txt
  │     ├── 20130911_CIVIL_PV_GAWRONSKI_page_1.txt
  │     ├── 20210604_CIVIL_Conclusions_Thirion_page_3.txt
  │     └── 20210604_CIVIL_Conclusions_Thirion_page_1.txt
  ├── results/
  │     └── scores_from_pdf.csv
  ├── docs/
  │     └── README.md (ce fichier)
  ├── requirements.txt
  └── CMakeLists.txt

Instructions pour exécuter le pipeline actuel

Depuis la racine du projet :

Assurez-vous que tous les scripts ont les permissions d'exécution :
chmod +x scripts/*.sh

Installez les dépendances Python :
pip install -r requirements.txt

Lancez le script principal avec votre fichier PDF :
bash scripts/pipeline_reconnaissance_text_pdf.sh input_pdf/votre_fichier.pdf processed_files/temp_processing/

Pour évaluer automatiquement le pipeline avec tous les PDF disponibles dans input_pdf/ :
python3 scripts/evaluate_pipeline_from_pdf.py
