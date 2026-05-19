import csv
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Kategoorialehtede API aadressid, millelt prominence infot korjame
API_URLS = [
    "https://services.err.ee/api/v2/category/getByUrl?url=video&domain=jupiter.err.ee",
    "https://services.err.ee/api/v2/category/getByUrl?url=v-saated&domain=jupiter.err.ee",
    "https://services.err.ee/api/v2/category/getByUrl?url=sarjad&domain=jupiter.err.ee",
    "https://services.err.ee/api/v2/category/getByUrl?url=filmid&domain=jupiter.err.ee",
]

# Põhikaust, kus asuvad sisendfailid ja kuhu salvestatakse väljundfailid
BASE_DIR = Path(r"C:\api_export")

# Positsiooniskooride maatriks: rowOrder + titleOrderInRow -> positionScore
MATRIX_FILE = BASE_DIR / "prominence_matrix.csv"

# Lehekülgede nähtavuse koefitsiendid: page -> pageCoefficient
PAGE_VISIBILITY_FILE = BASE_DIR / "page_visibility.csv"

# Tänane kuupäev failinime ja CSV sisu jaoks
file_date = datetime.now().strftime("%d.%m.%Y")
csv_date = datetime.now().strftime("%d.%m.%Y")

# Loome tänase kuupäevaga alamkausta
OUTPUT_DIR = BASE_DIR / file_date
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Päevane väljundfail
OUTPUT_FILE = OUTPUT_DIR / f"jupiter_prominence_{file_date}.csv"

# Master-fail, kuhu kogutakse kõikide päevade tulemused
MASTER_FILE = BASE_DIR / "jupiter_prominence_master.csv"

# Logifail, kuhu kirjutatakse töö käik ja võimalikud vead
LOG_FILE = OUTPUT_DIR / f"log_jupiter_prominence_{file_date}.txt"

# Lõpliku CSV veerud
fieldnames = [
    "date",
    "title",
    "prominenceScoreTotal",
    "posterUrl",
]


def write_log(message):
    """
    Kirjutab sõnumi korraga ekraanile ja logifaili.
    """
    print(message)
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(message + "\n")


def to_float(value):
    """
    Teisendab väärtuse komakohaga arvuks.
    Toetab nii Eesti komaformaati 0,8 kui ka punktiformaati 0.8.
    """
    if value is None:
        return 0.0

    return float(str(value).strip().replace(",", "."))


def load_prominence_matrix(file_path):
    """
    Loeb sisse prominence_matrix.csv faili.

    Fail peab olema kujul:
    rowOrder;titleOrderInRow;positionScore

    Funktsioon teeb sellest dictionary:
    (rowOrder, titleOrderInRow) -> positionScore
    """
    matrix = {}

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")

        for row in reader:
            row_order = int(row["rowOrder"])
            title_order = int(row["titleOrderInRow"])
            position_score = to_float(row["positionScore"])

            matrix[(row_order, title_order)] = position_score

    return matrix


def load_page_visibility(file_path):
    """
    Loeb sisse page_visibility.csv faili.

    Fail peab olema kujul:
    page;pageCoefficient

    Funktsioon teeb sellest dictionary:
    page -> pageCoefficient
    """
    coefficients = {}

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")

        for row in reader:
            page = row["page"].strip()
            coefficient = to_float(row["pageCoefficient"])

            coefficients[page] = coefficient

    return coefficients


def get_page_name_from_url(api_url):
    """
    Võtab API aadressist url= parameetri väärtuse.
    Näiteks:
    ...?url=v-saated&domain=jupiter.err.ee
    annab tulemuseks:
    v-saated
    """
    parsed_url = urlparse(api_url)
    query_params = parse_qs(parsed_url.query)
    return query_params.get("url", [""])[0]


def find_photo_url(item):
    """
    Otsib pealkirjaga seotud pildi URL-i.

    Kontrollib mõlemat välja:
    - verticalPhotos
    - photos

    Kui leiab photoUrlOriginal või url väärtuse, tagastab selle.
    Kui pilti ei leia, tagastab tühja stringi.
    """
    for photo_group in ["verticalPhotos", "photos"]:
        photos = item.get(photo_group, [])

        if isinstance(photos, list):
            for photo in photos:
                if not isinstance(photo, dict):
                    continue

                if photo.get("photoUrlOriginal"):
                    return photo.get("photoUrlOriginal")

                if photo.get("url"):
                    return photo.get("url")

                photo_types = photo.get("photoTypes", {})

                if isinstance(photo_types, dict):
                    for _, photo_type_data in photo_types.items():
                        if isinstance(photo_type_data, dict):
                            if photo_type_data.get("photoUrlOriginal"):
                                return photo_type_data.get("photoUrlOriginal")

                            if photo_type_data.get("url"):
                                return photo_type_data.get("url")

    return ""


