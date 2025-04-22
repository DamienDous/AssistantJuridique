# 🚀 Pipeline OCR dockerisé

## ✅ Prérequis
- [Docker installé](https://docs.docker.com/get-docker/)

## 🧪 Installation
Cloner le dépôt :
```bash
git clone https://github.com/tonutilisateur/tonrepo.git
cd tonrepo
```

Configurer (vérifie que Docker est installé) :
```bash
cmake .
```

## 🔧 Commandes disponibles

### 🏗️ Build de l'image Docker :
```bash
make build
```

### 🚀 Lancer le pipeline OCR :
```bash
make run FILE=nom_du_fichier.pdf
```

Le fichier doit être placé dans :
```
pipeline_OCR/traitement_lot/input_pdf/
```

Le résultat sera disponible dans :
```
pipeline_OCR/traitement_lot/output/
```

### 🧼 Nettoyer l'image Docker :
```bash
make clean
```

---

## 💡 Fonctionne sur :
- Linux
- macOS
- Windows (avec WSL2 ou Docker Desktop)
