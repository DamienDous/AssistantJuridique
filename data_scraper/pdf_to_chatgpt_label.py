# ——————————————
# CONFIGURATION UTILISATEUR
# ——————————————
EMAIL = "ghazi.dous@gmail.com"
PASSWORD = "opeAPV2002!"
# coding: utf-8

import os
import time
import fitz        # PyMuPDF, pour extraire du texte brut (si possible)
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import pyperclip
import re

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import ElementClickInterceptedException

import undetected_chromedriver as uc
from webdriver_manager.chrome import ChromeDriverManager

# ——————————————
# CONFIGURATION UTILISATEUR
# ——————————————


# Chemin vers le PDF à traiter (un seul PDF à la fois pour ce script)
PDF_FOLDER_PATH = r".\traitement_lot\test_chatgpt_pdf"

# Langue OCR (fra pour français, eng pour anglais, etc.)
TESSERACT_LANG = "fra"

# Dossier temporaire pour stocker les images rasterisées (OCR)
TMP_IMG_FOLDER = r".\temp\images"

# Fichier intermédiaire pour écrire le prompt que l’on enverra à ChatGPT
PROMPT_FOLDER = r".\temp\prompt"
JSON_FOLDER = r".\temp\json"
# Fichier de sortie pour la réponse de ChatGPT
OUTPUT_RESPONSE_FILE = r".\chatgpt_reponse.txt"


# ——————————————
# FONCTIONS D’EXTRACTION DE TEXTE
# ——————————————

def extraire_texte_pdf(pdf_path):
	"""
	Essaie d’abord d’extraire du texte avec PyMuPDF (fitz).
	Si aucune page ne contient de texte (ou si fitz renvoie une extraction vide),
	on passe en OCR image → tesseract.
	"""
	try:
		doc = fitz.open(pdf_path)
	except Exception as e:
		print(f"❌ Erreur à l’ouverture du PDF via fitz: {e}")
		return ""

	texte_raw = ""
	for page in doc:
		texte_raw += page.get_text("text") + "\n"

	# Si on obtient un résultat non vide, on le retourne
	if texte_raw.strip():
		print("✅ Extraction de texte réussie avec PyMuPDF (PDF natif).")
		return texte_raw

	# Sinon, on passe en OCR (PDF scanné ou texte non détectable)
	print("ℹ️ Pas de texte détectable directement, on passe en OCR (images).")
	return re.sub(r'\s+', ' ', extraire_texte_par_ocr(pdf_path)).strip()


def extraire_texte_par_ocr(pdf_path):
	"""
	1) Convertit chaque page du PDF en image (via pdf2image).  
	2) Applique pytesseract sur chaque image.  
	3) Retourne le texte concaténé.
	"""
	if not os.path.isdir(TMP_IMG_FOLDER):
		os.makedirs(TMP_IMG_FOLDER, exist_ok=True)

	print(f"📄 Conversion du PDF en images dans '{TMP_IMG_FOLDER}' …")
	try:
		pages = convert_from_path(pdf_path, dpi=300, fmt="png", output_folder=TMP_IMG_FOLDER, thread_count=2)
	except Exception as e:
		print(f"❌ Erreur lors de la conversion PDF→images: {e}")
		return ""

	texte_total = ""
	for idx, page_img in enumerate(pages, start=1):
		img_path = os.path.join(TMP_IMG_FOLDER, f"page_{idx:03d}.png")
		page_img.save(img_path, "PNG")
		print(f"✅ Page {idx} rasterisée => {img_path}")

		# OCR sur l’image
		try:
			texte_page = pytesseract.image_to_string(Image.open(img_path), lang=TESSERACT_LANG)
			print(f"   📝 OCR effectué sur page_{idx:03d}.png (longueur ~ {len(texte_page)} caractères).")
		except Exception as e:
			print(f"   ❌ Erreur OCR page {idx}: {e}")
			texte_page = ""

		texte_total += texte_page + "\n\n"

	return texte_total


# ——————————————
# GÉNÉRATION DU PROMPT
# ——————————————

