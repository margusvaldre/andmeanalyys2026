"""Jupiteri videokataloogi API lugemine.

Seda moodulit kasutab `ingest_catalog_api.py`, et lugeda kataloog API-st.

Miks eraldi moodul?
Kui API URL või väljade tõlgendus muutub, parandad ühes kohas.
"""

from __future__ import annotations

from typing import Any

import requests

# ERR Jupiteri videokataloogi avalik lõpp-punkt.
API_URL = "https://services.err.ee/api/v2/series/getSeriesData?type=video"
TIMEOUT_SECONDS = 30


def extract_photo_url(item: dict[str, Any]) -> str:
    """Võta posteri URL, kui see on JSON-is olemas.

    API struktuur on pesastatud; kui mõni tase puudub, tagastame tühja stringi.
    """
    try:
        return item["verticalPhotos"][0]["photoTypes"]["5"]["url"]
    except (KeyError, IndexError, TypeError):
        return ""


def normalize_item(item: dict[str, Any]) -> dict[str, str]:
    """Teisenda üks API kirje ühtlaseks sõnastikuks.

    Oluline projektis:
    - `heading` on kataloogi pealkiri;
    - hiljem ühendame vaadatavuse ja meta CSV-ga võtmega `title` ≈ `heading`.
    """
    return {
        "catalog_id": str(item.get("id", "")),
        "schedule_start": str(item.get("scheduleStart", "")),
        "heading": str(item.get("heading", "")).strip(),
        "primary_category_name": str(
            item.get("primaryCategory", {}).get("name", "")
        ).strip(),
        "primary_category_path": str(
            item.get("primaryCategory", {}).get("relativePath", "")
        ).strip(),
        "vertical_photo_url": extract_photo_url(item),
    }


def fetch_catalog_items() -> list[dict[str, str]]:
    """Lae kogu videokataloog API-st ja tagasta normaliseeritud read.

    Kontrollime JSON-i kuju, et viga oleks selge juba ingesti alguses,
    mitte alles andmebaasi kirjutamisel.
    """
    response = requests.get(API_URL, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("API vastus ei ole JSON objekt.")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("API vastuses puudub või on vigane väli `data`.")

    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("API vastuses puudub või on vigane väli `data.items`.")

    return [normalize_item(item) for item in items if isinstance(item, dict)]
