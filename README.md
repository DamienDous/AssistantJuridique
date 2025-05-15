# 🧠 Pipeline OCR Dockerisé (PDF > TIFF > ScanTailor > Tesseract > LanguageTool)

---

Ce projet automatise le traitement de documents PDF scannés :

- 📄 Conversion PDF → images TIFF
- 🪞 Nettoyage avec ScanTailor CLI
- 🔠 OCR via Tesseract
- 🧠 Correction orthographique avec LanguageTool
- 📥 Génération finale `.txt` et `.pdf` corrigé

---

## ✅ Prérequis

### 1. Logiciels obligatoires

- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- `make` (préinstallé sur macOS/Linux, à installer via MSYS2 sur Windows)

---

## 🧰 Règles d'utilisation cross-plateforme

### 🔁 `make build`

- Ce `make build` est **obligatoire la première fois sur tous les systèmes**.
- **Mais ensuite :**
  - Sur **macOS** et **Linux**, pas besoin de re-builder l’image Docker après chaque modification des `.sh` ou `.py` : le montage de dossier fonctionne parfaitement.
  - Sur **Windows**, le système de fichiers entre le conteneur Docker et l'hôte ne reflète **pas automatiquement les modifications**, à cause du backend **WSL 2 + Git Bash** :
    - ⚠️ Vous devez faire `make build` après toute modification dans les scripts `.sh` ou `.py`.

---

## 🚫 Interdiction d'utiliser Git Bash sous Windows

## 🐧 Option : Windows via WSL (Windows Subsystem for Linux)

- ✅ En utilisant **WSL 2**, vous disposez d’un environnement Linux natif sur Windows.
- ✅ Les commandes `make`, `docker`, `pyenv`, etc. fonctionnent comme sur macOS/Linux.
- ✅ Activation automatique du venv via `.python-version` si `pyenv` est installé dans WSL.

- L'exécution des scripts avec Git Bash sous Windows **provoque une erreur de montage de volumes (`-v`) dans Docker**.
- **Seuls PowerShell ou WSL sont compatibles** avec la synchronisation du projet local et le conteneur Docker.

### 🛡️ Mode Safe recommandé sous Windows

Deux cibles supplémentaires ont été ajoutées pour garantir un comportement sûr sous Windows :
- `make run-safe FILE=xxx.pdf` : exécute une pipeline avec protection contre Git Bash.
- `make run-safe-all` : exécute toute la pile sur tous les PDF, en sécurité.

👉 Recommandé si vous travaillez dans PowerShell ou dans des environnements instables comme certaines distributions WSL.

Un système de **sécurité a été mis en place dans le `Makefile`** pour bloquer automatiquement l'exécution si Git Bash est détecté.

- ✅ Activez le **mode safe** en restant dans PowerShell ou WSL.
- ❌ Ne pas utiliser `Git Bash` avec Docker.

---

## ▶️ Utilisation standard

### Pour lancer le traitement d’un fichier unique :

```bash
make build PLATFORM=linux/amd64      # Sur processeur Intel (Linux/Windows)
make build PLATFORM=linux/arm64      # Sur Mac M1/M2/M3/M4
make run FILE=nom_du_fichier.pdf
```

Le fichier doit être placé dans :
```
pipeline_OCR/traitement_lot/input_pdf/
```

Les résultats seront dans :
```
pipeline_OCR/traitement_lot/output/
```

### Pour tous les fichiers PDF :

```bash
make run-all
```

---

## 🧪 Corpus de test et évaluation

### Dossiers :

- PDF d’entrée : `pipeline_OCR/evaluation/input_pdf/`
- Fichiers texte de référence : `pipeline_OCR/evaluation/reference_txt/`

Ces références ont été **corrigées manuellement**.

### Lancer l’évaluation :

```bash
python3 pipeline_OCR/evaluation/evaluate_pipeline_from_pdf.py
```

### Exemple de résultat de l’évaluation :

```
Évaluation de : 20200227_CIVIL_conclusions_MAE_page_10.pdf
✅ Fichier OCR : .../output/temp_xxx/xxx.txt
✅ Fichier référence : .../reference_txt/xxx.txt
Score de similarité : 89.73%
```

---

## 📊 Tableau de scores à compléter

| PDF source                          | Score OCR actuel |
|------------------------------------|------------------|
| 20041102_CIVIL_dossier...st_julien |                  |
| 20130905_CIVIL_PV_GALLORO          |                  |
| 20130911_CIVIL_PV_GAWRONSKI        |                  |
| 20200227_CIVIL_MAE_p1              |                  |
| 20200227_CIVIL_MAE_p10             |                  |
| 20210604_CIVIL_Thirion_p1          |                  |
| 20210604_CIVIL_Thirion_p3          |                  |

➡️ Il reste à effectuer l’évaluation complète de la pipeline actuelle pour chaque fichier PDF ci-dessus.

---

## 🔬 Vers d’autres pipelines OCR

Le pipeline principal est :

```
pipeline_OCR/pipelines/pipeline_base/pipeline_reconnaissance_text_pdf.sh
```

Mais d’autres pipelines pourront être ajoutés dans `pipeline_OCR/pipelines/` :

### Outils à tester dans les futures versions :

- 🤖 `OCRmyPDF` pour un rendu OCR en calque
- 📚 `EasyOCR` ou `PaddleOCR`
- 🧼 Filtres d’image (OpenCV : CLAHE, sharpening, etc.)
- 🧠 Modèles IA spécialisés OCR français
- 🧪 OCR par segment avec apprentissage automatique

Chaque nouveau pipeline pourra être évalué avec les mêmes fichiers de référence.

---

## 📁 Arborescence recommandée

```
tonrepo/
├── Makefile
├── pipeline_OCR/
│   ├── traitement_lot/
│   │   ├── input_pdf/
│   │   └── output/
│   ├── pipelines/
│   │   └── pipeline_base/
│   │       ├── pipeline_reconnaissance_text_pdf.sh
│   │       └── 04_correction.py
│   └── evaluation/
│       ├── input_pdf/
│       ├── reference_txt/
│       └── evaluate_pipeline_from_pdf.py
```

---

## ✅ Exemple complet

```bash
make build PLATFORM=linux/amd64      # Sur processeur Intel (Linux/Windows)
make build PLATFORM=linux/arm64      # Sur Mac M1/M2/M3/M4
make run FILE=20200227_CIVIL_conclusions_MAE_page_10.pdf
make run-all
python3 pipeline_OCR/evaluation/evaluate_pipeline_from_pdf.py
```

---

Bonne exploration des pipelines OCR ! 🌱