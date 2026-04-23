import os
import time
import re
import csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# Любимата ти логика за папките, че да не търсиш файлчовците като изгубен гащник
try:
    output_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    output_dir = os.getcwd()

csv_file_path = os.path.join(output_dir, 'framar_doctors_full.csv')
progress_file_path = os.path.join(output_dir, 'processed_urls.txt')

# Лимит за работа - 5 часа и 30 минути (19800 секунди), льольо! 
# Иначе GitHub ще те репортне като мазен спамър.
MAX_RUNTIME_SECONDS = 5.5 * 3600
START_TIME = time.time()

def is_time_up():
    """Проверяваме дали не е време да си лягаш, палавник."""
    elapsed = time.time() - START_TIME
    return elapsed > MAX_RUNTIME_SECONDS

def load_processed_urls():
    """Зареждаме паметта на бота, да не повтаряме едни и същи докторчовци."""
    if os.path.exists(progress_file_path):
        with open(progress_file_path, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_processed_url(url):
    """Маркираме жертвите."""
    with open(progress_file_path, 'a', encoding='utf-8') as f:
        f.write(url + '\n')

def save_to_csv(data):
    """Мятаме мръвката директно в кюпа."""
    file_exists = os.path.isfile(csv_file_path)
    with open(csv_file_path, mode='a', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["Name", "Specialty", "Region", "Address", "Phone", "Email", "Dates", "Rating", "Path", "Source_URL"])
        if not file_exists:
            writer.writeheader()
        writer.writerow(data)

def setup_driver():
    """Пускаме машината на стероиди, съобразена с GitHub Actions! Pure brainrot speed!"""
    chrome_options = Options()
    
    # ТОВА Е МАГИЯТА ЗА СКОРОСТТА: Eager load + спиране на визуални боклукчовци
    chrome_options.page_load_strategy = 'eager'
    prefs = {
        "profile.managed_default_content_settings.images": 2, # Без картинки
        "profile.managed_default_content_settings.stylesheet": 2, # Без CSS
        "profile.managed_default_content_settings.fonts": 2 # Без шрифтове
    }
    chrome_options.add_experimental_option("prefs", prefs)

    # Мамка му човече, ако сме в GitHub (в облака), пускаме невидимия режим
    if os.getenv('GITHUB_ACTIONS'):
        print("[!] Скибиди облачен режим активиран (Headless & Fast)")
        chrome_options.add_argument("--headless=new") 
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
    else:
        # Иначе си гледаш как мърда на екрана
        print("[!] Локален турбо режим: Гледай как хвърчи!")
        chrome_options.add_argument("--start-maximized")
        
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def decline_cookies(driver):
    """Натискаме 'Отхвърляне' САМО ВЕДНЪЖ, за да не става паприкаш."""
    try:
        reject_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.cky-btn-reject"))
        )
        reject_btn.click()
        print("[!] Бисквитчовците са в коша!")
        time.sleep(0.5)
    except TimeoutException:
        pass
    except Exception as e:
        print(f"Нещо стана на паприкаш с бутона: {e}")

