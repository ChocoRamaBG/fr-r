import os
import time
import csv
from urllib.parse import unquote
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# Динамично установяване на работната директория
try:
    output_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    output_dir = os.getcwd()

csv_file_path = os.path.join(output_dir, 'framar_doctors_full.csv')
progress_file_path = os.path.join(output_dir, 'processed_urls.txt')

# Лимит за работа на скрипта (в секунди) за избягване на таймаут грешки при CI/CD платформи
MAX_RUNTIME_SECONDS = 5.5 * 3600
START_TIME = time.time()

def is_time_up():
    """Проверява дали не е превишено максималното разрешено време за работа."""
    elapsed = time.time() - START_TIME
    return elapsed > MAX_RUNTIME_SECONDS

def load_processed_urls():
    """Зарежда вече обработените URL адреси от файл, за да се избегне дублиране."""
    if os.path.exists(progress_file_path):
        with open(progress_file_path, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_processed_url(url):
    """Записва успешно обработения URL адрес в лог файла."""
    with open(progress_file_path, 'a', encoding='utf-8') as f:
        f.write(url + '\n')

def save_to_csv(data):
    """
    Записва извлечените данни в CSV файл. 
    Използва се utf-8-sig за правилна визуализация на кирилица в MS Excel.
    """
    file_exists = os.path.isfile(csv_file_path)
    
    # Дефиниране на разширените колони
    fieldnames = [
        "Name", "Specialty", "Region", "Address", "Phone", "Email", "Website",
        "Dates", "Rating", "Education", "Experience", "Qualifications", 
        "Memberships", "Additional_Info", "Path", "Source_URL"
    ]
    
    with open(csv_file_path, mode='a', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(data)

def setup_driver():
    """Конфигурира и стартира браузъра с оптимизации за скорост и съвместимост с Headless среди."""
    chrome_options = Options()
    
    # Eager load стратегия и блокиране на ресурсоемки елементи (изображения, CSS, шрифтове)
    chrome_options.page_load_strategy = 'eager'
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheet": 2,
        "profile.managed_default_content_settings.fonts": 2
    }
    chrome_options.add_experimental_option("prefs", prefs)

    # Проверка за изпълнение в GitHub Actions (или друга CI среда)
    if os.getenv('GITHUB_ACTIONS'):
        print("[Инфо] Активиран е Headless режим за облачна среда.")
        chrome_options.add_argument("--headless=new") 
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
    else:
        print("[Инфо] Активиран е локален режим (браузърът ще бъде видим).")
        chrome_options.add_argument("--start-maximized")
        
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def decline_cookies(driver):
    """Натиска бутона за отхвърляне на бисквитки, ако такъв е наличен."""
    try:
        reject_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.cky-btn-reject"))
        )
        reject_btn.click()
        print("[Инфо] Банерът за бисквитки е отхвърлен успешно.")
        time.sleep(0.5)
    except TimeoutException:
        pass
    except Exception as e:
        print(f"[Внимание] Проблем при отхвърлянето на бисквитките: {e}")