def generer_prompt_cas_pratique(texte_cas):
	"""
	Face au texte complet du cas pratique, on fabrique un prompt structuré.  
	Ici, on fait au plus simple : on préfixe avec les rubriques puis on colle le texte brut.
	"""
	entete = (
		"À partir de ce cas pratique juridique, génère un fichier JSON strict et minimaliste contenant uniquement"
		"les catégories suivantes : Faits, Problématique, Règles, Analyse, Solution."
		"Ne fais aucune supposition ou ajout d'information, utilise uniquement ce qui est explicitement écrit. "
	)
	return entete + texte_cas

def generer_prompt_cas_pratique_enrichi(texte_cas):
	"""
	Face au texte complet du cas pratique, on fabrique un prompt structuré.  
	Ici, on fait au plus simple : on préfixe avec les rubriques puis on colle le texte brut.
	"""
	entete = (
		"En te basant sur ce cas pratique juridique, génère un fichier JSON"
		"complet avec les rubriques Faits, Problématique, Règles, Analyse et Solution."
		"Pour chaque rubrique, développe les arguments, intègre des références jurisprudentielles,"
		"explique clairement le raisonnement juridique."
		"Ajoute des remarques pédagogiques sans déformer les faits. "
	)
	return entete + texte_cas

def ecrire_prompt_dans_fichier(prompt, chemin):
	with open(chemin, "w", encoding="utf-8") as f:
		f.write(prompt)
	print(f"✅ Prompt écrit dans '{chemin}' (longueur {len(prompt)} caractères).")


# ——————————————
# AUTOMATISATION CHROME / CHATGPT
# ——————————————

def init_driver():
	options = uc.ChromeOptions()
	options.add_argument("--disable-blink-features=AutomationControlled")
	options.add_argument("--window-size=1280,900")
	# options.add_argument("--headless=new")  # Si besoin du mode headless

	# Ajout des prefs pour autoriser l'accès au presse-papiers sans popup
	prefs = {
		"profile.default_content_setting_values.clipboard": 1  # 1 = autoriser, 2 = bloquer
	}
	options.add_experimental_option("prefs", prefs)

	driver = uc.Chrome(service=Service(ChromeDriverManager().install()), options=options)
	driver.execute_cdp_cmd(
		"Page.addScriptToEvaluateOnNewDocument",
		{
			"source": """
				Object.defineProperty(navigator, 'webdriver', {
				  get: () => undefined
				});
			"""
		},
	)
	return driver

def click_when_visible(wait, by, selector, retries=3):
	"""
	Essaie plusieurs fois de localiser et cliquer l'élément.
	- 'wait' doit être un WebDriverWait déjà instancié.
	- 'by' + 'selector' correspondent au locator Selenium.
	- 'retries' : nombre de tentatives en cas d'element stale.
	Retourne True si le clic a réussi, ou remonte TimeoutException si on n'a jamais trouvé l'élément.
	"""
	for tentative in range(retries):
		try:
			bouton = wait.until(EC.visibility_of_element_located((by, selector)))
			bouton.click()
			return True
		except StaleElementReferenceException:
			if tentative < retries - 1:
				continue
			else:
				raise
		except TimeoutException as e:
			# Si on n'a pas trouvé l'élément à temps, on remonte l'exception
			raise e


def se_connecter_chatgpt(driver, email, mot_de_passe, timeout=20, retries=3):
	wait = WebDriverWait(driver, timeout)

	# On navigue d'abord vers la page de connexion
	driver.get("https://chat.openai.com/auth/login")

	# 1) Cliquer sur le bouton "Se connecter"
	try:
		click_when_visible(wait, By.XPATH, "//button[@data-testid='login-button']", retries)
	except TimeoutException:
		print("❌ Le bouton 'Se connecter' n'a pas été trouvé.")
		driver.quit()
		return False

	# 2) Attendre que le champ e-mail apparaisse et saisir l'adresse e-mail
	try:
		champ_email = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@name='email']")))
		champ_email.send_keys(email)
	except TimeoutException:
		print("❌ Le champ e-mail n'a pas été trouvé.")
		driver.quit()
		return False

	# 3) Cliquer sur "Suivant" (validation de l'email)
	try:
		click_when_visible(wait, By.XPATH, "//button[contains(., 'Continuer')]", retries)
	except TimeoutException:
		print("❌ Le bouton 'Continuer' (après email) n'a pas été trouvé.")
		driver.quit()
		return False

	# 4) Attendre le champ mot de passe, puis saisir le mot de passe
	try:
		champ_mdp = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@name='password']")))
		champ_mdp.send_keys(mot_de_passe)
	except TimeoutException:
		print("❌ Le champ mot de passe n'a pas été trouvé.")
		driver.quit()
		return False

	# 5) Cliquer sur le bouton de connexion final (validation du mot de passe)
	try:
		click_when_visible(wait, By.XPATH, "//button[contains(., 'Continuer') or //div[text()='Log in']]", retries)
	except TimeoutException:
		print("❌ Le bouton pour valider le mot de passe n'a pas été trouvé.")
		driver.quit()
		return False

	# À ce stade, vous devriez être connecté. Il peut y avoir un 2FA ou un autre écran,
	# mais on se contentera ici de considérer que la connexion a réussi.
	return True

