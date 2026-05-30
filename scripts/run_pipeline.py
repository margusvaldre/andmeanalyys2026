"""Projekti andmetorustiku käsurealiides.

See fail ei tee ise andmetöötlust. Ta käivitab teisi skripte õiges järjekorras.

Praegused käsud:
- ingest-archives — päevased arhiivid (featured + catalog_daily) CSV-st
- ingest-catalog  — ERR API -> staging.catalog
- ingest-viewers  — CSV failid -> staging.viewers_raw
- ingest-featured — ERR API -> staging.featured_daily
- ingest-metadata — meta CSV -> staging.content_metadata
- ingest-all      — arhiivid + kõik neli järjest
- transform       — SQL: staging -> mart
- quality         — SQL: kirjutab quality.* tulemused (vt init/07_quality_objects.sql)
- check           — read-only kontroll: allikas -> staging -> mart -> Superseti vaated

Näide:
    docker compose exec pipeline python scripts/run_pipeline.py ingest-all
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from db import get_connection
from pipeline_check import run_pipeline_check

SCRIPTS_DIR = Path(__file__).resolve().parent
TRANSFORM_SQL = SCRIPTS_DIR / "01_transform.sql"

ARCHIVE_INGEST_STEPS = ("ingest_daily_archives.py",)

INGEST_STEPS = (
    "ingest_catalog_api.py",
    "ingest_viewers_csv.py",
    "ingest_featured_api.py",
    "ingest_metadata_csv.py",
)

ALL_INGEST_STEPS = ARCHIVE_INGEST_STEPS + INGEST_STEPS


def run_transform() -> int:
    """Käivita scripts/01_transform.sql PostgreSQL-is."""
    if not TRANSFORM_SQL.exists():
        print(f"Transformatsiooni fail puudub: {TRANSFORM_SQL}", file=sys.stderr)
        return 1

    print(f"Käivitan transformatsiooni: {TRANSFORM_SQL.name}")
    sql = TRANSFORM_SQL.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute("SELECT COUNT(*) FROM mart.dim_content")
                dim_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM mart.fact_content_daily")
                fact_count = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM mart.v_featured_viewership"
                )
                correlation_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM mart.content_structure_pct")
                structure_count = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM mart.dim_content WHERE in_metadata"
                )
                meta_dim_count = cur.fetchone()[0]
        print(f"Transformatsioon valmis.")
        print(f"  mart.dim_content: {dim_count} rida ({meta_dim_count} meta ühendusega)")
        print(f"  mart.fact_content_daily: {fact_count} rida")
        print(f"  mart.v_featured_viewership: {correlation_count} rida")
        print(f"  mart.content_structure_pct: {structure_count} rida")
        return 0
    except Exception as exc:
        print(f"Transformatsioon ebaõnnestus: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def run_quality() -> int:
    """Käivita quality.run_checks (vt init/07_quality_objects.sql, käsitsi ka scripts/02_quality_checks.sql)."""
    print("Käivitan andmekvaliteedi kontrollid (quality.run_checks).")
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT quality.run_checks(%s)", ("run_pipeline.py",))
                run_id = cur.fetchone()[0]
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM quality.rule_results
                    WHERE check_run_id = %s AND severity = 'fail'
                    """,
                    (run_id,),
                )
                fail_count = cur.fetchone()[0]
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM quality.rule_results
                    WHERE check_run_id = %s AND severity = 'warn'
                    """,
                    (run_id,),
                )
                warn_count = cur.fetchone()[0]
                if fail_count:
                    cur.execute(
                        """
                        SELECT rule_name, message, failing_count, sample_detail
                        FROM quality.rule_results
                        WHERE check_run_id = %s AND severity = 'fail'
                        ORDER BY rule_name
                        """,
                        (run_id,),
                    )
                    rows = cur.fetchall()
        print(f"  check_run_id: {run_id}")
        if warn_count:
            print(f"  Hoiatusi (warn): {warn_count} — vt quality.rule_results või quality.v_latest_rule_results.")
        if fail_count:
            print(f"  Ebaõnnestunud reeglid (fail): {fail_count}")
            for rule_name, message, failing_count, sample_detail in rows:
                extra = f" (n={failing_count})" if failing_count else ""
                sample = f" Näide: {sample_detail}" if sample_detail else ""
                print(f"    - {rule_name}{extra}: {message}{sample}")
            return 1
        print("  Kõik kriitilised kontrollid läbisid (severity=fail puudub).")
        return 0
    except Exception as exc:
        print(f"Kvaliteedikontroll ebaõnnestus: {exc}", file=sys.stderr)
        print(
            "Kui teade on 'function quality.run_checks does not exist', "
            "käivita üks kord: init/07_quality_objects.sql (vt README).",
            file=sys.stderr,
        )
        return 1
    finally:
        conn.close()


def run_script(script_name: str) -> int:
    """Käivita üks Pythoni skript ja tagasta selle väljumiskood."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name)],
        check=False,
    )
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Jupiteri andmetorustik: sissevõtt, transformatsioon ja andmekvaliteet."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "ingest-archives",
        help="Lae päevased arhiivid CSV-st (data/featured, data/catalog_daily).",
    )
    subparsers.add_parser(
        "ingest-catalog",
        help="Lae videokataloog API-st tabelisse staging.catalog.",
    )
    subparsers.add_parser(
        "ingest-viewers",
        help="Lae vaadatavuse CSV-failid tabelisse staging.viewers_raw.",
    )
    subparsers.add_parser(
        "ingest-featured",
        help="Lae esiletõstmise skoorid API-st tabelisse staging.featured_daily.",
    )
    subparsers.add_parser(
        "ingest-metadata",
        help="Lae sisu metaandmed CSV-st tabelisse staging.content_metadata.",
    )
    subparsers.add_parser(
        "ingest-all",
        help="Lae kataloog, vaadatavus, esiletõstmine ja meta CSV järjest.",
    )
    subparsers.add_parser(
        "transform",
        help="Ehita mart kiht staging andmetest (scripts/01_transform.sql).",
    )
    subparsers.add_parser(
        "quality",
        help="Käivita andmekvaliteedi kontrollid (quality.run_checks).",
    )
    check_parser = subparsers.add_parser(
        "check",
        help="Kontrolli toru tervist (read-only, ei lae andmeid).",
    )
    check_parser.add_argument(
        "--strict",
        action="store_true",
        help="Loenda WARN staatused veaks (exit 1).",
    )
    check_parser.add_argument(
        "--run-quality",
        action="store_true",
        help="Käivita enne kontrolli quality.run_checks.",
    )
    subparsers.add_parser(
        "run-all",
        help="Lae kõik allikad, käivita transformatsioon ja andmekvaliteedi kontrollid.",
    )

    args = parser.parse_args()

    if args.command == "ingest-catalog":
        return run_script("ingest_catalog_api.py")

    if args.command == "ingest-viewers":
        return run_script("ingest_viewers_csv.py")

    if args.command == "ingest-featured":
        return run_script("ingest_featured_api.py")

    if args.command == "ingest-metadata":
        return run_script("ingest_metadata_csv.py")

    if args.command == "ingest-archives":
        return run_script("ingest_daily_archives.py")

    if args.command == "ingest-all":
        for step in ALL_INGEST_STEPS:
            code = run_script(step)
            if code != 0:
                return code
        return 0

    if args.command == "transform":
        return run_transform()

    if args.command == "quality":
        return run_quality()

    if args.command == "check":
        if args.run_quality:
            code = run_quality()
            if code != 0:
                return code
            print()
        return run_pipeline_check(strict=args.strict)

    if args.command == "run-all":
        for step in ALL_INGEST_STEPS:
            code = run_script(step)
            if code != 0:
                return code
        code = run_transform()
        if code != 0:
            return code
        return run_quality()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
