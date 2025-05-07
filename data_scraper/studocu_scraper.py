import time
import os
import random
import requests
import fitz  # PyMuPDF
import csv
from pathlib import Path
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
import unicodedata
import subprocess
import re
import sys
from collections import deque
from urllib.parse import urlparse, urljoin
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException
from PIL import Image
from io import BytesIO

# Journal de scraping CSV
log_entries = []

def init_driver():
	options = uc.ChromeOptions()
	options.add_argument("--no-sandbox")
	options.add_argument("--disable-dev-shm-usage")
	options.add_argument("--disable-blink-features=AutomationControlled")
	options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
						 "AppleWebKit/537.36 (KHTML, like Gecko) "
						 "Chrome/123.0.0.0 Safari/537.36")

	print(f"Initialisation du driver Chrome en mode 'visuel'…")
	driver = uc.Chrome(service=Service(ChromeDriverManager().install()), options=options)

	# Masquer navigator.webdriver
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

def recherche_studocu(driver, mot_cle="cas pratique droit"):
	print(f"🔍 Test de recherche pour : {mot_cle}")
	driver.get("https://www.studocu.com/fr/")

	# 🔧 Attente que la page finisse de “clignoter” (cas du VPN)
	time.sleep(2.5)

	# 🍪 Gérer le bandeau cookies
	try:
		WebDriverWait(driver, 6).until(
			EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Tout refuser')]"))
		).click()
		print("✅ Cookies refusés.")
	except:
		print("ℹ️ Pas de popup cookies détecté.")

	try:
		# 🧠 Attendre que le champ soit cliquable
		champ = WebDriverWait(driver, 10).until(
			EC.element_to_be_clickable((By.CSS_SELECTOR, "input[placeholder*='Rechercher']"))
		)
		for tentative in range(2):  # on essaie une fois, puis on vérifie
			champ.click()
			time.sleep(0.5)
			champ.clear()
			champ.send_keys(mot_cle)
			time.sleep(0.5)
			if champ.get_attribute("value").strip():
				break
			print("⏳ Le mot-clé n’a pas été inséré, nouvelle tentative…")
		
		champ.submit()
		print("✅ Requête envoyée.")

		# Attendre les résultats
		WebDriverWait(driver, 10).until(
			EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a"))
		)

		time.sleep(2)  # laisse le temps au JS de charger les liens

		liens = driver.find_elements(By.CSS_SELECTOR, "a")
		liens_valides = [l.get_attribute("href") for l in liens if l.get_attribute("href") and "/fr/document/" in l.get_attribute("href")]

		print(f"🟢 {len(liens_valides)} liens potentiels trouvés :")
		for lien in liens_valides[:5]:
			print(" ➜", lien)

		return liens_valides

	except Exception as e:
		print("❌ Erreur pendant la recherche :", e)
		return []

def recherche_multi_studocu(driver, requetes, csv_output="studocu_liens.csv"):
	liens_total = []
	for requete in requetes:
		liens = recherche_studocu(driver, requete)
		for url in liens[:2]:  # ⛔ Limitation à 2 liens max par mot-clé
			try:
				driver.get(url)
				WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "title")))
				soup = BeautifulSoup(driver.page_source, "html.parser")
				titre = soup.title.text.strip() if soup.title else ""
			except Exception as e:
				print(f"⚠️ Impossible de récupérer le titre pour {url} : {e}")
				titre = ""
			liens_total.append({
				"requete": requete,
				"url": url,
				"titre": titre
			})
			
		time.sleep(random.uniform(2, 4))  # petite pause entre les requêtes

	with open(csv_output, "w", encoding="utf-8-sig", newline='') as f:
		writer = csv.DictWriter(f, fieldnames=["requete", "url", "titre"], delimiter=";")
		writer.writeheader()
		writer.writerows(liens_total)

	print(f"✅ Fichier CSV enregistré : {csv_output} ({len(liens_total)} liens)")

