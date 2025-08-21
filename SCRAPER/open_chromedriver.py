import undetected_chromedriver as uc
import os

profile_path = r"C:\temp\selenium_profile"
os.makedirs(profile_path, exist_ok=True)

options = uc.ChromeOptions()
options.add_argument("--window-size=1280,900")
options.add_argument(f'--user-data-dir={profile_path}')

driver = uc.Chrome(options=options)
driver.get("https://chat.openai.com/")
input("Connecte-toi à ChatGPT à la main une seule fois ici, puis appuie sur Entrée pour continuer le script...")