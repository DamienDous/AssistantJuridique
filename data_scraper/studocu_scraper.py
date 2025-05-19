TEMP_FOLDER = "dossier_temp"
DB_FOLDER = "DB"
SCORE_THRESHOLD = 0.5
SCROLL_OFFSET = 835
MAX_RETRIES = 3

import csv, os, time, cv2, re, random
from glob import glob
from pathlib import Path
import numpy as np
from io import BytesIO
from PIL import Image
from urllib.parse import urlparse
import undetected_chromedriver as uc
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys
from pdf_image_cleaner import process_images

def natural_sort_key(s):
	return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def random_sleep(a=0.8, b=3.0):
	time.sleep(random.uniform(a, b))

def click_human(driver, element):
	actions = ActionChains(driver)
	actions.move_to_element(element).pause(random.uniform(0.1,0.35)).click().perform()

def send_keys_human(element, text, min_delay=0.06, max_delay=0.22):
	for char in text:
		element.send_keys(char)
		random_sleep(random.uniform(min_delay, max_delay))

def studocu_slug(url):
	# 1. Extraire le chemin de l'URL
	path = urlparse(url).path
	# 2. Supprimer le premier / (toujours présent)
	path = path.lstrip('/')
	# 3. Enlever l'ID final (toujours numérique, avant éventuel "?")
	parts = path.split('/')
	# On enlève le dernier élément s'il ne contient que des chiffres
	if parts and parts[-1].isdigit():
		parts = parts[:-1]
	# 4. Joindre tous les morceaux avec un tiret
	slug = '-'.join(parts)
	return slug

def document_deja_traite(titre, dossier=TEMP_FOLDER):
	dossier_temp = os.path.join(dossier, f"{titre}_captures_debug")
	image_fusionnee = f"{dossier_temp}_document_fusionne_final.png"
	return os.path.exists(image_fusionnee)

USER_AGENTS = [
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...",
	# Ajoute-en plusieurs vrais, avec des versions récentes et variées (Edge, Chrome, Safari, etc.)
]

def init_driver():
	options = uc.ChromeOptions()
	options.add_argument("--no-sandbox")
	options.add_argument("--disable-dev-shm-usage")
	options.add_argument("--disable-blink-features=AutomationControlled")
	options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
	
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
		random_sleep(0.3)

		champ_mdp = driver.find_element(By.NAME, "password")
		champ_mdp.clear()
		champ_mdp.send_keys(mot_de_passe)
		random_sleep(0.5)

		# ✅ Simulation humaine : touche Entrée
		champ_mdp.send_keys(Keys.ENTER)
		print("🔐 Connexion envoyée via touche Entrée.")

		WebDriverWait(driver, 10).until(
			EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/fr/')]"))
		)
		print("✅ Connecté à Studocu.")

	except Exception as e:
		print(f"❌ Échec de la connexion : {e}")

def recherche_studocu(driver, mot_cle):
	print(f"🔍 Test de recherche pour : {mot_cle}")
	driver.get("https://www.studocu.com/fr/")

	random_sleep(2.5)
	# Cookies
	try:
		WebDriverWait(driver, 6).until(
			EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Tout refuser')]"))
		).click()
		print("✅ Cookies refusés.")
	except:
		print("ℹ️ Pas de popup cookies détecté.")

	all_liens = set()  # Pour éviter les doublons

	try:
		# Recherche du champ
		champ = WebDriverWait(driver, 10).until(
			EC.element_to_be_clickable((By.CSS_SELECTOR, "input[placeholder*='Rechercher']"))
		)
		for tentative in range(2):
			champ.click()
			random_sleep(0.5)
			champ.clear()
			send_keys_human(champ, mot_cle)
			random_sleep(0.5)
			if champ.get_attribute("value").strip():
				break
			print("⏳ Le mot-clé n’a pas été inséré, nouvelle tentative…")
		
		champ.submit()
		print("✅ Requête envoyée.")

		random_sleep(2)
		page_num = 1
		while True:
			# Attendre chargement des liens
			WebDriverWait(driver, 10).until(
				EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'a[href*="/fr/document/"]'))
			)

			# Récupérer les liens de la page courante
			liens = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/fr/document/"]')
			nb_avant = len(all_liens)
			for l in liens:
				href = l.get_attribute("href")
				if href and "/fr/document/" in href:
					all_liens.add(href)
			print(f"🟢 Page {page_num} : {len(all_liens) - nb_avant} nouveaux liens")

			# Chercher bouton "Suivant"
			try:
				next_btn = driver.find_element(By.CSS_SELECTOR, 'button[data-test-selector="search-document-pagination-next-button"]')
				if next_btn.get_attribute("disabled"):
					print("⏹️ Plus de pages suivantes.")
					break  # Bouton désactivé : fin des pages
				click_human(driver, next_btn)
				page_num += 1
				random_sleep(2.2)  # Attendre chargement nouvelle page
			except Exception as e:
				print("⏹️ Bouton 'Suivant' introuvable ou erreur :", e)
				break

		print(f"🟢 Total {len(all_liens)} liens récupérés pour la recherche '{mot_cle}'")
		for lien in list(all_liens)[:5]:
			print(" ➜", lien)

		return list(all_liens)

	except Exception as e:
		print("❌ Erreur pendant la recherche :", e)
		return []

