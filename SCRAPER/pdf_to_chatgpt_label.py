EMAIL = "ghazi.dous@gmail.com"
PASSWORD = "opeAPV2002!!"

# coding: utf-8

import os
import time
import fitz        # PyMuPDF, pour extraire du texte brut (si possible)
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import pyperclip
import re
import random

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
TMP_IMG_FOLDER = r".\traitement_lot\images"

# Fichier intermédiaire pour écrire le prompt que l’on enverra à ChatGPT
PROMPT_FOLDER = r".\traitement_lot\prompt"
JSON_FOLDER = r".\traitement_lot\json"
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
		# print(f"✅ Page {idx} rasterisée => {img_path}")

		# OCR sur l’image
		try:
			texte_page = pytesseract.image_to_string(Image.open(img_path), lang=TESSERACT_LANG)
			# print(f"   📝 OCR effectué sur page_{idx:03d}.png (longueur ~ {len(texte_page)} caractères).")
		except Exception as e:
			print(f"   ❌ Erreur OCR page {idx}: {e}")
			texte_page = ""

		texte_total += texte_page + "\n\n"

	return texte_total

# ——————————————
# GÉNÉRATION DU PROMPT
# ——————————————
def generer_prompt_cas_pratique_json():
	entete = (
			"Le but de cet exercice est de classifier chaque phrase de ce cas d'étude dans les catégories : "
			"Faits, Problématique, Règles, Analyse ou Solution. "
			"Convertis **exactement** ce texte en JSON, **SANS AUCUNE OMISSION, RÉFORMULATION ni RÉSUMÉ**. "
			"Tu dois utiliser exactement les mêmes informations en ne faisant **AUCUN CHANGEMENT**. "
			"Convertis selon le schéma suivant: "
			"{ "
			"   'Faits': ['Fait 1', 'Fait 2', 'Fait 3'], "
			"   'Problématique': 'Phrases pour la problématique juridique ici.', "
			"   'Règles': ['Règle 1', 'Règle 2', 'Règle 3'], "
			"   'Analyse': ['Analyse 1', 'Analyse 2'], "
			"   'Solution': 'Phrases pour la solution finale ici.' "
			"}"
			"**NE MODIFIE RIEN**, ne retourne que du JSON. "
			"Texte à convertir (**NE CHANGE RIEN**) :"
			)
	return entete

def ecrire_prompt_dans_fichier(prompt, chemin):
	with open(chemin, "w", encoding="utf-8") as f:
		f.write(prompt)
	print(f"✅ Prompt écrit dans '{chemin}' (longueur {len(prompt)} caractères).")


# ——————————————
# AUTOMATISATION CHROME / CHATGPT
# ——————————————

def generer_user_agent():
	user_agents = [
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36",
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36 Edge/16.16299",
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36",
		"Mozilla/5.0 (Windows NT 6.1; WOW64; rv:23.0) Gecko/20100101 Firefox/23.0",
		"Mozilla/5.0 (Windows NT 6.3; rv:36.0) Gecko/20100101 Firefox/36.0"
	]
	return random.choice(user_agents)

def init_driver_with_proxy(proxy_ip):
	options = uc.ChromeOptions()
	options.add_argument("--disable-blink-features=AutomationControlled")
	options.add_argument("--window-size=1280,900")
	
	# Assurez-vous que le profil est bien créé à chaque lancement
	# options.add_argument(f"--user-data-dir={r'./chrome_profiles/chrome_profile_' + str(int(time.time()))}")

	# Ajouter proxy si nécessaire
	# options.add_argument(f"--proxy-server={proxy_ip}")  # Utiliser un proxy pour chaque session

	# Ajout des prefs pour autoriser l'accès au presse-papiers sans popup
	# prefs = {
	# 	"profile.default_content_setting_values.clipboard": 1  # 1 = autoriser, 2 = bloquer
	# }
	# options.add_experimental_option("prefs", prefs)
	
	# Configuration utilisateur, user-agent, etc.
	user_agent = generer_user_agent()  # Assure-toi que cette fonction génère un user-agent correct
	options.add_argument(f"user-agent={user_agent}")

	# Crée le driver Chrome avec les options définies
	driver = uc.Chrome(service=Service(ChromeDriverManager().install()), options=options)
	
	# Si tu souhaites désactiver la détection de l'automatisation, garde cette ligne
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

	time.sleep(15)

	# À ce stade, vous devriez être connecté. Il peut y avoir un 2FA ou un autre écran,
	# mais on se contentera ici de considérer que la connexion a réussi.
	return True

