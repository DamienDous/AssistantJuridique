import subprocess
from pathlib import Path
import shutil
import glob

# Répertoires de base
base_dir = Path(__file__).resolve().parents[2]
pipeline_script = base_dir / "pipelines/pipeline_base/pipeline_reconnaissance_text_pdf.sh"
input_dir = base_dir / "../DB/cleaned"
output_dir = base_dir / "../DB/OCRise"

print("📂 Répertoire d'entrée :", input_dir)
print("📂 Répertoire de sortie :", output_dir)
print("⚙️  Script pipeline utilisé :", pipeline_script)

# Crée le répertoire output si nécessaire
output_dir.mkdir(parents=True, exist_ok=True)

# Lister tous les fichiers PDF à traiter
pdf_files = list(input_dir.glob("*.png"))
print(f"📄 {len(pdf_files)} fichier(s) PDF trouvé(s) dans {input_dir}")

if not pdf_files:
    print("❌ Aucun fichier PDF à traiter. Veuillez en ajouter dans input_pdf/.")
else:
    for pdf_file in pdf_files:
        name = pdf_file.stem
        workdir = output_dir / f"temp_{name}"
        workdir.mkdir(parents=True, exist_ok=True)

        print("\n▶️ Traitement de :", pdf_file.name)
        print("📁 Répertoire de travail temporaire :", workdir)
        print("🚀 Lancement du script shell...")

        result = subprocess.run([
            "bash", str(pipeline_script), str(pdf_file), str(workdir)
        ], capture_output=True, text=True)

        print("📤 Sortie standard :\n", result.stdout)
        print("📥 Erreurs éventuelles :\n", result.stderr)

        if result.returncode == 0:
            # Cherche récursivement le fichier *_final_corrige.pdf
            pdf_matches = list(workdir.rglob("*_final_corrige.pdf"))

            if pdf_matches:
                final_pdf = pdf_matches[0]
                dest_path = output_dir / f"{name}.pdf"
                shutil.move(str(final_pdf), dest_path)
                print(f"✅ PDF final trouvé et déplacé : {dest_path}")
            else:
                print(f"⚠️ Aucun PDF *_final_corrige.pdf trouvé dans {workdir}")
        else:
            print(f"❌ Échec (code {result.returncode}) : {pdf_file.name}")

        print(f"🧹 Suppression du répertoire temporaire : {workdir}")
        
        # Nettoyage du répertoire temporaire
        shutil.rmtree(workdir, ignore_errors=True)