def nettoyer_texte(html):
	soup = BeautifulSoup(html, "html.parser")
	for script in soup(["script", "style", "noscript"]):
		script.decompose()
	texte = soup.get_text(separator="\n")
	lignes = texte.splitlines()
	propre = []
	for ligne in lignes:
		ligne = unicodedata.normalize("NFKC", ligne.strip())
		if len(ligne) >= 25 and not ligne.lower().startswith("télécharger") and "studocu" not in ligne.lower():
			propre.append(" ".join(ligne.split()))
	return "\n".join(propre)

def scrape_contenu_premium_depuis_csv(driver, csv_path="studocu_liens.csv", dossier_sortie="studocu_txt"):
	if not os.path.exists(dossier_sortie):
		os.makedirs(dossier_sortie)

	with open(csv_path, "r", encoding="utf-8-sig") as f:
		reader = csv.DictReader(f, delimiter=";")
		for ligne in reader:
			url = ligne["url"]
			titre = ligne["titre"]
			print(f"\n🔗 Ouverture : {url}")
			try:
				driver.get(url)

				WebDriverWait(driver, 10).until(
					EC.presence_of_element_located((By.TAG_NAME, "body"))
				)
				time.sleep(3.5)  # attendre chargement PDF/HTML

				# Vérifie si le document est premium (aperçu)
				try:
					driver.find_element(By.XPATH, "//div[contains(text(), 'Ceci est un aperçu')]")
					print("⚠️ Document restreint (aperçu seulement)")
				except:
					print("✅ Document complet visible")

				# Récupération du contenu visible
				html = driver.page_source
				texte = nettoyer_texte(html)

				if len(texte) > 500:
					nom_fichier = titre.replace("/", "-").replace(":", "-").replace("?", "").strip()
					nom_fichier = "_".join(nom_fichier.split())[:100] + ".txt"
					chemin_fichier = os.path.join(dossier_sortie, nom_fichier)
					with open(chemin_fichier, "w", encoding="utf-8") as out:
						out.write(texte)
					print(f"💾 Texte sauvegardé : {chemin_fichier}")
				else:
					print("⛔ Texte trop court ou non récupéré.")

			except Exception as e:
				print(f"❌ Échec sur {url} : {e}")

def login_studocu(driver, email, mot_de_passe):
	driver.get("https://www.studocu.com/fr/login/")

	try:
		WebDriverWait(driver, 6).until(
			EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Tout refuser')]"))
		).click()
		print("✅ Cookies refusés.")
	except:
		print("ℹ️ Pas de pop-up cookies détecté.")

	try:
		bouton_email = WebDriverWait(driver, 8).until(
			EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-test-selector='email-login-button']"))
		)
		driver.execute_script("arguments[0].click();", bouton_email)
		print("✅ 'Continuer avec un e-mail' cliqué via JS.")
	except Exception as e:
		print(f"❌ Échec clic 'Continuer avec un e-mail' : {e}")
		return

	try:
		champ_email = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.NAME, "email")))
		champ_email.clear()
		champ_email.send_keys(email)
		time.sleep(0.3)

		champ_mdp = driver.find_element(By.NAME, "password")
		champ_mdp.clear()
		champ_mdp.send_keys(mot_de_passe)
		time.sleep(0.5)

		# ✅ Simulation humaine : touche Entrée
		champ_mdp.send_keys(Keys.ENTER)
		print("🔐 Connexion envoyée via touche Entrée.")

		WebDriverWait(driver, 10).until(
			EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/fr/')]"))
		)
		print("✅ Connecté à Studocu.")

	except Exception as e:
		print(f"❌ Échec de la connexion : {e}")

