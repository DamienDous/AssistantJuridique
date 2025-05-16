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
import cv2
import numpy as np
from glob import glob
import csv, os, time
from PIL import Image
from io import BytesIO
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

TEMP_FOLDER = "dossier_temp"
SCORE_THRESHOLD = 0.4
SCROLL_OFFSET = 835
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

def recherche_multi_studocu(driver, requetes, csv_output):
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

def scrape_contenu_premium_depuis_csv(driver, csv_path, dossier_sortie):
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
	
def capture_vue_premiere_page(driver, url, dossier):

	time.sleep(4)
	url_finale = driver.current_url
	print(f"📍 URL après chargement : {url_finale}")

	with open(os.path.join(dossier_temp, "debug_page_source.html"), "w", encoding="utf-8") as f:
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
		SCROLL_OFFSET = int(client_height / 2)
		print(SCROLL_OFFSET)
		nb_scrolls = max(1, 2 * scroll_height // client_height)  # double de captures
		print(f"📏 scrollHeight = {scroll_height}, clientHeight = {client_height}")
		print(f"📸 Nombre de scrolls estimé : {nb_scrolls}")

		for i in range(nb_scrolls):
			driver.execute_script(
				"arguments[0].scrollTop = (arguments[0].clientHeight / 2) * arguments[1];",
				scrollable, i
			)
			time.sleep(1.2)
			image = Image.open(BytesIO(driver.get_screenshot_as_png()))
			image_path = os.path.join(dossier_temp, f"{titre}_vue{i+1}.png")
			image.save(image_path)
			print(f"✅ Capture {i+1}/{nb_scrolls} enregistrée : {image_path}")
	except Exception as e:
		print(f"❌ Scroll ou capture échouée : {e}")

	return dossier_temp

def natural_sort_key(s):
	return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def decouper_image_zone_utilisable(image: np.ndarray) -> np.ndarray:
	# Zone utile : ajuste selon tes besoins
	x1, y1 = 1380, 555
	x2, y2 = 2620, 1800
	return image[y1:y2, x1:x2]

def zone_difference(img1, img2, template_path, max_offset=300):
	h = min(img1.shape[0], img2.shape[0])
	min_score = float("inf")
	best_y = 0

	# Recherche classique du meilleur chevauchement
	for y in range(20, max_offset):
		patch1 = img1[-y:]
		patch2 = img2[:y]
		if patch1.shape[0] != patch2.shape[0]:
			continue
		diff = np.abs(patch1.astype(np.int16) - patch2.astype(np.int16))
		score = np.mean(diff)
		if score < min_score:
			min_score = score
			best_y = y

	print(f"🔍 Meilleur chevauchement initial à y = {best_y} (score={min_score})")

	return best_y

def detect_popup_bbox(res, template_shape, threshold=0.7):
	ys, xs = np.where(res >= threshold)
	if len(xs) == 0:
		return None
	y_popup = np.max(ys)
	xs_popup = xs[ys == y_popup]
	if len(xs_popup) == 0:
		return None
	x_min = np.min(xs_popup)
	h_t, w_t = template_shape
	# On prend le x_min, le y_popup, et on rajoute la largeur/hauteur du template
	return (x_min, y_popup, x_min + w_t, y_popup + h_t)

def remplacer_popup_par_patch_suivant(images_utiles, y_cuts, template_path, debug_dir):
	os.makedirs(debug_dir, exist_ok=True)
	template = cv2.imread(template_path)
	if template is None:
		print(f"❌ Template non trouvé : {template_path}")
		return

	h_t, w_t = template.shape[:2]
	nb_patched = 0

	# Parcourir chaque paire d'images
	for i in range(len(images_utiles) - 1):
		img = images_utiles[i]
		img_suiv = images_utiles[i + 1]
		y_cut = y_cuts[i]

		# Détection précise des popups
		res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
		threshold = SCORE_THRESHOLD  # Utilise la variable globale (ou passe-la en argument)
		bbox = detect_popup_bbox(res, template.shape[:2], threshold)
		# ... détection popup ...
		if bbox:
			x1, y1, x2, y2 = bbox
			print("bbox : ", x1, y1, x2, y2)
			print("y_cut : ", y_cut)

			y1_suiv = y1 - SCROLL_OFFSET
			y2_suiv = y2 - SCROLL_OFFSET

			print("y1_suiv - y2_suiv: ", y1_suiv, y2_suiv)
			# Vérifie que ça reste dans les limites
			if y1_suiv < 0: y1_suiv = 0
			if y2_suiv > img_suiv.shape[0]: y2_suiv = img_suiv.shape[0]
			patch_propre = img_suiv[y1_suiv:y2_suiv, x1:x2]
			if patch_propre.shape == (y2-y1, x2-x1, 3):
				img[y1:y2, x1:x2] = patch_propre
				nb_patched += 1
				cv2.imwrite(f"{debug_dir}/debug_popup_patch_img{i}_{x1}_{y1}.png", patch_propre)
			else:
				print(f"Patch incorrect sur img {i+1}: {patch_propre.shape} au lieu de {(y2-y1, x2-x1, 3)}")

	if nb_patched == 0:
		print("❗ Aucun popup remplacé sur cette série.")
	else:
		print(f"✅ {nb_patched} popup(s) précisément remplacé(s).")

def assembler_document(dossier, sortie):
	
	# 1. Recherche tous les fichiers image (_vue*.png) dans le dossier et trie selon l'ordre naturel
	# Ouvre chaque image (format OpenCV) et stocke dans une liste
	chemins = sorted(glob(os.path.join(dossier, "*_vue*.png")), key=natural_sort_key)
	images = [cv2.imread(p) for p in chemins]
	images_utiles = []

	# 2. Découpe chaque image pour ne garder que la "zone utile" (zone centrale du document)
	for i, img in enumerate(images):
		decoupee = decouper_image_zone_utilisable(img)
		images_utiles.append(decoupee)
		debug_path = os.path.join(dossier, f"decoupe_debug_{i+1:02d}.png")
		cv2.imwrite(debug_path, decoupee)
		print(f"🧪 Image découpée enregistrée : {debug_path} ({decoupee.shape[1]}x{decoupee.shape[0]})")

	# 3. Pour chaque paire d'images consécutives, calcule la hauteur de chevauchement optimale (y_cut)
	# Cela permet de savoir à partir de quelle ligne il faut "assembler" l'image suivante
	y_cuts = []
	for i in range(len(images_utiles) - 1):
		y_cut = zone_difference(
			images_utiles[i],
			images_utiles[i+1],
			template_path=os.path.join(TEMP_FOLDER, "popup.png"),
			max_offset=images_utiles[i].shape[0] // 2
		)
		y_cuts.append(y_cut)

	# 4. Supprime les popups si besoin :
	#    Pour chaque image (sauf la dernière), détecte un éventuel popup et le remplace
	#    par un patch pris à la même position dans l'image suivante, en tenant compte du scroll (y_cut)
	remplacer_popup_par_patch_suivant(images_utiles, y_cuts, template_path=os.path.join(TEMP_FOLDER, "popup.png"), debug_dir="debug_patches")

	# 5. Reconstruit le document fusionné :
	#    Assemble les images en "coupant" les zones de recouvrement déjà utilisées,
	#    et en les collant à la suite les unes des autres.
	h_img, w_img = images_utiles[0].shape[:2]
	segments = [images_utiles[0]]
	for i in range(1, len(images_utiles)):
		y_cut = y_cuts[i-1]  # RÉUTILISE la valeur déjà calculée
		print(f"🔎 Image {i+1}: découpage dynamique à y = {y_cut}")
		segments.append(images_utiles[i][y_cut:])

	# 6. Construit un grand canvas final, colle tous les segments à la suite verticalement
	h_total = sum(seg.shape[0] for seg in segments)
	canvas = np.zeros((h_total, w_img, 3), dtype=np.uint8)

	y_offset = 0
	for seg in segments:
		h = seg.shape[0]
		canvas[y_offset:y_offset + h, :w_img] = seg
		y_offset += h

	# 7. Enregistre l'image fusionnée finale
	cv2.imwrite(sortie, canvas)
	print(f"✅ Document final fusionné enregistré sous : {sortie}")


if __name__ == "__main__":
	# Initialiser le driver
	driver = init_driver()
	try:
		email = "damien.dous@gmail.com"
		mot_de_passe = "azerty1!"
		login_studocu(driver, email, mot_de_passe)
		time.sleep(3)  # ⏳ Attendre que la session soit bien active
		
		os.makedirs(TEMP_FOLDER, exist_ok=True)

		with open("studocu_liens.csv", encoding="utf-8-sig") as f:
			reader = csv.DictReader(f, delimiter=";")
			for ligne in reader:
				print(ligne["url"])
				url = ligne["url"]
				titre_brut = ligne["titre"]
				titre = titre_brut.replace(" ", "_").replace("/", "_").replace(":", "_").replace("?", "").replace("\"", "").strip()
				titre = titre[:30]  # limite pour éviter des noms trop longs
				dossier_temp = TEMP_FOLDER+"/"+titre+"_captures_debug"
				os.makedirs(dossier_temp, exist_ok=True)

				print(f"\n🔗 Accès au document premium : {url}")
				driver.get(url)

				capture_vue_premiere_page(driver=driver, url=url, dossier=dossier_temp)
				assembler_document(dossier=dossier_temp, sortie=dossier_temp+"_document_fusionne_final.png")

	finally:
		driver.quit()
	# fusionner_captures_verticales(dossier="captures_debug")



