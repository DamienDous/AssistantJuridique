Réorganisation du projet OCR juridique

Ce projet est une réorganisation claire et propre du pipeline OCR existant afin de faciliter sa gestion, sa compréhension et ses futures améliorations. Il comporte deux usages principaux :

⚙️ Scorage : évaluer automatiquement la performance de différentes configurations de pipeline sur des fichiers de test (input_pdf + référence).

🧾 Traitement de masse : appliquer le pipeline validé à un ensemble de fichiers PDF réels (production).

Structure du projet

pipeline_OCR/
├── pipelines/
│   └── pipeline_base/
│       ├── pipeline_reconnaissance_text_pdf.sh   # Script principal orchestrant toutes les étapes
│       ├── 04_correction.py                      # Script de correction grammaticale avec LanguageTool
│       └── utilitaires/                          # Scripts annexes non appelés automatiquement
│           ├── convert_tiff_to_pdf.py
│           └── extract_txt_from_pdf.py
│
├── evaluation/                                   # Partie dédiée au scorage automatique
│   ├── evaluate_pipeline_from_pdf.py             # Évalue une pipeline sur tous les fichiers test
│   ├── input_pdf/                                # Fichiers PDF de test
│   ├── reference_txt/                            # Références texte (gold standard)
│   └── logs/                                     # Fichiers de score (CSV)
│
├── traitement_lot/                               # Traitement réel de lots PDF (production)
│   ├── input_pdf/                                # PDF à traiter réellement
│   └── output/                                   # Résultats de traitement (PDF corrigés)
│
├── processed_files/                              # Temporaire, utilisé par les scripts
├── docs/
│   └── README.md                                  # Ce fichier
├── requirements.txt
├── CMakeLists.txt
└── .gitignore

Utilisation du pipeline principal

1. Évaluation automatique d’une configuration :
python3 pipeline_OCR/evaluation/evaluate_pipeline_from_pdf.py

Ce script :

scanne tous les PDF présents dans evaluation/input_pdf/
applique pipeline_reconnaissance_text_pdf.sh à chacun
compare les textes générés aux références dans reference_txt/
enregistre les scores dans evaluation/logs/scores_from_pdf.csv

2. Traitement manuel d’un fichier unique :
bash pipeline_OCR/pipelines/pipeline_base/pipeline_reconnaissance_text_pdf.sh chemin/vers/fichier.pdf chemin/vers/WORKDIR/

Ce script effectue :
La conversion PDF → images TIFF
Le redressement et nettoyage avec ScanTailor (via Docker)
L’OCR avec Tesseract
La correction grammaticale via 04_correction.py
La reconstruction finale du PDF corrigé

Scripts spécifiques

🔹 04_correction.py
Corrige le texte OCR brut à l’aide de LanguageTool. Il est appelé automatiquement par pipeline_reconnaissance_text_pdf.sh. Il lit les .txt bruts et en produit une version corrigée dans le dossier _txt_corrige correspondant.

🔹 convert_tiff_to_pdf.py (utilitaire)
Permet de convertir des fichiers TIFF existants en un fichier PDF. Pratique pour assembler manuellement une séquence d’images après OCR ou traitement par ScanTailor.

🔹 extract_txt_from_pdf.py (utilitaire)
Permet d’extraire le texte brut (non OCR) d’un PDF en utilisant pdftotext. Utile uniquement si le PDF n’est pas une image scannée.

Ces scripts ne sont pas appelés automatiquement, mais peuvent être utiles ponctuellement pour des tests ou de la préparation manuelle.