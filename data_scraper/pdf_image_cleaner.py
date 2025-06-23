import cv2
import numpy as np
import pytesseract
import os
from glob import glob
import math

def check_homography_valid(M):
	det = np.linalg.det(M)
	if det < 0:
		print("⚠️ Attention : homographie miroir détectée")
		return False  # miroir
	if M[0,0] < 0 or M[1,1] < 0:
		print("⚠️ Attention : homographie avec inversion d’axe détectée")
		return False
	theta = math.atan2(M[1,0], M[0,0])  # en radians
	angle_deg = np.degrees(theta)
	if abs(angle_deg) > 45:
		print("⚠️ Attention : homographie avec rotation excessive détectée :", angle_deg)
		return False

	return True


	return img_gray

def crop_footer_with_orb(img, tpl, min_match_count=10, search_factor=2):
	img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
	tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)

	h_img, w_img = img_gray.shape
	h_tpl, w_tpl = tpl_gray.shape
	# On ne cherche que dans le bas de l'image (ex: 2x la hauteur du template)
	search_height = min(h_img, h_tpl * search_factor)
	y_offset = h_img - search_height
	roi = img_gray[y_offset:, :]  # bas de l'image

	# ORB
	orb = cv2.ORB_create(5000)
	kp1, des1 = orb.detectAndCompute(tpl_gray, None)
	kp2, des2 = orb.detectAndCompute(roi, None)

	if des1 is None or des2 is None:
		print("Pas de features détectées")
		return False

	bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
	matches = bf.match(des1, des2)
	matches = sorted(matches, key=lambda x: x.distance)
	print(len(matches), " match trouvés")
	matches = matches[:len(matches) // 2]
	if len(matches) > min_match_count:
		tpl_pts = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1,1,2)
		roi_pts = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1,1,2)

		# Homography (RANSAC pour robustesse)
		M, mask = cv2.findHomography(tpl_pts, roi_pts, cv2.RANSAC, 5.0)
		print(M)
		if check_homography_valid(M):

			inliers_tpl_pts = tpl_pts[mask.ravel() == 1]
			inliers_tpl_pts_dst = cv2.perspectiveTransform(inliers_tpl_pts, M)

			# Décalage vertical du roi
			inliers_tpl_pts_dst[:,:,1] += y_offset
			min_y = int(np.min(inliers_tpl_pts_dst[:,0,1]))
			print("min point : ", min_y)

			img_cropped = img[:min_y, :]
			
			img_display = img.copy()  # Pour ne pas modifier l’original
			for pt in inliers_tpl_pts_dst:
				x, y = int(pt[0][0]), int(pt[0][1])
				cv2.circle(img_display, (x, y), 5, (0, 0, 255), -1)  # rouge, rayon 5
			tpl_gray_display = tpl_gray.copy()  # Pour ne pas modifier l’original
			for pt in inliers_tpl_pts:
				x, y = int(pt[0][0]), int(pt[0][1])
				cv2.circle(tpl_gray_display, (x, y), 5, (0, 0, 255), -1)  # rouge, rayon 5
			cv2.imshow("Points transformés", img_display)
			cv2.imshow("Points template", tpl_gray_display)
			cv2.waitKey(0)
			cv2.destroyAllWindows()

			print("hauteur template : ", h_tpl)
			print ("img height : ", img.shape[0])
			print(f"On coupe à {min_y}px sur une hauteur totale de {h_img} et un y_offset de {y_offset}")
			
			#find_real_end(img[:y_crop, :])
			return img_cropped
		else:
			print(f"Homographie non calculable")
			return img
	else:
		print(f"Pas assez de matches: {len(matches)}")
		return img

def find_real_end(img, template):
	# On prend la bande juste avant le footer détecté
	gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
	# On segmente la bande en petites lignes (par ex 10 px de haut)
	h = gray.shape[0]
	last_line_with_text = h  # on remonte, en partant du bas
	for y in range(h-10, 0, -10):
		line_img = gray[y:y+10, :]
		txt = pytesseract.image_to_string(line_img, lang='fra')
		if txt.strip() != "":
			last_line_with_text = y+10  # coupe après la dernière ligne avec texte
			break
	# La vraie fin du contenu utile dans l'image d'origine
	y_crop = max(0, y_footer - (h - last_line_with_text))
	return y_crop

def remove_ad_areas_and_concat(img, templates, threshold):

	my_bool = True
	
	while my_bool:
		for tpl in templates:
			img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
			h, w = img.shape[:2]
			tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
			tpl_w, tpl_h = tpl_gray.shape[::-1]
			res = cv2.matchTemplate(img_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
			loc = np.where(res >= threshold)
			# Chercher le point avec la plus grande coordonnée y
			pts = list(zip(*loc[::-1]))
			if pts:
				# On prend le y max (le plus bas)
				pt_max = max(pts, key=lambda pt: pt[1])
				x, y = pt_max[0], pt_max[1]
				(y1, y2) = (y, y+tpl_h)
				print("suppression de :", y1, y2)
				# Coupe et recolle la partie sous le bloc à la place du bloc
				img = np.vstack((img[:y1, :], img[y2:, :]))

				break  # On sort du for et on recommence while True
		else:
			# Le for s'est terminé sans break → on peut sortir du while
			my_bool = False
			break

	return img

def process_images(img_path, output_img_path, templates_folder):
	print(f"process_images : {img_path}")
	THRESHOLD=0.3
	footer_templates = [cv2.imread(f) for f in sorted(glob(os.path.join(templates_folder, "*.png")))]
	img = cv2.imread(img_path)
	img_wo_ad = remove_ad_areas_and_concat(img, footer_templates, THRESHOLD)
	# img_cropped = crop_footer_with_orb(img_wo_ad, footer_templates)
	img_cropped = img_wo_ad[:-200, :]
	cv2.imwrite(output_img_path, img_cropped)


def process_images_folder(input_folder, output_folder, templates_folder):
	os.makedirs(output_folder, exist_ok=True)
	for img_path in glob(os.path.join(input_folder, "*.png")):
		output_img_path = output_folder + "/" + os.path.basename(img_path)
		process_images(img_path, output_img_path, templates_folder)


if __name__ == "__main__":
	process_images_folder("DB/png", "DB/cleaned_png", "DB/templates")