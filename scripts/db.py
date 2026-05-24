"""PostgreSQL ühendus ja töövoo käivituste logimine.

Iga ingest-skript kirjutab enne tööd rea tabelisse `staging.pipeline_runs`.
Nii näed hiljem:
- millal laadimine käis;
- kas õnnestus;
- mitu rida lisati.

Ühenduse parameetrid tulevad Docker Compose `.env` failist.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import psycopg2


def get_connection():
    """Loo ühendus PostgreSQL-iga.

    Dockeris on host tavaliselt `db`.
    Kohalikult käivitades kasuta `localhost` ja porti `.env` failist.
    """
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", os.environ.get("POSTGRES_USER", "praktikum")),
        password=os.environ.get(
            "DB_PASSWORD", os.environ.get("POSTGRES_PASSWORD", "praktikum")
        ),
        dbname=os.environ.get("DB_NAME", os.environ.get("POSTGRES_DB", "praktikum")),
    )


def utc_now() -> datetime:
    """Aeg UTC-s, et eri keskkondades oleks ajatemplid võrreldavad."""
    return datetime.now(timezone.utc)


def start_run(cur, *, source_name: str, row_count: int | None = None) -> uuid.UUID:
    """Alusta uut pipeline käivitust ja tagasta `run_id`.

    `source_name` eristab allikaid logis, nt `err_catalog_api` või `jupiter_viewers_csv`.
    """
    run_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO staging.pipeline_runs (
            run_id,
            started_at,
            source_name,
            status,
            row_count,
            message
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            str(run_id),
            utc_now(),
            source_name,
            "running",
            row_count,
            "Töö käib.",
        ),
    )
    return run_id


def finish_run(
    cur,
    *,
    run_id: uuid.UUID,
    status: str,
    row_count: int | None,
    message: str,
) -> None:
    """Märgi pipeline käivitus lõpetatuks (`success` või `failed`)."""
    cur.execute(
        """
        UPDATE staging.pipeline_runs
        SET
            finished_at = %s,
            status = %s,
            row_count = %s,
            message = %s
        WHERE run_id = %s
        """,
        (utc_now(), status, row_count, message, str(run_id)),
    )
