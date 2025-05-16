import os
from pathlib import Path
import re
from PIL import Image
import cv2
import numpy as np
from glob import glob

SCORE_THRESHOLD = 0.4


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
	
def find_best_patch(img_current, img_next, x, y, w, h, max_offset=10):
	best_score = float("inf")
	best_patch = None
	original_patch = img_current[y:y+h, x:x+w]

	# Recherche locale autour de la position initiale (±max_offset pixels verticalement)
	for dy in range(-max_offset, max_offset + 1):
		y_candidate = y + dy
		# Vérifier que le patch est dans les limites de l'image suivante
		if 0 <= y_candidate <= img_next.shape[0] - h:
			candidate_patch = img_next[y_candidate:y_candidate+h, x:x+w]
			# Calculer l'erreur quadratique moyenne pour déterminer le meilleur patch
			score = np.sum((original_patch.astype(int) - candidate_patch.astype(int)) ** 2)
			if score < best_score:
				best_score = score
				best_patch = candidate_patch

	return best_patch

def detect_popup_bbox(res, threshold=0.7):
	ys, xs = np.where(res >= threshold)
	if len(xs) == 0:
		return None
	# On cherche le Y max (le plus bas), puis tous les X associés
	y_popup = np.max(ys)
	xs_popup = xs[ys == y_popup]
	if len(xs_popup) == 0:
		return None
	x_min = np.min(xs_popup)
	x_max = np.max(xs_popup)
	return (x_min, y_popup, x_max, y_popup)  # (x1, y1, x2, y2)

def remplacer_popup_par_patch_suivant(images_utiles, y_cuts, template_path, debug_dir="debug_patches"):
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
		loc = np.where(res >= threshold)

		res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
		bbox = detect_popup_bbox(res, threshold)

		# ... détection popup ...
		if bbox:
			x1, y1, x2, y2 = bbox
			h_t, w_t = template.shape[:2]
			x2 += w_t
			y2 += h_t

			# Applique le scroll !
			y1_suiv = y1 - y_cut
			y2_suiv = y2 - y_cut
			# Vérifie que ça reste dans les limites
			if y1_suiv < 0: y1_suiv = 0
			if y2_suiv > img_suiv.shape[0]: y2_suiv = img_suiv.shape[0]
			patch_propre = img_suiv[y1_suiv:y2_suiv, x1:x2]
			if patch_propre.shape == (y2-y1, x2-x1, 3):
				img[y1:y2, x1:x2] = patch_propre
				nb_patched += 1
				cv2.imwrite(f"{debug_dir}/debug_popup_patch_img{i}_{x1}_{y1}.png", patch_propre)
			else:
				print(f"Patch incorrect sur img {i+1}: {patch_propre.shape}")


	if nb_patched == 0:
		print("❗ Aucun popup remplacé sur cette série.")
	else:
		print(f"✅ {nb_patched} popup(s) précisément remplacé(s).")

def decouper_image_zone_utilisable(image: np.ndarray) -> np.ndarray:
	# Zone utile : ajuste selon tes besoins
	x1, y1 = 1380, 555
	x2, y2 = 2620, 1800
	return image[y1:y2, x1:x2]

def zone_difference(img1, img2, max_offset=300, template_path="popup.png"):
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

	# Détection popup
	try:
		template = cv2.imread(template_path)
		if template is not None:
			h_t, w_t = template.shape[:2]
			result = cv2.matchTemplate(img2, template, cv2.TM_CCOEFF_NORMED)
			_, max_val, _, max_loc = cv2.minMaxLoc(result)
			print(f"🎯 MatchTemplate score popup: {max_val:.3f}")

			if max_val > 0.7:
				popup_y = max_loc[1]
				print(f"⚠️ Popup détectée précisément à y={popup_y}, hauteur={h_t}")

				# ✅ Nouvelle condition très explicite : 
				# Si popup détectée, alors couper précisément avant la popup
				if popup_y < h:
					best_y = min(best_y, popup_y)
					print(f"🚩 Coupe ajustée précisément AVANT la popup à y={best_y}")

	except Exception as e:
		print(f"❌ Erreur matching template : {e}")

	return best_y

def natural_sort_key(s):
	return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

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

	y_cuts = []
	for i in range(len(images_utiles) - 1):
		y_cut = zone_difference(
			images_utiles[i],
			images_utiles[i+1],
			max_offset=images_utiles[i].shape[0] // 2,
			template_path=os.path.join(dossier, "popup.png")
		)
		y_cuts.append(y_cut)

	# Correction popup sur l'ensemble du set 
	remplacer_popup_par_patch_suivant(images_utiles, y_cuts, template_path=os.path.join(dossier, "popup.png"))

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
	assembler_document()


