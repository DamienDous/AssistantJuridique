import time
import os
import random
import requests
import fitz  # PyMuPDF
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
import unicodedata

# Liste des mots-clés pertinents
keywords = [
    "droit", "jurisprudence", "cas pratique", "droit civil", "responsabilité",
    "obligations", "contrat", "exemple de cas pratique", "corrigé", "consultation"
]

# Patterns de pages à ignorer
exclude_patterns = ["mentions-legales", "cookies", "plan-du-site", "/legal", "/privacy", "/accessibilite"]

def init_driver(headless=True):
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    if headless:
        options.add_argument("--headless=new")
    
    driver = uc.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    # Supprimer navigator.webdriver pour passer plus incognito
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """
    })

    return driver

def scrape_website(url):
    visited_urls = set()
    base_url = "/".join(url.split("/")[:3])

    try:
        print("Initialisation du driver Chrome...")
        driver = init_driver(headless=True)
        visit_page(url, driver, visited_urls, base_url)
    except Exception as e:
        print(f"Erreur lors du scraping de {url}: {e}")
    finally:
        try:
            print("Fermeture du navigateur...")
            driver.quit()
        except Exception as e:
            print(f"Erreur lors de la fermeture du navigateur : {e}")

def visit_page(url, driver, visited_urls, base_url, retries=3):
    if url in visited_urls or any(p in url for p in exclude_patterns):
        print(f"Page ignorée ou déjà visitée : {url}")
        return

    visited_urls.add(url)
    print(f"Visite de la page : {url}")

    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        print(f"Page {url} complètement chargée.")

        scrape_pdfs(driver, base_url)
        simulate_clicks(driver)
        scrape_and_save_txt(driver, base_url)

        links = extract_all_links(driver, base_url)
        print(f"Liens trouvés sur {url}: {len(links)} liens")

        for href in links:
            if (
                href
                and href.startswith(base_url)
                and href not in visited_urls
                and not any(x in href for x in ["mailto:", "javascript:", "#logout", "#"])
            ):
                time.sleep(random.uniform(0.5, 1.5))
                print(f"Suivi du lien : {href}")
                visit_page(href, driver, visited_urls, base_url)

    except StaleElementReferenceException as e:
        print(f"Erreur d'élément obsolète sur {url}, réessai... {e}")
        if retries > 0:
            time.sleep(2)
            visit_page(url, driver, visited_urls, base_url, retries - 1)
        else:
            print(f"Échec après plusieurs tentatives sur {url}")
    except TimeoutException as e:
        print(f"Erreur de timeout lors du scraping de {url}: {e}")
    except Exception as e:
        print(f"Erreur lors du scraping de la page {url}: {e}")

def extract_all_links(driver, base_url):
    links = set()
    soup = BeautifulSoup(driver.page_source, "html.parser")
    for tag in soup.find_all(["a", "button", "div"]):
        for attr in ["href", "onclick", "data-href"]:
            raw = tag.get(attr, "")
            if isinstance(raw, str) and "http" in raw:
                clean_url = raw.split("'")[1] if "'" in raw else raw
                if clean_url.startswith(base_url):
                    links.add(clean_url)
    return list(links)

def simulate_clicks(driver):
    try:
        buttons = driver.find_elements(By.XPATH, "//button[contains(., 'Voir le corrigé')]")
        for btn in buttons:
            try:
                btn.click()
                time.sleep(1)
            except:
                continue
    except:
        pass

def scrape_pdfs(driver, base_url):
    try:
        print("Scraping des PDFs...")
        links = driver.find_elements(By.TAG_NAME, "a")
        pdf_links = [
            link.get_attribute('href')
            for link in links
            if link.get_attribute('href') and link.get_attribute('href').lower().endswith('.pdf')
        ]

        if pdf_links:
            print(f"PDFs trouvés sur cette page : {len(pdf_links)}")
            for pdf in pdf_links:
                try:
                    pdf_content = read_pdf_content(pdf)
                    print(f"Contenu du PDF analysé pour {pdf}.")
                    if any(keyword in pdf_content.lower() for keyword in keywords):
                        download_pdf(pdf, base_url)
                except Exception as e:
                    print(f"Erreur lors de la lecture du PDF {pdf}: {e}")
        else:
            print(f"Aucun PDF trouvé sur {driver.current_url}")
    except Exception as e:
        print(f"Erreur lors du scraping des PDF : {e}")

def scrape_and_save_txt(driver, base_url):
    try:
        soup = BeautifulSoup(driver.page_source, "html.parser")

        raw_lines = soup.get_text(separator="\n").splitlines()
        cleaned_lines = []
        for line in raw_lines:
            line = line.strip()
            line = unicodedata.normalize("NFKC", line)
            line = line.replace("’", "'").replace("«", '"').replace("»", '"')
            line = " ".join(line.split())
            if len(line) >= 20:
                cleaned_lines.append(line)
        text = "\n".join(cleaned_lines)
        text_lower = text.lower()

        if any(k in text_lower for k in keywords):
            print("✅ Mots-clés trouvés dans le TEXTE, sauvegarde en cours…")

            title_tag = soup.find("title")
            desc_tag = soup.find("meta", attrs={"name": "description"})
            meta_title = title_tag.text.strip() if title_tag else ""
            meta_description = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""

            header = ""
            if meta_title:
                header += f"### TITLE: {meta_title}\n"
            if meta_description:
                header += f"### DESCRIPTION: {meta_description}\n"

            site_name = base_url.split("//")[1].split("/")[0]
            os.makedirs(site_name, exist_ok=True)

            filename = driver.current_url.replace("https://", "").replace("http://", "").replace("/", "_") + ".txt"
            path = os.path.join(site_name, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write(header + "\n" + text)
            print(f"[TXT] sauvegardé : {path}")
        else:
            print("⛔ Aucun mot-clé dans le TEXTE visible, pas de TXT enregistré.")
    except Exception as e:
        print(f"Erreur lors de l'enregistrement du TXT : {e}")

def read_pdf_content(pdf_url):
    print(f"Lecture du contenu du PDF {pdf_url}")
    response = requests.get(pdf_url, timeout=15)
    with open("temp.pdf", "wb") as f:
        f.write(response.content)
    text = ""
    with fitz.open("temp.pdf") as doc:
        for page in doc:
            text += page.get_text()
    os.remove("temp.pdf")
    return text

def download_pdf(pdf_url, base_url):
    try:
        site_name = base_url.split("//")[1].split("/")[0]
        os.makedirs(site_name, exist_ok=True)

        pdf_data = requests.get(pdf_url, timeout=15)
        pdf_filename = os.path.basename(pdf_url.split("?")[0])
        save_path = os.path.join(site_name, pdf_filename)

        with open(save_path, 'wb') as pdf_file:
            pdf_file.write(pdf_data.content)
        print(f"[PDF] téléchargé : {save_path}")
    except Exception as e:
        print(f"Erreur lors du téléchargement du PDF {pdf_url}: {e}")

if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://idai.pantheonsorbonne.fr"
    scrape_website(url)
