"""Päevaste arhiivide eksport ja import (featured + catalog_daily).

Failid (nagu data/viewers/):
- data/featured/jupiter_f_YYYYMMDD-YYYYMMDD.csv
- data/catalog_daily/jupiter_c_YYYYMMDD-YYYYMMDD.csv

Eksport: pärast edukat API ingestit (üks päev korraga).
Import: käsitsi `ingest-archives` — varukoopia taastamiseks (nt uus andmebaas).
  Failid laetakse ükshaaval; cron/run-all arhiive ei loe.
"""

from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from psycopg2.extras import execute_batch

from db import finish_run, get_connection, start_run, utc_now

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
FEATURED_DIR = DATA_ROOT / "featured"
CATALOG_DAILY_DIR = DATA_ROOT / "catalog_daily"

FEATURED_FILENAME = re.compile(
    r"^jupiter_f_(?P<start>\d{8})-(?P<end>\d{8})\.csv$",
    re.IGNORECASE,
)
CATALOG_FILENAME = re.compile(
    r"^jupiter_c_(?P<start>\d{8})-(?P<end>\d{8})\.csv$",
    re.IGNORECASE,
)

FEATURED_COLUMNS = (
    "feature_date",
    "title",
    "prominence_score_total",
    "poster_url",
)
CATALOG_COLUMNS = (
    "snapshot_date",
    "catalog_id",
    "schedule_start",
    "heading",
    "primary_category_name",
    "primary_category_path",
    "vertical_photo_url",
    "source_url",
)


def period_tag(day: date) -> str:
    """Tagasta YYYYMMDD-YYYYMMDD (ühe päeva fail)."""
    stamp = day.strftime("%Y%m%d")
    return f"{stamp}-{stamp}"


def featured_archive_path(day: date) -> Path:
    stamp = day.strftime("%Y%m%d")
    return FEATURED_DIR / f"jupiter_f_{stamp}-{stamp}.csv"


def catalog_archive_path(day: date) -> Path:
    stamp = day.strftime("%Y%m%d")
    return CATALOG_DAILY_DIR / f"jupiter_c_{stamp}-{stamp}.csv"


def parse_yyyymmdd(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def archive_day_from_path(path: Path, pattern: re.Pattern[str]) -> date | None:
    """Päeva kuupäev failinimest (ühepäevase faili puhul start=end)."""
    match = pattern.match(path.name)
    if not match:
        return None
    return parse_yyyymmdd(match.group("start"))


def open_csv_for_read(path: Path):
    for encoding in ("utf-8-sig", "cp1257", "windows-1252"):
        try:
            handle = path.open(encoding=encoding, newline="")
            handle.read(4096)
            handle.seek(0)
            return handle
        except UnicodeDecodeError:
            continue
    return path.open(encoding="latin-1", newline="")


def write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") or "" for key in fieldnames})


def export_featured_day(feature_date: date) -> int:
    """Ekspordi ühe päeva featured_daily read CSV-sse."""
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT feature_date, title, prominence_score_total, poster_url
                    FROM staging.featured_daily
                    WHERE feature_date = %s
                    ORDER BY title
                    """,
                    (feature_date,),
                )
                db_rows = cur.fetchall()
        if not db_rows:
            print(f"Featured arhiiv: {feature_date} — ridu pole, faili ei kirjutata.")
            return 0

        rows = [
            {
                "feature_date": row[0].isoformat(),
                "title": row[1],
                "prominence_score_total": str(row[2]),
                "poster_url": row[3] or "",
            }
            for row in db_rows
        ]
        path = featured_archive_path(feature_date)
        write_csv(path, FEATURED_COLUMNS, rows)
        print(f"Featured arhiiv: kirjutatud {path.name} ({len(rows)} rida).")
        return 0
    finally:
        conn.close()


def export_catalog_daily_day(snapshot_date: date) -> int:
    """Ekspordi ühe päeva catalog_daily read CSV-sse."""
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        snapshot_date,
                        catalog_id,
                        schedule_start,
                        heading,
                        primary_category_name,
                        primary_category_path,
                        vertical_photo_url,
                        source_url
                    FROM staging.catalog_daily
                    WHERE snapshot_date = %s
                    ORDER BY catalog_id
                    """,
                    (snapshot_date,),
                )
                db_rows = cur.fetchall()
        if not db_rows:
            print(f"Catalog arhiiv: {snapshot_date} — ridu pole, faili ei kirjutata.")
            return 0

        rows = [
            {
                "snapshot_date": row[0].isoformat(),
                "catalog_id": row[1],
                "schedule_start": row[2] or "",
                "heading": row[3],
                "primary_category_name": row[4] or "",
                "primary_category_path": row[5] or "",
                "vertical_photo_url": row[6] or "",
                "source_url": row[7] or "",
            }
            for row in db_rows
        ]
        path = catalog_archive_path(snapshot_date)
        write_csv(path, CATALOG_COLUMNS, rows)
        print(f"Catalog arhiiv: kirjutatud {path.name} ({len(rows)} rida).")
        return 0
    finally:
        conn.close()