def extract_doctor_details(driver, url):
    """Бъркаме в профилчето със скоростта на светлината. Без слипове, без бисквитки!"""
    try:
        driver.get(url)
        # Махаме decline_cookies() и time.sleep() от тук. Pure speed!
        
        details = {
            "Name": "N/A", "Specialty": "N/A", "Region": "N/A", 
            "Address": "N/A", "Phone": "N/A", "Email": "N/A", 
            "Dates": "N/A", "Rating": "N/A", "Path": "N/A", "Source_URL": url
        }
        
        details["Name"] = driver.find_element(By.TAG_NAME, "h1").text
        
        try:
            rating_element = driver.find_element(By.CSS_SELECTOR, "span.fl")
            if "оценки" in rating_element.text or "/" in rating_element.text:
                details["Rating"] = rating_element.text.strip()
        except: pass

        try:
            time_tag = driver.find_element(By.CSS_SELECTOR, "time.subheader.last")
            details["Dates"] = time_tag.text
        except: pass

        try:
            crumbs = driver.find_elements(By.CSS_SELECTOR, "#breadcrumbs .section")
            path_text = " > ".join([c.text for c in crumbs if c.text.lower() != "назад"])
            details["Path"] = path_text
        except: pass

        info_elements = driver.find_elements(By.CSS_SELECTOR, "#info p")
        for p in info_elements:
            t = p.text
            if "Специалист:" in t: details["Specialty"] = t.replace("Специалист:", "").strip()
            elif "Населено място:" in t: details["Region"] = t.replace("Населено място:", "").strip()
            elif "Адрес:" in t: details["Address"] = t.replace("Адрес:", "").strip()
            elif "Телефон:" in t: details["Phone"] = t.replace("Телефон:", "").strip()
            elif "E-mail:" in t: details["Email"] = t.replace("E-mail:", "").strip()
            
        return details
    except Exception as e:
        print(f"Мамка му човече, грешка при {url}: {e}")
        return None

def scrape_framar():
    processed_urls = load_processed_urls()
    driver = setup_driver()
    
    try:
        print("Започваме голямото скубане в облака, боклуче...")
        driver.get("https://spravochnik.framar.bg/%D0%BC%D0%B5%D0%B4%D0%B8%D1%86%D0%B8%D0%BD%D1%81%D0%BA%D0%B8-%D1%81%D0%BF%D0%B5%D1%86%D0%B8%D0%B0%D0%BB%D0%B8%D1%81%D1%82%D0%B8")
        
        # Разкарваме ги веднъж и завинаги!
        decline_cookies(driver)
        
        region_elements = driver.find_elements(By.XPATH, "//a[contains(@href, '-%D0%BE%D0%B1%D0%BB%D0%B0%D1%81%D1%82')]")
        region_links = sorted(list(set([el.get_attribute("href") for el in region_elements])))
        
        print(f"Намерих {len(region_links)} региончовци.")

        for region_url in region_links:
            if is_time_up(): break # Спираме, ако времето изтече
            
            print(f"\n--- Област: {region_url} ---")
            page = 1
            previous_first_doc = None  # Спасението ти от безкрайния цикъл, гащник!
            
            while True:
                if is_time_up(): break
                
                p_segment = f"/стр-{page}" if page > 1 else ""
                current_url = f"{region_url.split('?')[0]}{p_segment}?vars=10000,1,0,0"
                driver.get(current_url)
                
                doc_links = driver.find_elements(By.CSS_SELECTOR, "article.item h2.header a")
                doctor_urls = [el.get_attribute("href") for el in doc_links]
                
                if not doctor_urls: break

                # ТУК Е МАГИЯТА: Проверяваме дали сървърчовците не ни въртят същата плоча
                if previous_first_doc == doctor_urls[0]:
                    print(f"Мамка му човече, ударихме на камък! Сайтът върти същите докторчовци. Бягаме!")
                    break
                
                previous_first_doc = doctor_urls[0]

                print(f"Страница {page}: {len(doctor_urls)} потенциални жертви.")
                
                for doc_url in doctor_urls:
                    if is_time_up(): break
                    if doc_url in processed_urls: continue
                    
                    details = extract_doctor_details(driver, doc_url)
                    if details:
                        save_to_csv(details)
                        save_processed_url(doc_url)
                        processed_urls.add(doc_url)
                        print(f"  [+] Оскубан: {details['Name']}")
                    
                    # Малък таймер, за да не ни баннат, че сме прекалено бързи
                    time.sleep(0.2)
                
                page += 1
            
            if is_time_up():
                print("--- ВРЕМЕТО ИЗТЕЧЕ! Спираме за днес, гащник. ---")
                break

    finally:
        driver.quit()
        print(f"\n--- ГОТОВО, БОКЛУЧЕ! ---")

if __name__ == "__main__":
    scrape_framar()