def fermer_popup_connexion(driver, timeout=10):
	"""
	Ferme le popup de connexion s'il est visible.
	"""
	try:
		# Vérifier si le bouton "Annuler" ou "Se connecter" existe
		bouton_annuler = driver.find_elements(By.XPATH, "//button[text()='Annuler']")
		bouton_se_connecter = driver.find_elements(By.XPATH, "//button[text()='Se connecter']")
		
		if bouton_annuler:
			bouton_annuler[0].click()  # Cliquer sur "Annuler" pour fermer le popup
			print("✅ Popup de connexion fermé par 'Annuler'.")
		
		elif bouton_se_connecter:
			bouton_se_connecter[0].click()  # Cliquer sur "Se connecter" si nécessaire
			print("✅ Popup de connexion fermé par 'Se connecter'.")
		
	except Exception as e:
		print(f"⚠️ Erreur lors de la fermeture du popup de connexion : {e}")

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

			# Vérifie si le bouton est cliquable avant de le retourner
			WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(bouton_copier))

			print(f"✅ {len(boutons)} boutons détectés, dernier bouton prêt à être cliqué.")
			return bouton_copier

		if time.time() - start_time > timeout:
			raise TimeoutException(f"⏳ Timeout : {len(boutons)} boutons trouvés, attendu au moins {nombre_attendu_boutons}.")

		time.sleep(poll_interval)

def verifier_ou_reconnecter(driver, timeout=10):
	"""
	Vérifie si la page est déconnectée et si le bouton "Rester déconnecté" est visible.
	Si le popup de déconnexion est détecté, on clique sur "Rester déconnecté" et continue le processus.
	"""
	try:
		# Vérifier si le bouton de déconnexion est visible
		bouton_rester_deconnecte = driver.find_elements(By.XPATH, "//button[contains(text(), 'Rester déconnecté')]")
		if bouton_rester_deconnecte:
			bouton_rester_deconnecte[0].click()  # Ferme le popup "Rester déconnecté"
			print("✅ Popup 'Rester déconnecté' fermé.")
			return True  # La page a été réinitialisée
		else:
			print("✅ Pas de popup 'Rester déconnecté' détecté.")
			return False  # Pas de déconnexion
	except Exception as e:
		print(f"⚠️ Erreur lors de la vérification ou fermeture du popup de déconnexion : {e}")
		return False

def relancer_page(driver, url="https://chat.openai.com", retries=3):
	"""
	Si la page plante ou si l'utilisateur est déconnecté, on relance la page.
	"""
	for _ in range(retries):
		try:
			driver.get(url)
			time.sleep(2)
			print(f"✅ Page relancée avec succès.")
			return True
		except Exception as e:
			print(f"❌ Échec de la relance de la page : {e}")
			time.sleep(5)
	return False

