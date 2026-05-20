"""Lae Jupiteri videokataloog API-st PostgreSQL-i (inkrementaalne režiim).

Sihttabelid:
- `staging.catalog` — üks rida iga catalog_id kohta (praegune seis)
- `staging.catalog_title_changes` — logi, kui pealkiri (heading) muutub

Loogika iga API käivituse korral (sh cron):
1. Uus catalog_id -> INSERT staging.catalog
2. Olemas catalog_id, aga heading erineb -> logi muutus + uuenda catalog
3. Olemas catalog_id, heading sama -> uuenda ainult last_seen_at
4. API-st kadunud kirjeid EI kustutata (esialgu)

Käivitus:
    docker compose exec pipeline python scripts/ingest_catalog_api.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from psycopg2.extras import execute_batch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog_api import API_URL, fetch_catalog_items
from db import finish_run, get_connection, start_run, utc_now


def dedupe_api_items(raw_items: list[dict[str, str]]) -> list[dict[str, str]]:
    """API võib sama catalog_id mitu korda tagastada; hoiame viimase rea."""
    by_catalog_id: dict[str, dict[str, str]] = {}
    for row in raw_items:
        if row["catalog_id"] and row["heading"]:
            by_catalog_id[row["catalog_id"]] = row
    return list(by_catalog_id.values())


def load_existing_catalog(cur) -> dict[str, str]:
    """Tagasta olemasolev catalog_id -> heading kaart."""
    cur.execute("SELECT catalog_id, heading FROM staging.catalog")
    return {catalog_id: heading for catalog_id, heading in cur.fetchall()}


def ingest_catalog() -> int:
    """Põhivoog: API -> võrdlus olemasolevaga -> uued read + pealkirja muutused."""
    run_id = None
    conn = get_connection()

    try:
        print(f"Laen kataloogi API-st: {API_URL}")
        raw_items = fetch_catalog_items()
        items = dedupe_api_items(raw_items)
        print(f"API-st saadi {len(raw_items)} kirjet, unikaalseid {len(items)}.")

        if len(items) < len(raw_items):
            print(
                f"Eemaldati {len(raw_items) - len(items)} duplikaatkirjet "
                f"(sama catalog_id API vastuses)."
            )

        now = utc_now()
        new_rows: list[tuple] = []
        pending_changes: list[tuple[str, str, str]] = []
        update_changed: list[tuple] = []
        unchanged_ids: list[str] = []

        with conn:
            with conn.cursor() as cur:
                existing = load_existing_catalog(cur)
                existing_count = len(existing)

                for row in items:
                    catalog_id = row["catalog_id"]
                    heading = row["heading"]
                    old_heading = existing.get(catalog_id)

                    if old_heading is None:
                        new_rows.append(
                            (
                                catalog_id,
                                row["schedule_start"],
                                heading,
                                row["primary_category_name"],
                                row["primary_category_path"],
                                row["vertical_photo_url"],
                                API_URL,
                                now,
                                now,
                            )
                        )
                        continue

                    if old_heading != heading:
                        pending_changes.append((catalog_id, old_heading, heading))
                        update_changed.append(
                            (
                                row["schedule_start"],
                                heading,
                                row["primary_category_name"],
                                row["primary_category_path"],
                                row["vertical_photo_url"],
                                now,
                                catalog_id,
                            )
                        )
                    else:
                        unchanged_ids.append(catalog_id)

                run_id = start_run(
                    cur,
                    source_name="err_catalog_api",
                    row_count=len(new_rows) + len(pending_changes),
                )

                change_log = [
                    (str(run_id), catalog_id, old_h, new_h)
                    for catalog_id, old_h, new_h in pending_changes
                ]

                if new_rows:
                    execute_batch(
                        cur,
                        """
                        INSERT INTO staging.catalog (
                            catalog_id,
                            schedule_start,
                            heading,
                            primary_category_name,
                            primary_category_path,
                            vertical_photo_url,
                            source_url,
                            first_seen_at,
                            last_seen_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        new_rows,
                        page_size=500,
                    )

                if change_log:
                    execute_batch(
                        cur,
                        """
                        INSERT INTO staging.catalog_title_changes (
                            run_id,
                            catalog_id,
                            old_heading,
                            new_heading
                        )
                        VALUES (%s, %s, %s, %s)
                        """,
                        change_log,
                        page_size=500,
                    )

                if update_changed:
                    execute_batch(
                        cur,
                        """
                        UPDATE staging.catalog
                        SET
                            schedule_start = %s,
                            heading = %s,
                            primary_category_name = %s,
                            primary_category_path = %s,
                            vertical_photo_url = %s,
                            last_seen_at = %s
                        WHERE catalog_id = %s
                        """,
                        update_changed,
                        page_size=500,
                    )

                if unchanged_ids:
                    cur.execute(
                        """
                        UPDATE staging.catalog
                        SET last_seen_at = %s
                        WHERE catalog_id = ANY(%s)
                        """,
                        (now, unchanged_ids),
                    )

                message = (
                    f"Uusi: {len(new_rows)}, pealkiri muutus: {len(change_log)}, "
                    f"muutumata: {len(unchanged_ids)}."
                )
                finish_run(
                    cur,
                    run_id=run_id,
                    status="success",
                    row_count=len(new_rows) + len(change_log),
                    message=message,
                )

        print(f"Valmis. run_id={run_id}")
        print(f"  staging.catalog ridu (enne): {existing_count}")
        print(f"  uusi kirjeid: {len(new_rows)}")
        print(f"  pealkirja muutusi: {len(change_log)}")
        print(f"  muutumata (ainult last_seen_at): {len(unchanged_ids)}")
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
        print(f"Ingest ebaõnnestus: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def main() -> int:
    return ingest_catalog()


if __name__ == "__main__":
    raise SystemExit(main())