def recherche_multi_studocu(driver, requetes, csv_output):
	liens_total = []
	for requete in requetes:
		liens = recherche_studocu(driver, requete)
		for url in liens:  # ⛔ Limitation à 2 liens max par mot-clé
			liens_total.append({
				"requete": requete,
				"url": url
			})
			
		random_sleep(random.uniform(2, 4))  # petite pause entre les requêtes

	with open(csv_output, "w", encoding="utf-8-sig", newline='') as f:
		writer = csv.DictWriter(f, fieldnames=["requete", "url"], delimiter=";")
		writer.writeheader()
		writer.writerows(liens_total)

	print(f"✅ Fichier CSV enregistré : {csv_output} ({len(liens_total)} liens)")

def decouper_image_zone_utilisable(image: np.ndarray) -> np.ndarray:
	# Zone utile : ajuste selon tes besoins
	x1, y1 = 1380, 200
	x2, y2 = 2620, 1800
	return image[y1:y2, x1:x2]

def capture_vue_premiere_page(driver, url, dossier):

	random_sleep(4)
	url_finale = driver.current_url
	print(f"📍 URL après chargement : {url_finale}")

	with open(os.path.join(dossier_temp, "debug_page_source.html"), "w", encoding="utf-8") as f:
		f.write(driver.page_source)
	print("🧩 HTML sauvegardé pour inspection.")

	# 🔎 Zoom (facultatif)
	try:
		driver.execute_script("document.body.style.zoom='61%'")
		random_sleep(1.5)
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
			random_sleep(0.8, 1.7)
			image = Image.open(BytesIO(driver.get_screenshot_as_png()))
			image_path = os.path.join(dossier_temp, f"{titre}_vue{i+1}.png")
			image.save(image_path)
			print(f"✅ Capture {i+1}/{nb_scrolls} enregistrée : {image_path}")
	except Exception as e:
		print(f"❌ Scroll ou capture échouée : {e}")

	return dossier_temp

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
			template_path=os.path.join(os.getcwd(), "popup.png"),
			max_offset=images_utiles[i].shape[0] // 2
		)
		y_cuts.append(y_cut)

	# 4. Supprime les popups si besoin :
	#    Pour chaque image (sauf la dernière), détecte un éventuel popup et le remplace
	#    par un patch pris à la même position dans l'image suivante, en tenant compte du scroll (y_cut)
	remplacer_popup_par_patch_suivant(images_utiles, y_cuts, template_path=os.path.join(os.getcwd(), "popup.png"), debug_dir="debug_patches")

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
		random_sleep(3)  # ⏳ Attendre que la session soit bien active
		
		# os.makedirs(TEMP_FOLDER, exist_ok=True)
		# csv_output = "studocu_liens.csv"
		# requetes=["cas pratique droit", "exercice pratique droit"]
		# recherche_multi_studocu(driver, requetes, csv_output)

		with open("studocu_liens.csv", encoding="utf-8-sig") as f:
			reader = csv.DictReader(f, delimiter=";")
			for ligne in reader:
				url = ligne["url"]
				titre = studocu_slug(url)
				dossier_temp = TEMP_FOLDER+"/"+titre
				DB_ori_file_path = DB_FOLDER+"/original/"+titre+".png"
				DB_cleaned_file_path = DB_FOLDER+"/cleaned/"+titre+"_cleaned.png"
				DB_templates_path = DB_FOLDER+"/templates/"
				# 🛑 Vérification si déjà capturé
				if os.path.exists(DB_ori_file_path):
					print(f"⏩ Déjà traité, on saute : {DB_ori_file_path}")
					continue

				os.makedirs(dossier_temp, exist_ok=True)

				for attempt in range(MAX_RETRIES):
					try:
						print(f"\n🔗 Accès au document premium : {url}")
						driver.get(url)
						random_sleep(2, 4)
						capture_vue_premiere_page(driver=driver, url=url, dossier=dossier_temp)
						assembler_document(dossier=dossier_temp, sortie=DB_file_path)
						process_images(DB_ori_file_path, DB_cleaned_file_path, DB_templates_path)
						break  # Succès, on sort du retry
					except Exception as e:
						print(f"❌ Erreur lors de la capture ({attempt+1}/{MAX_RETRIES}) : {e}")
						random_sleep(10, 18)
						# Log (optionnel)
				
				with open("progression_log.csv", "a", encoding="utf-8-sig", newline='') as logf:
					writer = csv.writer(logf, delimiter=";")
					writer.writerow([titre, url, DB_file_path, "OK"])

	finally:
		driver.quit()