def fusionner_captures_verticales(dossier, nom_sortie="document_complet.png"):
	from PIL import Image

	def numero_vue(fichier):
		match = re.search(r"_vue(\d+)\.png$", fichier)
		return int(match.group(1)) if match else float("inf")

	images = sorted(
		[f for f in os.listdir(dossier) if f.endswith(".png") and "_vue" in f],
		key=numero_vue
	)

	if not images:
		print("❌ Aucune image à fusionner.")
		return

	images_pil = [Image.open(os.path.join(dossier, img)) for img in images]
	largeur = max(img.width for img in images_pil)
	hauteur_totale = sum(img.height for img in images_pil)

	image_fusionnee = Image.new("RGB", (largeur, hauteur_totale))
	y_offset = 0
	for img in images_pil:
		image_fusionnee.paste(img, (0, y_offset))
		y_offset += img.height

	image_fusionnee.save(os.path.join(dossier, nom_sortie))
	print(f"✅ Image fusionnée enregistrée : {os.path.join(dossier, nom_sortie)}")
	
def capture_vue_premiere_page(driver, dossier="captures_debug"):
	import csv, os, time
	from PIL import Image
	from io import BytesIO
	from selenium.webdriver.common.by import By
	from selenium.webdriver.common.keys import Keys

	os.makedirs(dossier, exist_ok=True)

	with open("studocu_liens.csv", encoding="utf-8-sig") as f:
		reader = csv.DictReader(f, delimiter=";")
		next(reader)
		next(reader)
		premiere = next(reader)
		url = premiere["url"]
		titre_brut = premiere["titre"]
		titre = titre_brut.replace(" ", "_").replace("/", "_").replace(":", "_").replace("?", "").replace("\"", "").strip()
		titre = titre[:90]  # limite pour éviter des noms trop longs

	print(f"\n🔗 Accès au document premium : {url}")
	driver.get(url)

	time.sleep(4)
	url_finale = driver.current_url
	print(f"📍 URL après chargement : {url_finale}")

	with open(os.path.join(dossier, "debug_page_source.html"), "w", encoding="utf-8") as f:
		f.write(driver.page_source)
	print("🧩 HTML sauvegardé pour inspection.")

	# 🔎 Zoom (facultatif)
	try:
		driver.execute_script("document.body.style.zoom='61%'")
		time.sleep(1.5)
	except Exception as e:
		print(f"⚠️ Zoom échoué : {e}")

	# 🧭 Scroll progressif sur le conteneur scrollable
	try:
		print("🔍 Recherche du conteneur scrollable…")
		scrollable = driver.find_element(By.ID, "document-wrapper")
		scroll_height = driver.execute_script("return arguments[0].scrollHeight", scrollable)
		client_height = driver.execute_script("return arguments[0].clientHeight", scrollable)

		nb_scrolls = max(1, scroll_height // client_height)
		print(f"📏 scrollHeight = {scroll_height}, clientHeight = {client_height}")
		print(f"📸 Nombre de scrolls estimé : {nb_scrolls}")

		for i in range(nb_scrolls):
			driver.execute_script("arguments[0].scrollTop = arguments[0].clientHeight * arguments[1];",
								  scrollable, i)
			time.sleep(1.2)
			image = Image.open(BytesIO(driver.get_screenshot_as_png()))
			image_path = os.path.join(dossier, f"{titre}_vue{i+1}.png")
			image.save(image_path)
			print(f"✅ Capture {i+1}/{nb_scrolls} enregistrée : {image_path}")
	except Exception as e:
		print(f"❌ Scroll ou capture échouée : {e}")



if __name__ == "__main__":
	# Initialiser le driver
	driver = init_driver()
	try:
		email = "damien.dous@gmail.com"
		mot_de_passe = "azerty1!"
		login_studocu(driver, email, mot_de_passe)
		time.sleep(3)  # ⏳ Attendre que la session soit bien active
		capture_vue_premiere_page(driver=driver)
	finally:
		driver.quit()
	fusionner_captures_verticales(dossier_captures="captures_debug")
