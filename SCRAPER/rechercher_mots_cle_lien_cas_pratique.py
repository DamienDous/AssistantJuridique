import csv
from urllib.parse import urlparse, unquote
from collections import Counter
import re

def normalize(text):
	# Minuscule + suppression des tirets/underscores
	return re.sub(r'[^\w\s]', ' ', text.lower()).replace('-', ' ').replace('_', ' ')

def extraire_mots_utiles(depuis_url):
	# Découpe propre des segments d’URL, supprime les chiffres
	segments = [unquote(p) for p in urlparse(depuis_url).path.split('/') if p and not p.isdigit()]
	mots = []
	for segment in segments:
		mots += normalize(segment).split()
	return set(m for m in mots if len(m) > 3)  # évite "de", "et", "du", etc.

def comparer_liste_lien(nom_fichier):
	nouveaux_mots = []

	with open(nom_fichier, newline='', encoding='utf-8') as csvfile:
		reader = csv.reader(csvfile, delimiter=';')
		for row in reader:
			if len(row) != 2:
				continue
			recherche, url = row
			# mots_recherche = set(normalize(recherche).split())
			mots_url = extraire_mots_utiles(url)
			mots_inattendus = mots_url # - mots_recherche
			nouveaux_mots.extend(mots_inattendus)

	compteur = Counter(nouveaux_mots)
	return compteur.most_common()

# Exemple d'utilisation :
if __name__ == "__main__":
	resultats = comparer_liste_lien("studocu_liens.csv")

	for mot, freq in resultats:
		if freq > 50:
		    print(f"{mot:20s} → {freq}")