def extract_doctor_details(driver, url):
    """Извлича и структурира детайлната информация от профила на специалиста."""
    try:
        driver.get(url)
        decoded_url = unquote(url)
        
        details = {
            "Name": "N/A", "Specialty": "N/A", "Region": "N/A", 
            "Address": "N/A", "Phone": "N/A", "Email": "N/A", "Website": "N/A",
            "Dates": "N/A", "Rating": "N/A", "Education": "N/A", "Experience": "N/A",
            "Qualifications": "N/A", "Memberships": "N/A", "Additional_Info": "N/A",
            "Path": "N/A", "Source_URL": decoded_url
        }
        
        try:
            details["Name"] = driver.find_element(By.TAG_NAME, "h1").text
        except Exception:
            pass
        
        try:
            rating_element = driver.find_element(By.CSS_SELECTOR, "div#rate span.fl")
            if "оценки" in rating_element.text or "/" in rating_element.text:
                details["Rating"] = rating_element.text.strip()
        except Exception:
            pass

        try:
            time_tag = driver.find_element(By.CSS_SELECTOR, "time.subheader.last")
            details["Dates"] = time_tag.text.strip()
        except Exception:
            pass

        try:
            crumbs = driver.find_elements(By.CSS_SELECTOR, "#breadcrumbs .section")
            path_text = " > ".join([c.text for c in crumbs if c.text.lower() != "назад"])
            details["Path"] = path_text.strip()
        except Exception:
            pass

        # Итериране през всички дъщерни елементи на информационния блок, за да се уловят 
        # допълнителните секции (Образование, Професионален опит и др.)
        try:
            info_container = driver.find_element(By.ID, "info")
            children = info_container.find_elements(By.XPATH, "./*")
            
            current_section = None
            section_texts = {
                "Education": [],
                "Experience": [],
                "Qualifications": [],
                "Memberships": [],
                "Additional": []
            }

            for child in children:
                tag = child.tag_name.lower()
                text = child.text.strip()
                
                if not text:
                    continue

                if tag == "p":
                    if text.startswith("Специалист:"):
                        details["Specialty"] = text.replace("Специалист:", "").strip()
                    elif text.startswith("Населено място:"):
                        details["Region"] = text.replace("Населено място:", "").strip()
                    elif text.startswith("Адрес:"):
                        details["Address"] = text.replace("Адрес:", "").strip()
                    elif text.startswith("Телефон:"):
                        details["Phone"] = text.replace("Телефон:", "").strip()
                    elif text.startswith("E-mail:"):
                        details["Email"] = text.replace("E-mail:", "").strip()
                    elif text.startswith("Сайт:"):
                        details["Website"] = text.replace("Сайт:", "").strip()
                    elif text.startswith("Още информация:"):
                        # Подсказка, че следва свободен текст
                        current_section = "Additional"
                    else:
                        # Ако сме в активна секция, добавяме текста на параграфа към нея
                        if current_section:
                            section_texts[current_section].append(text)

                elif tag == "h2":
                    t_lower = text.lower()
                    if "образование" in t_lower:
                        current_section = "Education"
                    elif "професионален" in t_lower or "опит" in t_lower or "път" in t_lower:
                        current_section = "Experience"
                    elif "квалификаци" in t_lower or "курс" in t_lower:
                        current_section = "Qualifications"
                    elif "членств" in t_lower:
                        current_section = "Memberships"
                    else:
                        # Непознати заглавия се класифицират като допълнителна информация
                        current_section = "Additional"
                        section_texts[current_section].append(text)

                elif tag in ["ul", "ol", "div"]:
                    if current_section:
                        section_texts[current_section].append(text)

            # Обединяване на събраните масиви от текст в краен стринг
            details["Education"] = "\n".join(section_texts["Education"]).strip() or "N/A"
            details["Experience"] = "\n".join(section_texts["Experience"]).strip() or "N/A"
            details["Qualifications"] = "\n".join(section_texts["Qualifications"]).strip() or "N/A"
            details["Memberships"] = "\n".join(section_texts["Memberships"]).strip() or "N/A"
            details["Additional_Info"] = "\n".join(section_texts["Additional"]).strip() or "N/A"

        except Exception as e:
            print(f"[Внимание] Грешка при парсване на допълнителните данни за {decoded_url}: {e}")
            
        return details
        
    except Exception as e:
        print(f"[Грешка] Неуспешно извличане на детайли за {unquote(url)}: {e}")
        return None

def scrape_framar():
    """Основна функция за итериране през регионите и страниците на справочника."""
    processed_urls = load_processed_urls()
    driver = setup_driver()
    
    try:
        print("[Инфо] Стартиране на процеса по извличане на данни...")
        driver.get("https://spravochnik.framar.bg/%D0%BC%D0%B5%D0%B4%D0%B8%D1%86%D0%B8%D0%BD%D1%81%D0%BA%D0%B8-%D1%81%D0%BF%D0%B5%D1%86%D0%B8%D0%B0%D0%BB%D0%B8%D1%81%D1%82%D0%B8")
        
        decline_cookies(driver)
        
        region_elements = driver.find_elements(By.XPATH, "//a[contains(@href, '-%D0%BE%D0%B1%D0%BB%D0%B0%D1%81%D1%82')]")
        region_links = sorted(list(set([el.get_attribute("href") for el in region_elements])))
        
        print(f"[Инфо] Намерени са {len(region_links)} региона за обхождане.")

        for region_url in region_links:
            if is_time_up(): 
                break 
            
            print(f"\n--- Обработка на регион: {unquote(region_url)} ---")
            page = 1
            previous_first_doc = None
            
            while True:
                if is_time_up(): 
                    break
                
                p_segment = f"/стр-{page}" if page > 1 else ""
                current_url = f"{region_url.split('?')[0]}{p_segment}?vars=10000,1,0,0"
                driver.get(current_url)
                
                doc_links = driver.find_elements(By.CSS_SELECTOR, "article.item h2.header a")
                doctor_urls = [el.get_attribute("href") for el in doc_links]
                
                if not doctor_urls: 
                    break

                # Проверка за повтарящо се съдържание (предотвратяване на безкраен цикъл)
                if previous_first_doc == doctor_urls[0]:
                    print("[Внимание] Засечено е повторение на резултатите. Преминаване към следващия регион.")
                    break
                
                previous_first_doc = doctor_urls[0]

                print(f"Страница {page}: Открити {len(doctor_urls)} профила.")
                
                for doc_url in doctor_urls:
                    if is_time_up(): 
                        break
                    if doc_url in processed_urls: 
                        continue
                    
                    details = extract_doctor_details(driver, doc_url)
                    if details:
                        save_to_csv(details)
                        save_processed_url(doc_url)
                        processed_urls.add(doc_url)
                        print(f"  [+] Успешно записан: {details['Name']} | {unquote(doc_url)}")
                    
                    time.sleep(0.2)
                
                page += 1
            
            if is_time_up():
                print("--- [Инфо] Максималното време за изпълнение изтече. Процесът се спира. ---")
                break

    finally:
        driver.quit()
        print("\n--- [Инфо] Процесът приключи. ---")

if __name__ == "__main__":
    scrape_framar()