def envoyer_prompt_et_recuperer_reponse(driver, prompt, fichier_sortie, numero_reponse, timeout=120):
	"""
	Envoi le prompt à ChatGPT de manière naturelle, ajoute des délais réalistes et gère les erreurs de page.
	"""
	wait = WebDriverWait(driver, 10)

	# Fermer le popup de connexion ou de consentement, si présent
	fermer_popup_connexion(driver)

	zone_placeholder = wait.until(EC.element_to_be_clickable((
		By.CSS_SELECTOR,
		"p[data-placeholder='Poser une question']"
	)))
	zone_placeholder.click()
	time.sleep(random.uniform(1, 1.5))  # Pause entre les actions pour simuler un comportement humain

	# On récupère l’élément actif (c’est le contenteditable sur lequel on peut taper)
	editor = driver.switch_to.active_element
	lignes = prompt.split("\n")

	# Envoyer par blocs de 10 lignes, avec un délai naturel
	taille_bloc = 1
	for i in range(0, len(lignes), taille_bloc):
		bloc = lignes[i:i + taille_bloc]
		editor.send_keys(bloc)
		editor.send_keys(Keys.SHIFT, Keys.ENTER)  # saut de ligne sans envoyer
		# time.sleep(random.uniform(1, 2))  # Délai réaliste entre les envois de lignes

	# Envoi final du message
	editor.send_keys(Keys.ENTER)
	time.sleep(random.uniform(1, 1.5))  # Pause après l'envoi

	print("▶ Prompt envoyé à ChatGPT.")
	time.sleep(15)  # Attente pour la réponse de ChatGPT

	# Vérifier si la page a été déconnectée, si oui, la relancer
	if verifier_ou_reconnecter(driver):
		return envoyer_prompt_et_recuperer_reponse(driver, prompt, fichier_sortie, numero_reponse, timeout)

	print("attente réponse gpt -> numero_reponse : ", numero_reponse)
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

	pattern = r"json\s*(\{.*?\})\s*"
	match = re.search(pattern, json_copie, re.DOTALL)

	if match:
		json_copie_texte = match.group(1)
		print("JSON récupéré")
	else:
		print("Texte récupéré")
		json_copie_texte = json_copie
	
	print("👉 TAILLE JSON: ", len(json_copie_texte))

	# Sauvegarder dans un fichier
	with open(fichier_sortie, "w", encoding="utf-8") as f:
		f.write(json_copie_texte)
	
	print(f"✅ JSON sauvegardé dans '{fichier_sortie}' (taille {len(json_copie_texte)} caractères).")
	
	return ""

# ——————————————
# PROGRAMME PRINCIPAL
# ——————————————

def main():
	# Lancer Chrome + Selenium et se connecter à ChatGPT
	proxy_ip = "http://51.81.245.3:17981"
	driver = init_driver_with_proxy(proxy_ip)
	try:
		succes_connexion = se_connecter_chatgpt(driver, EMAIL, PASSWORD)
		if not succes_connexion:
			return
		time.sleep(2)

		# Connexion
		chat_url = "https://chatgpt.com/"
		driver.get(chat_url)
		time.sleep(2)

		# Attente et vérification
		wait = WebDriverWait(driver, 30)
		
		cpt = 1

		for i, nom_fichier in enumerate(os.listdir(PDF_FOLDER_PATH), start=1):
			chemin_complet = os.path.join(PDF_FOLDER_PATH, nom_fichier)
			nom_sans_ext, extension = os.path.splitext(nom_fichier)
			txt_path = PROMPT_FOLDER + "/" + nom_sans_ext + ".txt"
			
			# On charge le texte du pdf s'il a déjà été créer
			if os.path.isfile(txt_path):
				print("✅ ", txt_path, " existe")
				with open(txt_path, "r", encoding="utf-8") as f:
					texte_complet = f.read()
			else:
				# Sinon on extrait le texte du pdf par OCR
				print("⚠️ ", txt_path, " n'existe pas")
				print(f"📄 Extraction du texte depuis : {chemin_complet} …")
				texte_complet = extraire_texte_pdf(chemin_complet)
				if not texte_complet.strip():
					print("❗ Aucune donnée textuelle récupérée du PDF.")
					return
				# On écrit le texte récupéré par OCR pour ne pas avoir à le refaire
				ecrire_prompt_dans_fichier(texte_complet, txt_path)
				
			json_path = JSON_FOLDER + "/" + nom_sans_ext + ".json"
			# On vérifie que le texte n'a pas déjà était prompté
			if os.path.isfile(json_path):
				print("⚠️ Cas pratique déjà prompté")
				continue
			
			print("👉 TAILLE PROMPT: ", len(texte_complet))

			# Traiter les fichiers de taille inférieur à 5000 char 
			if len(texte_complet) > 5000:
				print("❗ cas d'étude trop grand : > 5000 caractères")
				continue

			# Initialisation prompt pour création json
			prompt_json = generer_prompt_cas_pratique_json() + " " + texte_complet
			reponse_enrichie = envoyer_prompt_et_recuperer_reponse(driver, prompt_json, json_path, numero_reponse=cpt)
			cpt += 1
		
		time.sleep(100)
	finally:
		driver.quit()
		print("🔒 Navigateur fermé. Fin du script.")

if __name__ == "__main__":
	main()