@dataclass
class FileParseResult:
    rows: list[dict[str, Any]]
    skipped: int


def _parse_featured_row(raw: dict[str, str], *, path_name: str, line_no: int) -> dict[str, Any] | None:
    title = (raw.get("title") or "").strip()
    if not title:
        return None
    try:
        feature_date = date.fromisoformat((raw.get("feature_date") or "").strip())
        score_raw = (raw.get("prominence_score_total") or "").strip().replace(" ", "")
        if not score_raw:
            raise ValueError("prominence_score_total on tühi")
        return {
            "feature_date": feature_date,
            "title": title,
            "prominence_score_total": Decimal(score_raw),
            "poster_url": (raw.get("poster_url") or "").strip() or None,
            "source_file": path_name,
        }
    except (ValueError, InvalidOperation) as exc:
        print(
            f"  {path_name} rida {line_no}: vahele jäetud ({exc})",
            file=sys.stderr,
        )
        return None


def _parse_catalog_row(raw: dict[str, str], *, path_name: str, line_no: int) -> dict[str, Any] | None:
    catalog_id = (raw.get("catalog_id") or "").strip()
    heading = (raw.get("heading") or "").strip()
    if not catalog_id or not heading:
        return None
    try:
        snapshot_date = date.fromisoformat((raw.get("snapshot_date") or "").strip())
        source_url = (raw.get("source_url") or "").strip()
        if not source_url:
            raise ValueError("source_url on tühi")
        return {
            "snapshot_date": snapshot_date,
            "catalog_id": catalog_id,
            "schedule_start": (raw.get("schedule_start") or "").strip() or None,
            "heading": heading,
            "primary_category_name": (raw.get("primary_category_name") or "").strip() or None,
            "primary_category_path": (raw.get("primary_category_path") or "").strip() or None,
            "vertical_photo_url": (raw.get("vertical_photo_url") or "").strip() or None,
            "source_url": source_url,
            "source_file": path_name,
        }
    except ValueError as exc:
        print(
            f"  {path_name} rida {line_no}: vahele jäetud ({exc})",
            file=sys.stderr,
        )
        return None


def _read_featured_file(path: Path) -> FileParseResult:
    rows: list[dict[str, Any]] = []
    skipped = 0
    with open_csv_for_read(path) as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if not reader.fieldnames or not set(FEATURED_COLUMNS).issubset(
            set(reader.fieldnames)
        ):
            raise ValueError(
                f"Failis {path.name} puuduvad veerud. Oodatud: {list(FEATURED_COLUMNS)}"
            )
        for line_no, raw in enumerate(reader, start=2):
            parsed = _parse_featured_row(raw, path_name=path.name, line_no=line_no)
            if parsed is None:
                skipped += 1
            else:
                rows.append(parsed)
    return FileParseResult(rows=rows, skipped=skipped)


def _read_catalog_file(path: Path) -> FileParseResult:
    rows: list[dict[str, Any]] = []
    skipped = 0
    with open_csv_for_read(path) as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if not reader.fieldnames or not set(CATALOG_COLUMNS).issubset(set(reader.fieldnames)):
            raise ValueError(
                f"Failis {path.name} puuduvad veerud. Oodatud: {list(CATALOG_COLUMNS)}"
            )
        for line_no, raw in enumerate(reader, start=2):
            parsed = _parse_catalog_row(raw, path_name=path.name, line_no=line_no)
            if parsed is None:
                skipped += 1
            else:
                rows.append(parsed)
    return FileParseResult(rows=rows, skipped=skipped)


def _load_existing_featured_dates(cur) -> set[date]:
    cur.execute("SELECT DISTINCT feature_date FROM staging.featured_daily")
    return {row[0] for row in cur.fetchall()}


