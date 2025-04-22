from pathlib import Path
import os
import re
import language_tool_python

def corriger_texte(texte, tool):
    # Découper en phrases pour éviter les blocages
    phrases = re.split(r'(?<=[.!?])\s+', texte)
    result = ""
    for phrase in phrases:
        if phrase.strip():
            matches = tool.check(phrase)
            corr = language_tool_python.utils.correct(phrase, matches)
            result += corr + " "
    return result.strip()

def main():
    workdir = os.environ.get("WORKDIR")
    if not workdir:
        print("❌ Erreur : la variable WORKDIR n'est pas définie.")
        exit(1)

    # Rechercher le dossier se terminant par '_txt'
    text_dir = None
    for root, dirs, _ in os.walk(workdir):
        for d in dirs:
            if d.endswith("_txt") and not d.endswith("_txt_corrige"):
                text_dir = os.path.join(root, d)
                break
        if text_dir:
            break

    if not text_dir:
        print(f"❌ Aucun dossier '*_txt' trouvé sous {workdir}")
        exit(1)

    target_dir = text_dir.replace("_txt", "_txt_corrige")
    os.makedirs(target_dir, exist_ok=True)

    tool = language_tool_python.LanguageTool("fr")

    # Traiter chaque fichier .txt
    for filename in os.listdir(text_dir):
        if filename.endswith(".txt") and not filename.endswith("_corrigé.txt"):
            input_path = os.path.join(text_dir, filename)
            output_name = Path(filename).stem + ".txt"
            output_path = os.path.join(target_dir, output_name)

            with open(input_path, "r", encoding="utf-8", errors="ignore") as fin:
                raw = fin.read()

            corrected = corriger_texte(raw, tool)

            with open(output_path, "w", encoding="utf-8") as fout:
                fout.write(corrected)

            print(f"✅ Corrigé : {output_path}")

if __name__ == "__main__":
    main()