def attendre_bouton_copier_complexe(driver, nombre_attendu_boutons, timeout=60, poll_interval=0.5):
	"""
	Attend que le nombre de boutons 'Copier' atteigne nombre_attendu_boutons,
	puis retourne le dernier bouton.
	"""
	xpath_cible = (
		"//div[contains(@class,'flex min-h-[46px] justify-start')]"
		"//button[@aria-label='Copier' and contains(@class,'text-token-text-secondary')]"
	)
	start_time = time.time()
	
	while True:
		boutons = driver.find_elements(By.XPATH, xpath_cible)
		if len(boutons) >= nombre_attendu_boutons:
			bouton_copier = boutons[-1]
			driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", bouton_copier)
			time.sleep(1.5)
			print(f"✅ {len(boutons)} boutons détectés, dernier bouton prêt à être cliqué.")
			return bouton_copier
		
		if time.time() - start_time > timeout:
			raise TimeoutException(f"⏳ Timeout : {len(boutons)} boutons trouvés, attendu au moins {nombre_attendu_boutons}.")
		
		time.sleep(poll_interval)

def attendre_et_copier_json(driver, timeout=60):
	wait = WebDriverWait(driver, timeout)

	# 1) Attendre que le cadre JSON soit visible
	cadre_json = wait.until(EC.visibility_of_element_located((
		By.XPATH,
		"//div[contains(@class,'rounded-md') and .//div[contains(text(),'json')]]"
	)))
	print("✅ Cadre JSON visible")

	bouton_copier = attendre_bouton_copier_complexe(driver, timeout=120)
	time.sleep(2)

	try:
		bouton_copier.click()
		print("✅ Bouton 'Copier' cliqué normalement.")
	except ElementClickInterceptedException:
		print("⚠️ Clic intercepté, tentative via JavaScript.")
		driver.execute_script("arguments[0].click();", bouton_copier)
		print("✅ Bouton 'Copier' cliqué via JavaScript.")

	time.sleep(3)

def envoyer_prompt_et_recuperer_reponse(driver, prompt, fichier_sortie, numero_reponse, timeout=120):
	"""
	1) Repère la zone de saisie : <textarea tabindex='0'>  
	2) Coupe le prompt en lignes, puis pour chaque ligne : taper → SHIFT+ENTER  
	3) Enfin taper → ENTER pour envoyer le prompt  
	4) Attendre l’apparition des réponses (<div class='markdown'>)  
	5) Scroller jusqu’à la fin (hauteur ne change plus)  
	6) Récupérer le dernier <div class='markdown'>  
	"""
	wait = WebDriverWait(driver, 10)

	zone_placeholder = wait.until(EC.element_to_be_clickable((
		By.CSS_SELECTOR,
		"p[data-placeholder='Poser une question']"
	)))
	zone_placeholder.click()
	# Au clique, le focus passe dans le <div contenteditable="true"> sous-jacent.
	time.sleep(0.5)
	print(prompt)

	# On récupère l’élément actif (c’est le contenteditable sur lequel on peut taper)
	editor = driver.switch_to.active_element
	lignes = prompt.split("\n")

	# Envoyer par blocs de 10 lignes
	taille_bloc = 20
	for i in range(0, len(lignes), taille_bloc):
		bloc = lignes[i:i+taille_bloc]
		editor.send_keys(bloc)
		editor.send_keys(Keys.SHIFT, Keys.ENTER)  # saut de ligne sans envoyer

	# Envoi final du message
	editor.send_keys(Keys.ENTER)
	time.sleep(0.5)

	# Envoi final
	editor.send_keys(Keys.ENTER)

	print("▶ Prompt envoyé à ChatGPT.")
	time.sleep(15)
	print("attente réponse gpt")
	
	bouton_copier = attendre_bouton_copier_complexe(driver, nombre_attendu_boutons=numero_reponse)
	time.sleep(2)

	try:
		bouton_copier.click()
		print("✅ Bouton 'Copier' cliqué normalement.")
	except ElementClickInterceptedException:
		print("⚠️ Clic intercepté, tentative via JavaScript.")
		driver.execute_script("arguments[0].click();", bouton_copier)
		print("✅ Bouton 'Copier' cliqué via JavaScript.")

	time.sleep(3)

	# Lire le contenu du presse-papiers
	json_copie = pyperclip.paste()
	print("json collé")

	print("Contenu JSON copié :")
	pattern = r"json\s*(\{.*?\})\s*"
	match = re.search(pattern, json_copie, re.DOTALL)

	if match:
		json_copie_texte = match.group(1)+"\n}"
		print("JSON extrait :")
		print(json_copie_texte)
	else:
		print("Pas de bloc JSON trouvé.")
		json_copie_texte = json_copie
		print(json_copie)

	# 4) Sauvegarder dans un fichier
	with open(fichier_sortie, "w", encoding="utf-8") as f:
		f.write(json_copie_texte)
	
	print(f"✅ JSON sauvegardé dans '{fichier_sortie}' (taille {len(json_copie_texte)} caractères).")
	
	return ""