def _load_existing_catalog_dates(cur) -> set[date]:
    cur.execute("SELECT DISTINCT snapshot_date FROM staging.catalog_daily")
    return {row[0] for row in cur.fetchall()}


def _insert_featured_rows(cur, rows: list[dict[str, Any]], *, run_id, loaded_at) -> int:
    if not rows:
        return 0
    db_tuples = [
        (
            row["feature_date"],
            row["title"],
            row["prominence_score_total"],
            row["poster_url"],
            str(run_id),
            loaded_at,
        )
        for row in rows
    ]
    execute_batch(
        cur,
        """
        INSERT INTO staging.featured_daily (
            feature_date,
            title,
            prominence_score_total,
            poster_url,
            run_id,
            loaded_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (feature_date, title) DO UPDATE SET
            prominence_score_total = EXCLUDED.prominence_score_total,
            poster_url = EXCLUDED.poster_url,
            run_id = EXCLUDED.run_id,
            loaded_at = EXCLUDED.loaded_at
        """,
        db_tuples,
        page_size=500,
    )
    return len(db_tuples)


def _insert_catalog_rows(cur, rows: list[dict[str, Any]], *, run_id, loaded_at) -> int:
    if not rows:
        return 0
    db_tuples = [
        (
            row["snapshot_date"],
            str(run_id),
            row["catalog_id"],
            row["schedule_start"],
            row["heading"],
            row["primary_category_name"],
            row["primary_category_path"],
            row["vertical_photo_url"],
            row["source_url"],
            loaded_at,
        )
        for row in rows
    ]
    execute_batch(
        cur,
        """
        INSERT INTO staging.catalog_daily (
            snapshot_date,
            run_id,
            catalog_id,
            schedule_start,
            heading,
            primary_category_name,
            primary_category_path,
            vertical_photo_url,
            source_url,
            loaded_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (snapshot_date, catalog_id) DO UPDATE SET
            run_id = EXCLUDED.run_id,
            schedule_start = EXCLUDED.schedule_start,
            heading = EXCLUDED.heading,
            primary_category_name = EXCLUDED.primary_category_name,
            primary_category_path = EXCLUDED.primary_category_path,
            vertical_photo_url = EXCLUDED.vertical_photo_url,
            source_url = EXCLUDED.source_url,
            loaded_at = EXCLUDED.loaded_at
        """,
        db_tuples,
        page_size=500,
    )
    return len(db_tuples)


