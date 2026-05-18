import csv
import requests
from datetime import datetime
from pathlib import Path

# API aadress, kust võtame Jupiteri videokataloogi andmed
API_URL = "https://services.err.ee/api/v2/series/getSeriesData?type=video"

# Põhikaust, kuhu kõik failid salvestatakse
BASE_DIR = Path(r"C:\api_export")

# Tänane kuupäev formaadis DD-MM-YYYY
date_stamp = datetime.now().strftime("%d-%m-%Y")

# Loob iga päeva jaoks eraldi kausta
# Näiteks: C:\api_export\18-05-2026
OUTPUT_DIR = BASE_DIR / date_stamp
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Päevase CSV faili nimi
OUTPUT_FILE = OUTPUT_DIR / f"video_catalogue_{date_stamp}.csv"

# Koondfail, kuhu kogutakse kõik päevad kokku
MASTER_FILE = BASE_DIR / "video_catalogue_master.csv"

# Logifail, kuhu kirjutatakse töö käik ja võimalikud vead
LOG_FILE = OUTPUT_DIR / f"log_{date_stamp}.txt"

# CSV veerud ja nende järjekord
fieldnames = [
    "date",
    "id",
    "scheduleStart",
    "heading",
    "primaryCategory.name",
    "primaryCategory.relativePath",
    "verticalPhotos.type5.url",
]


# Funktsioon logi kirjutamiseks
# Kirjutab info nii ekraanile kui ka logifaili
def write_log(message):
    print(message)

    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(message + "\n")


try:

    # Teeb API päringu
    response = requests.get(API_URL, timeout=30)

    # Annab vea, kui API vastus ei ole edukas
    response.raise_for_status()

    # Teisendab API JSON-vastuse Python dictionaryks
    data = response.json()

    # Võtab välja kõik videokataloogi itemid
    items = data["data"]["items"]

    # Siia kogume kõik read, mis lähevad CSV faili
    rows = []

    # Käib kõik itemid ükshaaval läbi
    for item in items:

        # Püüab võtta vertical photo URL-i
        # Kui väärtust ei ole, jätab tühjaks
        try:
            vertical_photo_type_5_url = (
                item["verticalPhotos"][0]["photoTypes"]["5"]["url"]
            )

        except (KeyError, IndexError, TypeError):
            vertical_photo_type_5_url = ""

        # Koostab ühe CSV rea
        row = {
            "date": date_stamp,
            "id": item.get("id", ""),
            "scheduleStart": item.get("scheduleStart", ""),
            "heading": item.get("heading", ""),
            "primaryCategory.name": (
                item.get("primaryCategory", {}).get("name", "")
            ),
            "primaryCategory.relativePath": (
                item.get("primaryCategory", {}).get("relativePath", "")
            ),
            "verticalPhotos.type5.url": vertical_photo_type_5_url,
        }

        # Lisab rea rows listi
        rows.append(row)

    # -----------------------------------------
    # 1. PÄEVASE CSV FAILI LOOMINE
    # -----------------------------------------

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            delimiter=";"
        )

        # Kirjutab veerupealkirjad
        writer.writeheader()

        # Kirjutab kõik read faili
        writer.writerows(rows)

    # -----------------------------------------
    # 2. MASTER CSV UUENDAMINE
    # -----------------------------------------

    # Siia kogume vanad read,
    # välja arvatud tänase kuupäeva omad
    existing_rows = []

    # Kontrollib, kas master fail juba eksisteerib
    if MASTER_FILE.exists():

        with MASTER_FILE.open(
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as f:

            reader = csv.DictReader(f, delimiter=";")

            for row in reader:

                # Jätab alles ainult teiste päevade read
                # Tänase kuupäeva read eemaldatakse
                if row.get("date") != date_stamp:
                    existing_rows.append(row)

    # Lisab vanadele ridadele tänased read juurde
    all_rows = existing_rows + rows

    # Kirjutab kogu master faili uuesti üle
    with MASTER_FILE.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            delimiter=";"
        )

        # Veerupealkirjad
        writer.writeheader()

        # Kõik read
        writer.writerows(all_rows)

    # -----------------------------------------
    # LOGIMINE
    # -----------------------------------------

    write_log(f"Päevane CSV loodud: {OUTPUT_FILE}")
    write_log(f"Koond-CSV uuendatud: {MASTER_FILE}")
    write_log(f"Kuupäev {date_stamp} masteris asendatud")
    write_log(f"Tänaseid ridu: {len(rows)}")
    write_log(f"Masteris ridu kokku: {len(all_rows)}")

# Kui midagi läheb valesti,
# kirjutatakse viga logisse
except Exception as e:

    write_log(f"ERROR: {e}")
