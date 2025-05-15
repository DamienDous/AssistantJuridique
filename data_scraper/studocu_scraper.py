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
			image_path = os.path.join(dossier, f"{titre}_vue{i+1}.png")
			image.save(image_path)
			print(f"✅ Capture {i+1}/{nb_scrolls} enregistrée : {image_path}")
	except Exception as e:
		print(f"❌ Scroll ou capture échouée : {e}")


# === Traitement post-capture : Découpe + Alignement + Fusion ===
def natural_sort_key(s):
	return [int(text) if text.isdigit() else text.lower()
			for text in re.split(r'(\d+)', s)]

def decouper_image_zone_utilisable(image: np.ndarray) -> np.ndarray:
	x1, y1 = 1380, 555
	x2, y2 = 2620, 1800
	return image[y1:y2, x1:x2]

def calculer_transformation(img_ref, img_cible):
	orb = cv2.ORB_create(5000)
	kp1, des1 = orb.detectAndCompute(img_ref, None)
	kp2, des2 = orb.detectAndCompute(img_cible, None)
	if des1 is None or des2 is None:
		return np.float32([[1, 0, 0], [0, 1, 0]])
	matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
	matches = matcher.match(des1, des2)
	matches = sorted(matches, key=lambda x: x.distance)[:50]
	if len(matches) < 4:
		return np.float32([[1, 0, 0], [0, 1, 0]])
	pts1 = np.float32([kp1[m.queryIdx].pt for m in matches])
	pts2 = np.float32([kp2[m.trainIdx].pt for m in matches])
	M, _ = cv2.estimateAffinePartial2D(pts2, pts1)
	return M if M is not None else np.float32([[1, 0, 0], [0, 1, 0]])

def fusionner_par_confiance(base, alignee, seuil=10):
	mask_base = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
	mask_alignee = cv2.cvtColor(alignee, cv2.COLOR_BGR2GRAY)
	mask_diff = (np.abs(mask_alignee.astype(int) - mask_base.astype(int)) > seuil).astype(np.uint8) * 255
	fusion = base.copy()
	fusion[mask_diff == 255] = alignee[mask_diff == 255]
	return fusion
import cv2
import numpy as np

def detect_overlay_zone(img: np.ndarray) -> bool:
    """Détecte la présence d’une barre sombre avec bouton vert et texte blanc."""
    if img.shape[0] < 60:
        return False
    h, w = img.shape[:2]
    bande = img[h//2:h//2 + 60]  # zone centrale

    mask_dark = cv2.inRange(bande, (30, 30, 30), (70, 70, 70))       # fond sombre
    mask_white = cv2.inRange(bande, (180, 180, 180), (255, 255, 255))  # texte blanc
    mask_green = cv2.inRange(bande, (0, 140, 14), (80, 255, 94))       # vert fluo

    total = mask_dark.size
    ratio_dark = np.count_nonzero(mask_dark) / total
    ratio_white = np.count_nonzero(mask_white) / total
    ratio_green = np.count_nonzero(mask_green) / total

    if ratio_dark > 0.25 and ratio_white > 0.01 and ratio_green > 0.01:
        print("🧠 Overlay détecté (fond sombre + texte + bouton vert)")
        return True
    return False


def zone_difference(img1, img2, max_offset=300, template_path="popup.png"):
    h = min(img1.shape[0], img2.shape[0])
    min_score = float("inf")
    best_y = 0

    # 1. Calcul du meilleur chevauchement
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

    # 2. Chargement du template pop-up
    try:
        template = cv2.imread(template_path)
        if template is not None:
            h_t, w_t = template.shape[:2]

            # Match dans toute l'image
            result = cv2.matchTemplate(img2, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            print(f"🎯 MatchTemplate score : {max_val:.3f}")

            # Si le match est fort (> 0.8), on coupe la pop-up
            if max_val > 0.8:
                popup_y = max_loc[1]
                print(f"⚠️ Barre flottante détectée à y={popup_y}. Contournement.")
                best_y = max(best_y, popup_y + h_t)  # on coupe en dessous
    except Exception as e:
        print(f"❌ Erreur chargement ou matching template : {e}")

    return best_y


def assembler_document(dossier="captures_debug", sortie="document_fusionne_final.png"):
    chemins = sorted(glob(os.path.join(dossier, "*_vue*.png")), key=natural_sort_key)
    images = [cv2.imread(p) for p in chemins]
    images_utiles = []

    for i, img in enumerate(images):
        decoupee = decouper_image_zone_utilisable(img)
        images_utiles.append(decoupee)
        debug_path = os.path.join(dossier, f"decoupe_debug_{i+1:02d}.png")
        cv2.imwrite(debug_path, decoupee)
        print(f"🧪 Image découpée enregistrée : {debug_path} ({decoupee.shape[1]}x{decoupee.shape[0]})")

    h_img, w_img = images_utiles[0].shape[:2]
    segments = [images_utiles[0]]

    for i in range(1, len(images_utiles)):
        y_cut = zone_difference(
            segments[-1],
            images_utiles[i],
            max_offset=h_img // 2,
            template_path=os.path.join(dossier, "popup.png")
        )
        print(f"🔎 Image {i+1}: découpage dynamique à y = {y_cut}")
        segments.append(images_utiles[i][y_cut:])

    h_total = sum(seg.shape[0] for seg in segments)
    canvas = np.zeros((h_total, w_img, 3), dtype=np.uint8)

    y_offset = 0
    for seg in segments:
        h = seg.shape[0]
        canvas[y_offset:y_offset + h, :w_img] = seg
        y_offset += h

    cv2.imwrite(sortie, canvas)
    print(f"✅ Document final fusionné enregistré sous : {sortie}")





if __name__ == "__main__":
	# Initialiser le driver
	# driver = init_driver()
	# try:
	# 	email = "damien.dous@gmail.com"
	# 	mot_de_passe = "azerty1!"
	# 	login_studocu(driver, email, mot_de_passe)
	# 	time.sleep(3)  # ⏳ Attendre que la session soit bien active
	# 	capture_vue_premiere_page(driver=driver)
	# finally:
	# 	driver.quit()
	# fusionner_captures_verticales(dossier="captures_debug")

	assembler_document()