def ingest_featured_archive(*, missing_only: bool = False) -> int:
    """Lae featured arhiivid ükshaaval staging.featured_daily tabelisse."""
    if not FEATURED_DIR.exists():
        FEATURED_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Featured arhiiv: kaust {FEATURED_DIR} puudus — loodud, faile pole.")
        return 0

    files = sorted(
        path
        for path in FEATURED_DIR.glob("jupiter_f_*.csv")
        if FEATURED_FILENAME.match(path.name)
    )
    if not files:
        print(f"Featured arhiiv: faile ei leitud kaustast {FEATURED_DIR}")
        return 0

    conn = get_connection()
    run_id = None
    loaded_at = utc_now()
    total_rows = 0
    total_skipped = 0
    files_loaded = 0
    try:
        with conn:
            with conn.cursor() as cur:
                existing = _load_existing_featured_dates(cur) if missing_only else set()
                run_id = start_run(
                    cur,
                    source_name="jupiter_featured_archive_csv",
                    row_count=None,
                )
                for path in files:
                    archive_day = archive_day_from_path(path, FEATURED_FILENAME)
                    if archive_day is None:
                        continue
                    if missing_only and archive_day in existing:
                        print(f"{path.name}: juba laetud ({archive_day}), vahele")
                        continue
                    try:
                        result = _read_featured_file(path)
                    except ValueError as exc:
                        print(f"Featured arhiiv: {exc}", file=sys.stderr)
                        return 1
                    if not result.rows:
                        print(
                            f"{path.name}: kehtivaid ridu pole",
                            file=sys.stderr,
                        )
                        return 1
                    total_skipped += result.skipped
                    suffix = f" ({result.skipped} vahele jäetud)" if result.skipped else ""
                    inserted = _insert_featured_rows(
                        cur, result.rows, run_id=run_id, loaded_at=loaded_at
                    )
                    total_rows += inserted
                    files_loaded += 1
                    print(f"{path.name}: {inserted} rida laaditud{suffix}")

                if missing_only and not files_loaded:
                    print("Featured arhiiv: uusi faile polnud (kõik päevad juba laetud).")
                    finish_run(
                        cur,
                        run_id=run_id,
                        status="success",
                        row_count=0,
                        message="Featured arhiiv: uusi päevi polnud.",
                    )
                    return 0

                if files and files_loaded == 0:
                    print(
                        "Featured arhiiv: ühtegi faili ei laaditud.",
                        file=sys.stderr,
                    )
                    return 1

                finish_run(
                    cur,
                    run_id=run_id,
                    status="success",
                    row_count=total_rows,
                    message=f"Featured arhiiv: {files_loaded} faili, {total_rows} rida.",
                )
        if total_skipped:
            print(f"Featured arhiiv: kokku {total_skipped} rida vahele jäetud.")
        print(f"Featured arhiiv ingest valmis. run_id={run_id}, {total_rows} rida.")
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
        print(f"Featured arhiiv ingest ebaõnnestus: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def ingest_catalog_daily_archive(*, missing_only: bool = False) -> int:
    """Lae catalog_daily arhiivid ükshaaval staging.catalog_daily tabelisse."""
    if not CATALOG_DAILY_DIR.exists():
        CATALOG_DAILY_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Catalog arhiiv: kaust {CATALOG_DAILY_DIR} puudus — loodud, faile pole.")
        return 0

    files = sorted(
        path
        for path in CATALOG_DAILY_DIR.glob("jupiter_c_*.csv")
        if CATALOG_FILENAME.match(path.name)
    )
    if not files:
        print(f"Catalog arhiiv: faile ei leitud kaustast {CATALOG_DAILY_DIR}")
        return 0

    conn = get_connection()
    run_id = None
    loaded_at = utc_now()
    total_rows = 0
    total_skipped = 0
    files_loaded = 0
    try:
        with conn:
            with conn.cursor() as cur:
                existing = _load_existing_catalog_dates(cur) if missing_only else set()
                run_id = start_run(
                    cur,
                    source_name="jupiter_catalog_daily_archive_csv",
                    row_count=None,
                )
                for path in files:
                    archive_day = archive_day_from_path(path, CATALOG_FILENAME)
                    if archive_day is None:
                        continue
                    if missing_only and archive_day in existing:
                        print(f"{path.name}: juba laetud ({archive_day}), vahele")
                        continue
                    try:
                        result = _read_catalog_file(path)
                    except ValueError as exc:
                        print(f"Catalog arhiiv: {exc}", file=sys.stderr)
                        return 1
                    if not result.rows:
                        print(
                            f"{path.name}: kehtivaid ridu pole",
                            file=sys.stderr,
                        )
                        return 1
                    total_skipped += result.skipped
                    suffix = f" ({result.skipped} vahele jäetud)" if result.skipped else ""
                    inserted = _insert_catalog_rows(
                        cur, result.rows, run_id=run_id, loaded_at=loaded_at
                    )
                    total_rows += inserted
                    files_loaded += 1
                    print(f"{path.name}: {inserted} rida laaditud{suffix}")

                if missing_only and not files_loaded:
                    print("Catalog arhiiv: uusi faile polnud (kõik päevad juba laetud).")
                    finish_run(
                        cur,
                        run_id=run_id,
                        status="success",
                        row_count=0,
                        message="Catalog arhiiv: uusi päevi polnud.",
                    )
                    return 0

                if files and files_loaded == 0:
                    print(
                        "Catalog arhiiv: ühtegi faili ei laaditud.",
                        file=sys.stderr,
                    )
                    return 1

                finish_run(
                    cur,
                    run_id=run_id,
                    status="success",
                    row_count=total_rows,
                    message=f"Catalog arhiiv: {files_loaded} faili, {total_rows} rida.",
                )
        if total_skipped:
            print(f"Catalog arhiiv: kokku {total_skipped} rida vahele jäetud.")
        print(f"Catalog arhiiv ingest valmis. run_id={run_id}, {total_rows} rida.")
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
        print(f"Catalog arhiiv ingest ebaõnnestus: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def ingest_all_archives(*, missing_only: bool = False) -> int:
    """Lae featured ja catalog_daily arhiivid (ükshaaval)."""
    mode = "ainult puuduvad päevad" if missing_only else "kõik failid"
    print(f"Arhiivide import ({mode}).")
    for fn in (ingest_featured_archive, ingest_catalog_daily_archive):
        code = fn(missing_only=missing_only)
        if code != 0:
            return code
    return 0
