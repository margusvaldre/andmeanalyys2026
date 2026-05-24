"""Lae Jupiteri esiletõstmise skoorid API-st PostgreSQL-i (päevane snapshot).

Sihttabel: `staging.featured_daily` — üks rida iga (feature_date, title) kohta.

Iga käivituse korral:
1. Päri 4 kategoorialehte ja arvuta prominence skoorid
2. Kustuta sama päeva vanad read (kui cron käib mitu korda)
3. Sisesta uued read

Käivitus:
    docker compose exec pipeline python scripts/ingest_featured_api.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from psycopg2.extras import execute_batch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import finish_run, get_connection, start_run, utc_now
from prominence_api import fetch_featured_rows, load_config


def ingest_featured(*, feature_date: date | None = None) -> int:
    """Põhivoog: API + konfig -> staging.featured_daily."""
    run_id = None
    conn = get_connection()
    snapshot_date = feature_date or date.today()

    try:
        print("Laen prominence konfiguratsiooni...")
        prominence_matrix, page_visibility = load_config()

        print("Päring ERR API-st (4 kategoorialehte)...")
        rows = fetch_featured_rows(
            prominence_matrix=prominence_matrix,
            page_visibility=page_visibility,
        )
        print(f"Koondatud {len(rows)} pealkirja.")

        now = utc_now()
        insert_rows = [
            (
                snapshot_date,
                row["title"],
                row["prominence_score_total"],
                row["poster_url"] or None,
            )
            for row in rows
            if row["title"]
        ]

        with conn:
            with conn.cursor() as cur:
                run_id = start_run(
                    cur,
                    source_name="err_featured_api",
                    row_count=len(insert_rows),
                )

                cur.execute(
                    """
                    DELETE FROM staging.featured_daily
                    WHERE feature_date = %s
                    """,
                    (snapshot_date,),
                )
                deleted = cur.rowcount

                if insert_rows:
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
                        """,
                        [
                            (
                                row_date,
                                title,
                                score,
                                poster_url,
                                str(run_id),
                                now,
                            )
                            for row_date, title, score, poster_url in insert_rows
                        ],
                        page_size=500,
                    )

                message = (
                    f"Päev {snapshot_date}: kustutati {deleted} vana rida, "
                    f"lisati {len(insert_rows)} rida."
                )
                finish_run(
                    cur,
                    run_id=run_id,
                    status="success",
                    row_count=len(insert_rows),
                    message=message,
                )

        print(f"Valmis. run_id={run_id}")
        print(f"  feature_date: {snapshot_date}")
        print(f"  kustutatud: {deleted}")
        print(f"  lisatud: {len(insert_rows)}")
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
    return ingest_featured()


if __name__ == "__main__":
    raise SystemExit(main())
