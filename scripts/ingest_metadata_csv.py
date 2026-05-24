"""Lae Jupiteri sisu metaandmed CSV-st PostgreSQL-i.

Siht: `staging.content_metadata` — üks rida iga pealkirja kohta (praegune snapshot).

Oodatav fail: `data/metadata/jupiter_metadata.csv`
Veerud (semikoolon): updated, title, origin, type

Ühendusvõti teiste allikatega on `title` (normaliseeritakse transformis võtmega
mart.normalize_title).

Iga käivituse korral asendatakse kogu staging.content_metadata uue faili sisuga.

Käivitus:
    docker compose exec pipeline python scripts/ingest_metadata_csv.py
"""

from __future__ import annotations

import csv
import sys
from datetime import date, datetime
from pathlib import Path

from psycopg2.extras import execute_batch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import finish_run, get_connection, start_run

METADATA_DIR = Path(__file__).resolve().parent.parent / "data" / "metadata"
DEFAULT_FILE = METADATA_DIR / "jupiter_metadata.csv"

REQUIRED_COLUMNS = {"updated", "title", "origin", "type"}


def parse_updated(value: str) -> date:
    """Loe veeru updated väärtus (kujul 20.05.2026)."""
    return datetime.strptime(value.strip(), "%d.%m.%Y").date()


def open_metadata_csv(path: Path):
    """Ava CSV, proovides UTF-8 ja Windowsi kodeeringuid."""
    for encoding in ("utf-8-sig", "cp1257", "windows-1252"):
        try:
            handle = path.open(encoding=encoding, newline="")
            handle.read(4096)
            handle.seek(0)
            return handle, encoding
        except UnicodeDecodeError:
            continue
    return path.open(encoding="latin-1", newline=""), "latin-1"


def normalize_type_code(raw: str) -> str:
    code = (raw or "").strip().upper()
    if code == "CULTRURE":
        return "CULTURE"
    return code


def read_metadata_rows(path: Path) -> list[dict]:
    """Loe meta CSV failist read."""
    rows: list[dict] = []
    handle, encoding = open_metadata_csv(path)
    with handle:
        reader = csv.DictReader(handle, delimiter=";")
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"Failis {path.name} puuduvad oodatud veerud. "
                f"Oodatud: {sorted(REQUIRED_COLUMNS)}"
            )

        for raw in reader:
            title = (raw.get("title") or "").strip()
            if not title:
                continue

            origin = (raw.get("origin") or "").strip().upper()
            content_type = normalize_type_code(raw.get("type") or "")

            rows.append(
                {
                    "title": title,
                    "updated_at": parse_updated(raw["updated"]),
                    "origin_code": origin,
                    "content_type_code": content_type,
                    "source_file": path.name,
                }
            )

    print(f"{path.name}: {len(rows)} rida (kodeering: {encoding})")
    return rows


def ingest_metadata(path: Path = DEFAULT_FILE) -> int:
    """Lae meta CSV staging.content_metadata tabelisse (täielik asendus)."""
    if not path.exists():
        print(f"Meta CSV puudub: {path}", file=sys.stderr)
        return 1

    parsed = read_metadata_rows(path)
    if not parsed:
        print("Meta CSV ei sisaldanud ühtegi rida.", file=sys.stderr)
        return 1

    # Sama pealkiri failis kaks korda — jääb viimane rida.
    merged: dict[str, dict] = {}
    for row in parsed:
        merged[row["title"]] = row
    db_rows = list(merged.values())
    print(f"Unikaalseid meta ridu: {len(db_rows)}")

    conn = get_connection()
    run_id = None
    try:
        with conn:
            with conn.cursor() as cur:
                run_id = start_run(
                    cur,
                    source_name="jupiter_metadata_csv",
                    row_count=len(db_rows),
                )

                cur.execute("TRUNCATE TABLE staging.content_metadata")

                execute_batch(
                    cur,
                    """
                    INSERT INTO staging.content_metadata (
                        title,
                        updated_at,
                        origin_code,
                        content_type_code,
                        source_file,
                        run_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            row["title"],
                            row["updated_at"],
                            row["origin_code"],
                            row["content_type_code"],
                            row["source_file"],
                            str(run_id),
                        )
                        for row in db_rows
                    ],
                    page_size=500,
                )

                finish_run(
                    cur,
                    run_id=run_id,
                    status="success",
                    row_count=len(db_rows),
                    message="Meta CSV laaditud staging.content_metadata tabelisse.",
                )

        print(f"Valmis. run_id={run_id}, staging.content_metadata ridu: {len(db_rows)}")
        return 0
    except Exception as exc:
        if run_id is not None:
            with conn:
                with conn.cursor() as cur:
                    finish_run(
                        cur,
                        run_id=run_id,
                        status="failed",
                        row_count=None,
                        message=str(exc),
                    )
        print(f"Meta ingest ebaõnnestus: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def main() -> int:
    return ingest_metadata()


if __name__ == "__main__":
    raise SystemExit(main())