# ——————————————
# PROGRAMME PRINCIPAL
# ——————————————

def main():
	# 3) Lancer Chrome + Selenium et se connecter à ChatGPT
	driver = init_driver()
	try:
		# succes_connexion = se_connecter_chatgpt(driver, EMAIL, PASSWORD)
		# if not succes_connexion:
		# 	return
		# time.sleep(2)
		# 4) Une fois connecté, on navigue sur la page de chat précise :
		chat_url = "https://chatgpt.com"
		driver.get(chat_url)
		time.sleep(2)

		# 4) Attendre que le bouton (ou la zone) pour entrer le texte apparaisse
		wait = WebDriverWait(driver, 20)
		numero_reponse = 0
		for i, nom_fichier in enumerate(os.listdir(PDF_FOLDER_PATH), start=1):
			chemin_complet = os.path.join(PDF_FOLDER_PATH, nom_fichier)

			nom_sans_ext, extension = os.path.splitext(nom_fichier)
			txt_path = PROMPT_FOLDER + "/" + nom_sans_ext + ".txt"
			txt_enrichi_path = PROMPT_FOLDER + "/" + nom_sans_ext + "_enrichi.txt"
			print(txt_path)
			if os.path.isfile(txt_path):
				print(txt_path, "existe")
				with open(txt_path, "r", encoding="utf-8") as f:
					prompt = f.read()
			if os.path.isfile(txt_enrichi_path):
				with open(txt_enrichi_path, "r", encoding="utf-8") as f:
					prompt_enrichi = f.read()
			else:
				print(txt_path, "n'existe pas")
				# 1) Extraire le texte du PDF (ou OCR)
				print(f"📄 Extraction du texte depuis : {chemin_complet} …")
				texte_complet = extraire_texte_pdf(chemin_complet)
				if not texte_complet.strip():
					print("❗ Aucune donnée textuelle récupérée du PDF.")
					return
				# Générer le prompt structuré
				prompt = generer_prompt_cas_pratique(texte_complet)
				prompt_enrichi = generer_prompt_cas_pratique_enrichi(texte_complet)
				ecrire_prompt_dans_fichier(prompt, txt_path)
				ecrire_prompt_dans_fichier(prompt_enrichi, txt_path)
				
			# 4) Envoyer le prompt complet et récupérer la réponse
			json_path = JSON_FOLDER + "/" + nom_sans_ext + ".json"
			reponse = envoyer_prompt_et_recuperer_reponse(driver, prompt, json_path, numero_reponse=i)

			json_enrichi_path = JSON_FOLDER + "/" + nom_sans_ext + "_enrichi.json"
			reponse_enrichie = envoyer_prompt_et_recuperer_reponse(driver, prompt_enrichi, json_enrichi_path, numero_reponse=i)
			
		time.sleep(100)

	finally:
		driver.quit()
		print("🔒 Navigateur fermé. Fin du script.")


if __name__ == "__main__":
	main()