def extract_rows(data, page_name, prominence_matrix, page_visibility):
    """
    Võtab ühest kategoorialehe API vastusest kõik aktiivsed pealkirjad.

    Iga pealkirja kohta arvutatakse:
    positionScore = väärtus prominence_matrix.csv failist
    pageCoefficient = väärtus page_visibility.csv failist
    prominenceScore = positionScore * pageCoefficient

    Selles etapis võib sama title esineda mitu korda.
    Koondamine toimub hiljem aggregate_by_title funktsioonis.
    """
    rows = []

    front_page = (
        data
        .get("data", {})
        .get("category", {})
        .get("frontPage", [])
    )

    # Kui lehe koefitsienti ei leita, kasutatakse vaikimisi 1.0
    page_coefficient = page_visibility.get(page_name, 1.0)

    # row_order on frontPage ploki järjekorranumber
    for row_order, section in enumerate(front_page, start=1):

        if not isinstance(section, dict):
            continue

        # Rea nimi ei lähe lõppfaili, aga row_orderi kaudu leitakse maatriksist skoor
        title_counter = 0

        items = section.get("data", [])

        if not isinstance(items, list):
            continue

        # title_counter on pealkirja järjekord konkreetse rea sees
        for item in items:

            if not isinstance(item, dict):
                continue

            # Arvesse lähevad ainult aktiivse meediaga pealkirjad
            if item.get("heading") and item.get("hasActiveMedia") is True:

                title_counter += 1

                # Leiab maatriksist positsiooni skoori
                # Kui kombinatsiooni ei leita, kasutatakse 0.0
                position_score = prominence_matrix.get(
                    (row_order, title_counter),
                    0.0
                )

                # Arvutab lõpliku skoori sellel konkreetsel lehel ja positsioonil
                prominence_score = position_score * page_coefficient

                rows.append({
                    "date": csv_date,
                    "title": item.get("heading", ""),
                    "posterUrl": find_photo_url(item),
                    "prominenceScore": prominence_score,
                })

    return rows


def aggregate_by_title(rows):
    """
    Koondab read pealkirja järgi.

    Kui sama title esineb mitmel lehel või mitmes reas,
    siis liidetakse kõik tema prominenceScore väärtused kokku.

    Lõpptulemus:
    üks rida ühe title kohta.
    """
    aggregated = {}

    for row in rows:
        title = row["title"]

        if title not in aggregated:
            aggregated[title] = {
                "date": row["date"],
                "title": title,
                "prominenceScoreTotal": 0.0,
                "posterUrl": row["posterUrl"],
            }

        # Summeerib sama title kõik prominenceScore väärtused
        aggregated[title]["prominenceScoreTotal"] += float(row["prominenceScore"])

        # Kui esimesel real polnud posterUrl-i, aga hilisemal real on, kasutab hilisemat
        if not aggregated[title]["posterUrl"] and row["posterUrl"]:
            aggregated[title]["posterUrl"] = row["posterUrl"]

    return list(aggregated.values())


try:
    # Loeb sisse positsiooniskooride maatriksi
    prominence_matrix = load_prominence_matrix(MATRIX_FILE)

    # Loeb sisse lehekülgede nähtavuse koefitsiendid
    page_visibility = load_page_visibility(PAGE_VISIBILITY_FILE)

    write_log(f"Maatriks loetud: {MATRIX_FILE}")
    write_log(f"Lehe koefitsiendid loetud: {PAGE_VISIBILITY_FILE}")

    # Siia kogutakse kõikide lehtede kõik read enne title-põhist koondamist
    all_today_rows = []

    # Käib kõik API aadressid järjest läbi
    for api_url in API_URLS:
        page_name = get_page_name_from_url(api_url)

        write_log(f"Alustan lehe pärimist: {page_name}")

        response = requests.get(api_url, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Ekstraheerib ühe lehe read
        rows = extract_rows(
            data=data,
            page_name=page_name,
            prominence_matrix=prominence_matrix,
            page_visibility=page_visibility,
        )

        all_today_rows.extend(rows)

        write_log(f"Leht valmis: {page_name}. Ridu enne koondamist: {len(rows)}")

    # Koondab sama title kirjed üheks reaks
    aggregated_today_rows = aggregate_by_title(all_today_rows)

    # Kirjutab päevase CSV faili
    with OUTPUT_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(aggregated_today_rows)

    # Loeb master-failist vanad read, välja arvatud tänase kuupäeva omad
    existing_rows = []

    if MASTER_FILE.exists():
        with MASTER_FILE.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")

            for row in reader:
                if row.get("date") != csv_date:
                    existing_rows.append(row)

    # Lisab vanadele ridadele tänased koondatud read
    all_rows = existing_rows + aggregated_today_rows

    # Kirjutab master-faili uuesti üle
    with MASTER_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(all_rows)

    write_log(f"Päevane CSV loodud: {OUTPUT_FILE}")
    write_log(f"Koond-CSV uuendatud: {MASTER_FILE}")
    write_log(f"Ridu enne koondamist: {len(all_today_rows)}")
    write_log(f"Ridu pärast koondamist: {len(aggregated_today_rows)}")
    write_log(f"Masteris ridu kokku: {len(all_rows)}")

except Exception as e:
    write_log(f"ERROR: {e}")
