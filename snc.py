# -*- coding: utf-8 -*-

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Funktion, um ein Docker-Secret zu lesen
def get_docker_secret(secret_name):
    secret_path = f"/run/secrets/{secret_name}"
    try:
        with open(secret_path, 'r') as file:
            secret = file.read().strip()  # Entfernt führende und nachfolgende Leerzeichen
        return secret
    except FileNotFoundError:
        print(f"Secret {secret_name} nicht gefunden!")
        return None

# Login-Daten
username = get_docker_secret("sn_user")
password = get_docker_secret("sn_password")
base_url = get_docker_secret("sn_url")

# Headless Chrome konfigurieren
options = Options()
options.add_argument('--headless')  # Keine GUI
options.add_argument('--disable-gpu')  # Deaktiviert GPU-Beschleunigungen
options.add_argument('--no-sandbox')  # Verhindert Sandbox-Probleme

# Chrome WebDriver starten
driver = webdriver.Chrome(options=options)

try:
    # Login-Seite öffnen
    print("Oeffne Login-Seite:", f"{base_url}/login.do")
    driver.get(f"{base_url}/login.do")
    
    # Auf Login-Formular warten
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, "user_name"))
    )
    print("Login-Formular gefunden.")

    # Benutzernamen eingeben
    driver.find_element(By.ID, "user_name").send_keys(username)

    # Passwort eingeben
    driver.find_element(By.ID, "user_password").send_keys(password)

    # Login-Button klicken
    driver.find_element(By.ID, "sysverb_login").click()

    # Warten, bis die nächste Seite geladen ist nice
    WebDriverWait(driver, 40).until(
        EC.url_contains("ui_page.do")
    )

    print("Login erfolgreich. Weiterleitung...")

    # Zielseite nach Login aufrufen
    test_runner_url = f"{base_url}/atf_test_runner.do?sysparm_nostack=true&sysparm_scheduled_tests_only=true"
    driver.get(test_runner_url)

    # Wartezeit, damit die Seite geladen wird
    time.sleep(5)

    # Seitentitel drucken
    print("Seitentitel:", driver.title)
    
    print("Warte 3 Minuten...")
    while True:
        time.sleep(180)  # 3 Minuten warten
        print("Warte 3 Minuten...")  # Oder eine andere Aktion, wenn gewünscht

except Exception as e:
    print(f"Fehler: {str(e)}")
    # Überprüfe die aktuelle URL, um zu sehen, ob wir auf der Login-Seite oder einer anderen Seite sind
    print("Aktuelle URL nach Fehler:", driver.current_url)
    # Optional: Screenshot erstellen, um mehr Informationen zu bekommen
    driver.save_screenshot("error_screenshot.png")
finally:
    # WebDriver beenden
    #driver.quit()
    print("... done")
