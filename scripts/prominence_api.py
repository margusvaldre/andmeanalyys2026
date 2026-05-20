"""Jupiteri esiletõstmise (prominence) skoorid ERR API-st.

Loeb kategoorialehtede API vastuseid, arvutab positsiooniskoori maatriksi ja
lehe nähtavuse koefitsientide abil ning koondab tulemused pealkirja (title) järgi.

Konfiguratsioonifailid (vaikimisi `data/prominence/`):
- prominence_matrix.csv — rowOrder;titleOrderInRow;positionScore
- page_visibility.csv — page;pageCoefficient
"""

from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

API_URLS = [
    "https://services.err.ee/api/v2/category/getByUrl?url=video&domain=jupiter.err.ee",
    "https://services.err.ee/api/v2/category/getByUrl?url=v-saated&domain=jupiter.err.ee",
    "https://services.err.ee/api/v2/category/getByUrl?url=sarjad&domain=jupiter.err.ee",
    "https://services.err.ee/api/v2/category/getByUrl?url=filmid&domain=jupiter.err.ee",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROMINENCE_DIR = PROJECT_ROOT / "data" / "prominence"


def to_float(value) -> float:
    """Teisenda arv stringist (toetab koma- ja punktvormingut)."""
    if value is None:
        return 0.0
    return float(str(value).strip().replace(",", "."))


def load_prominence_matrix(file_path: Path) -> dict[tuple[int, int], float]:
    """Loe prominence_matrix.csv -> (rowOrder, titleOrderInRow) -> positionScore."""
    matrix: dict[tuple[int, int], float] = {}

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            row_order = int(row["rowOrder"])
            title_order = int(row["titleOrderInRow"])
            position_score = to_float(row["positionScore"])
            matrix[(row_order, title_order)] = position_score

    return matrix


def load_page_visibility(file_path: Path) -> dict[str, float]:
    """Loe page_visibility.csv -> page -> pageCoefficient."""
    coefficients: dict[str, float] = {}

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            page = row["page"].strip()
            coefficients[page] = to_float(row["pageCoefficient"])

    return coefficients


def get_page_name_from_url(api_url: str) -> str:
    """Võta API URL-ist url= parameetri väärtus (nt v-saated)."""
    parsed_url = urlparse(api_url)
    query_params = parse_qs(parsed_url.query)
    return query_params.get("url", [""])[0]


def find_photo_url(item: dict) -> str:
    """Otsi pealkirjaga seotud pildi URL verticalPhotos või photos väljadest."""
    for photo_group in ("verticalPhotos", "photos"):
        photos = item.get(photo_group, [])
        if not isinstance(photos, list):
            continue

        for photo in photos:
            if not isinstance(photo, dict):
                continue

            if photo.get("photoUrlOriginal"):
                return photo["photoUrlOriginal"]

            if photo.get("url"):
                return photo["url"]

            photo_types = photo.get("photoTypes", {})
            if isinstance(photo_types, dict):
                for photo_type_data in photo_types.values():
                    if not isinstance(photo_type_data, dict):
                        continue
                    if photo_type_data.get("photoUrlOriginal"):
                        return photo_type_data["photoUrlOriginal"]
                    if photo_type_data.get("url"):
                        return photo_type_data["url"]

    return ""


def extract_rows(
    data: dict,
    page_name: str,
    prominence_matrix: dict[tuple[int, int], float],
    page_visibility: dict[str, float],
) -> list[dict]:
    """Ekstraheeri ühe kategoorialehe aktiivsed pealkirjad koos prominence skooriga."""
    rows: list[dict] = []

    front_page = (
        data.get("data", {}).get("category", {}).get("frontPage", [])
    )
    page_coefficient = page_visibility.get(page_name, 1.0)

    for row_order, section in enumerate(front_page, start=1):
        if not isinstance(section, dict):
            continue

        title_counter = 0
        items = section.get("data", [])

        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            if item.get("heading") and item.get("hasActiveMedia") is True:
                title_counter += 1
                position_score = prominence_matrix.get(
                    (row_order, title_counter),
                    0.0,
                )
                prominence_score = position_score * page_coefficient

                rows.append(
                    {
                        "title": item.get("heading", ""),
                        "poster_url": find_photo_url(item),
                        "prominence_score": prominence_score,
                    }
                )

    return rows


def aggregate_by_title(rows: list[dict]) -> list[dict]:
    """Koonda read pealkirja järgi; liida prominence_score väärtused kokku."""
    aggregated: dict[str, dict] = {}

    for row in rows:
        title = row["title"]
        if title not in aggregated:
            aggregated[title] = {
                "title": title,
                "prominence_score_total": 0.0,
                "poster_url": row["poster_url"],
            }

        aggregated[title]["prominence_score_total"] += float(row["prominence_score"])

        if not aggregated[title]["poster_url"] and row["poster_url"]:
            aggregated[title]["poster_url"] = row["poster_url"]

    return list(aggregated.values())


def fetch_category_page(api_url: str, *, timeout: int = 30) -> dict:
    """Päri ühe kategoorialehe JSON vastus."""
    response = requests.get(api_url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_featured_rows(
    *,
    prominence_matrix: dict[tuple[int, int], float],
    page_visibility: dict[str, float],
    api_urls: list[str] | None = None,
) -> list[dict]:
    """Päri kõik lehed ja tagasta koondatud read (üks rida pealkirja kohta)."""
    urls = api_urls or API_URLS
    all_rows: list[dict] = []

    for api_url in urls:
        page_name = get_page_name_from_url(api_url)
        data = fetch_category_page(api_url)
        page_rows = extract_rows(
            data=data,
            page_name=page_name,
            prominence_matrix=prominence_matrix,
            page_visibility=page_visibility,
        )
        all_rows.extend(page_rows)

    return aggregate_by_title(all_rows)


def default_config_paths(
    prominence_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Tagasta maatriksi ja lehe koefitsientide failiteed."""
    base = prominence_dir or DEFAULT_PROMINENCE_DIR
    return (
        base / "prominence_matrix.csv",
        base / "page_visibility.csv",
    )


def load_config(
    prominence_dir: Path | None = None,
) -> tuple[dict[tuple[int, int], float], dict[str, float]]:
    """Lae mõlemad konfiguratsioonifailid."""
    matrix_path, visibility_path = default_config_paths(prominence_dir)
    return (
        load_prominence_matrix(matrix_path),
        load_page_visibility(visibility_path),
    )
