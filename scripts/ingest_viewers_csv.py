"""Lae Jupiteri vaadatavuse CSV-failid PostgreSQL-i.

Siht: `staging.viewers_raw`

Oodatavad failid kaustas `data/viewers/`:
- `jupiter_d_YYYYMMDD-YYYYMMDD.csv` — päevane vaade (grain = daily)
- `jupiter_w_YYYYMMDD-YYYYMMDD.csv` — nädala vaade (grain = weekly)

Tähtis:
Nädala fail EI ole päevafailide summa. Need on eraldi allikad.

Ühendusvõti teiste allikatega on `title` (pealkiri).
Metaandmed laetakse skriptiga `ingest_metadata_csv.py` tabelisse `staging.content_metadata`.

Käivitus:
    docker compose exec pipeline python scripts/ingest_viewers_csv.py
"""

from __future__ import annotations

import csv
import io
import re
import sys
from datetime import date, datetime
from pathlib import Path

from psycopg2.extras import execute_batch

from db import finish_run, get_connection, start_run

# Projekti juurkaust/data/viewers — pipeline konteineris mountitakse /app/data
VIEWERS_DIR = Path(__file__).resolve().parent.parent / "data" / "viewers"

# Failinime näide: jupiter_d_20260517-20260517.csv
FILENAME_PATTERN = re.compile(
    r"^jupiter_(?P<grain>[dw])_(?P<start>\d{8})-(?P<end>\d{8})\.csv$",
    re.IGNORECASE,
)


def parse_view_date(value: str) -> date:
    """Loe CSV veeru `date` väärtus (kujul 17.05.2026)."""
    return datetime.strptime(value.strip(), "%d.%m.%Y").date()


def parse_period_yyyymmdd(value: str) -> date:
    """Loe perioodi algus/lõpp failinimest (kujul 20260517)."""
    return datetime.strptime(value, "%Y%m%d").date()


def parse_int(value: str) -> int:
    """Loe vaatamiste arv; tühjad väärtused käsitletakse nullina."""
    cleaned = (value or "").strip().replace(" ", "")
    if cleaned == "":
        return 0
    return int(cleaned)


def discover_viewer_files() -> list[tuple[Path, str, date, date]]:
    """Leia kõik toetatud vaadatavuse CSV-failid ja määra grain + periood."""
    if not VIEWERS_DIR.exists():
        raise FileNotFoundError(f"Kaust puudub: {VIEWERS_DIR}")

    files: list[tuple[Path, str, date, date]] = []
    for path in sorted(VIEWERS_DIR.glob("jupiter_*.csv")):
        match = FILENAME_PATTERN.match(path.name)
        if not match:
            print(f"Jätan vahele (tundmatu nimi): {path.name}")
            continue

        grain_code = match.group("grain").lower()
        grain = "daily" if grain_code == "d" else "weekly"
        period_start = parse_period_yyyymmdd(match.group("start"))
        period_end = parse_period_yyyymmdd(match.group("end"))
        files.append((path, grain, period_start, period_end))
    return files


def open_viewer_csv(path: Path):
    """Ava CSV tekstina, proovides UTF-8, cp1257 ja teisi kodeeringuid.

    ERR failid võivad olla segatud (nt UTF-8 päised, cp1257 keha); 4 KB proov
    ei piisa — dekodeerime kogu faili enne csv.DictReader-it.
    """
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1257", "windows-1252"):
        try:
            text = raw.decode(encoding)
            return io.StringIO(text), encoding
        except UnicodeDecodeError:
            continue
    return io.StringIO(raw.decode("latin-1")), "latin-1"


def read_viewer_rows(
    path: Path,
    *,
    grain: str,
    period_start: date,
    period_end: date,
) -> list[dict]:
    """Loe üks CSV fail sõnastike loendiks."""
    rows: list[dict] = []
    handle, _encoding = open_viewer_csv(path)
    with handle:
        reader = csv.DictReader(handle, delimiter=";")
        required = {"date", "type", "title", "total", "live", "od", "web", "app"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"Failis {path.name} puuduvad oodatud veerud. "
                f"Oodatud: {sorted(required)}"
            )

        for raw in reader:
            title = (raw.get("title") or "").strip()
            if not title:
                continue

            rows.append(
                {
                    "grain": grain,
                    "period_start": period_start,
                    "period_end": period_end,
                    "view_date": parse_view_date(raw["date"]),
                    "content_type": (raw.get("type") or "").strip(),
                    "title": title,
                    "total": parse_int(raw["total"]),
                    "live": parse_int(raw["live"]),
                    "od": parse_int(raw["od"]),
                    "web": parse_int(raw["web"]),
                    "app": parse_int(raw["app"]),
                    "source_file": path.name,
                }
            )
    return rows


def ingest_viewers() -> int:
    """Lae kõik leitud CSV-d ühe pipeline käivituse alla."""
    files = discover_viewer_files()
    if not files:
        print(f"CSV faile ei leitud kaustast {VIEWERS_DIR}")
        return 1

    # Ühendame mitme faili read üheks komplektiks.
    # Võti: grain + periood + pealkiri.
    # Kui sama võti esineb kaks korda, jääb viimane faili rida kehtima.
    merged: dict[tuple, dict] = {}
    for path, grain, period_start, period_end in files:
        parsed = read_viewer_rows(
            path,
            grain=grain,
            period_start=period_start,
            period_end=period_end,
        )
        print(
            f"{path.name}: {len(parsed)} rida "
            f"({grain}, {period_start} .. {period_end})"
        )
        for row in parsed:
            key = (row["grain"], row["period_start"], row["period_end"], row["title"])
            merged[key] = row

    all_db_rows = list(merged.values())
    print(f"Unikaalseid vaadatavuse ridu kokku: {len(all_db_rows)}")

    conn = get_connection()
    run_id = None
    try:
        with conn:
            with conn.cursor() as cur:
                run_id = start_run(
                    cur,
                    source_name="jupiter_viewers_csv",
                    row_count=len(all_db_rows),
                )

                db_tuples = [
                    (
                        str(run_id),
                        row["grain"],
                        row["period_start"],
                        row["period_end"],
                        row["view_date"],
                        row["content_type"],
                        row["title"],
                        row["total"],
                        row["live"],
                        row["od"],
                        row["web"],
                        row["app"],
                        row["source_file"],
                    )
                    for row in all_db_rows
                ]

                execute_batch(
                    cur,
                    """
                    INSERT INTO staging.viewers_raw (
                        run_id,
                        grain,
                        period_start,
                        period_end,
                        view_date,
                        content_type,
                        title,
                        total,
                        live,
                        od,
                        web,
                        app,
                        source_file
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    )
                    """,
                    db_tuples,
                    page_size=500,
                )

                finish_run(
                    cur,
                    run_id=run_id,
                    status="success",
                    row_count=len(db_tuples),
                    message="Vaadatavuse CSV-d laaditud staging.viewers_raw tabelisse.",
                )

        print(f"Valmis. run_id={run_id}, staging.viewers_raw ridu: {len(all_db_rows)}")
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
        print(f"Vaadatavuse ingest ebaõnnestus: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def main() -> int:
    return ingest_viewers()


if __name__ == "__main__":
    raise SystemExit(main())
