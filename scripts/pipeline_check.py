"""Toru tervisekontroll: allikas -> staging -> mart -> Superseti vaated.

Read-only (vaikimisi). Ei lae andmeid ega käivita transformi.

Käivitus:
    docker compose exec pipeline python scripts/run_pipeline.py check
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from db import get_connection

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
VIEWERS_DIR = DATA_ROOT / "viewers"
METADATA_FILE = DATA_ROOT / "metadata" / "jupiter_metadata.csv"

REQUIRED_TABLES = (
    "staging.catalog",
    "staging.featured_daily",
    "staging.viewers_raw",
    "staging.content_metadata",
    "mart.dim_content",
    "mart.content_structure_pct",
    "mart.fact_content_daily",
    "mart.title_match_daily",
)

REQUIRED_VIEWS = (
    "mart.v_featured_viewership",
    "mart.v_superset_origin_pct",
    "mart.v_superset_content_type_pct",
    "mart.v_superset_featured_top",
)


class Status(str, Enum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class CheckResult:
    name: str
    status: Status
    message: str


def _query_count(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _query_one(cur, sql: str, params: tuple = ()):
    cur.execute(sql, params)
    return cur.fetchone()


def check_db_connection() -> list[CheckResult]:
    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return [CheckResult("DB ühendus", Status.OK, "PostgreSQL vastab")]
    except Exception as exc:
        return [
            CheckResult("DB ühendus", Status.FAIL, f"Ühendus ebaõnnestus: {exc}")
        ]


def check_schema(cur) -> list[CheckResult]:
    results: list[CheckResult] = []
    for rel in REQUIRED_TABLES + REQUIRED_VIEWS:
        cur.execute("SELECT to_regclass(%s)", (rel,))
        exists = cur.fetchone()[0] is not None
        kind = "Vaade" if rel.startswith("mart.v_") else "Tabel"
        if exists:
            results.append(CheckResult(f"{kind} {rel}", Status.OK, "olemas"))
        else:
            results.append(
                CheckResult(
                    f"{kind} {rel}",
                    Status.FAIL,
                    "puudub — käivita init skriptid (vt README)",
                )
            )
    return results


def check_data_files() -> list[CheckResult]:
    results: list[CheckResult] = []
    if METADATA_FILE.is_file():
        results.append(
            CheckResult(
                "Fail meta CSV",
                Status.OK,
                f"{METADATA_FILE.name} olemas",
            )
        )
    else:
        results.append(
            CheckResult(
                "Fail meta CSV",
                Status.FAIL,
                f"puudub: {METADATA_FILE}",
            )
        )

    daily_files = list(VIEWERS_DIR.glob("jupiter_d_*.csv")) if VIEWERS_DIR.is_dir() else []
    weekly_files = list(VIEWERS_DIR.glob("jupiter_w_*.csv")) if VIEWERS_DIR.is_dir() else []
    if daily_files:
        results.append(
            CheckResult(
                "Failid viewers (daily)",
                Status.OK,
                f"{len(daily_files)} faili kaustas data/viewers/",
            )
        )
    else:
        results.append(
            CheckResult(
                "Failid viewers (daily)",
                Status.FAIL,
                "puuduvad jupiter_d_*.csv failid",
            )
        )
    if weekly_files:
        results.append(
            CheckResult(
                "Failid viewers (weekly)",
                Status.OK,
                f"{len(weekly_files)} nädala faili",
            )
        )
    else:
        results.append(
            CheckResult(
                "Failid viewers (weekly)",
                Status.WARN,
                "nädala faile pole (valikuline)",
            )
        )
    return results


def check_staging(cur) -> list[CheckResult]:
    results: list[CheckResult] = []
    thresholds = (
        ("staging.catalog", "SELECT COUNT(*) FROM staging.catalog", 1),
        ("staging.content_metadata", "SELECT COUNT(*) FROM staging.content_metadata", 1),
        ("staging.featured_daily", "SELECT COUNT(*) FROM staging.featured_daily", 1),
        (
            "staging.viewers_raw (daily)",
            "SELECT COUNT(*) FROM staging.viewers_raw WHERE grain = 'daily'",
            1,
        ),
    )
    for name, sql, minimum in thresholds:
        count = _query_count(cur, sql)
        if count >= minimum:
            results.append(CheckResult(name, Status.OK, f"{count} rida"))
        else:
            results.append(
                CheckResult(
                    name,
                    Status.FAIL,
                    f"{count} rida — käivita run-all või ingest-*",
                )
            )

    featured_days = _query_count(
        cur, "SELECT COUNT(DISTINCT feature_date) FROM staging.featured_daily"
    )
    viewer_days = _query_count(
        cur,
        "SELECT COUNT(DISTINCT view_date) FROM staging.viewers_raw WHERE grain = 'daily'",
    )
    if featured_days >= 1 and viewer_days >= 1:
        row = _query_one(
            cur,
            """
            SELECT
                (SELECT MAX(feature_date) FROM staging.featured_daily) AS latest_featured,
                (SELECT MAX(view_date) FROM staging.viewers_raw WHERE grain = 'daily') AS latest_viewers
            """,
        )
        latest_featured, latest_viewers = row
        if latest_featured == latest_viewers:
            results.append(
                CheckResult(
                    "Päevade kattumine (featured vs viewers)",
                    Status.OK,
                    f"mõlemad {latest_featured}",
                )
            )
        else:
            results.append(
                CheckResult(
                    "Päevade kattumine (featured vs viewers)",
                    Status.WARN,
                    f"featured={latest_featured}, viewers={latest_viewers} — "
                    "views_total võib olla tühi viimasel featured päeval",
                )
            )
    return results


def check_mart(cur) -> list[CheckResult]:
    results: list[CheckResult] = []
    mart_checks = (
        ("mart.dim_content", "SELECT COUNT(*) FROM mart.dim_content"),
        (
            "mart.dim_content (meta)",
            "SELECT COUNT(*) FROM mart.dim_content WHERE in_metadata",
        ),
        ("mart.content_structure_pct", "SELECT COUNT(*) FROM mart.content_structure_pct"),
        ("mart.fact_content_daily", "SELECT COUNT(*) FROM mart.fact_content_daily"),
        ("mart.v_featured_viewership", "SELECT COUNT(*) FROM mart.v_featured_viewership"),
        ("mart.v_superset_origin_pct", "SELECT COUNT(*) FROM mart.v_superset_origin_pct"),
        (
            "mart.v_superset_content_type_pct",
            "SELECT COUNT(*) FROM mart.v_superset_content_type_pct",
        ),
        ("mart.v_superset_featured_top", "SELECT COUNT(*) FROM mart.v_superset_featured_top"),
    )
    for name, sql in mart_checks:
        count = _query_count(cur, sql)
        if count > 0:
            results.append(CheckResult(name, Status.OK, f"{count} rida"))
        elif name in {"mart.v_featured_viewership", "mart.v_superset_featured_top"}:
            results.append(
                CheckResult(
                    name,
                    Status.WARN,
                    "0 rida — kontrolli featured/viewers päevade kattumist",
                )
            )
        else:
            results.append(
                CheckResult(
                    name,
                    Status.FAIL,
                    "0 rida — käivita transform (run-all)",
                )
            )

    viewed_rows = _query_count(
        cur,
        """
        SELECT COUNT(*)
        FROM mart.content_structure_pct
        WHERE structure_type = 'viewed'
        """,
    )
    if viewed_rows == 0:
        results.append(
            CheckResult(
                "Struktuur: vaadatud rida",
                Status.WARN,
                "viewed struktuuri read puuduvad — viewers CSV võib puududa featured päeval",
            )
        )
    else:
        results.append(
            CheckResult(
                "Struktuur: vaadatud rida",
                Status.OK,
                f"{viewed_rows} segmenti",
            )
        )
    return results


def check_quality(cur) -> list[CheckResult]:
    results: list[CheckResult] = []
    cur.execute("SELECT to_regclass('quality.check_runs')")
    if cur.fetchone()[0] is None:
        results.append(
            CheckResult(
                "Quality skeem",
                Status.WARN,
                "quality.check_runs puudub — käivita init/07",
            )
        )
        return results

    row = _query_one(
        cur,
        """
        SELECT status, started_at, trigger_source
        FROM quality.check_runs
        ORDER BY started_at DESC
        LIMIT 1
        """,
    )
    if row is None:
        results.append(
            CheckResult(
                "Quality viimane käivitus",
                Status.WARN,
                "pole veel käinud — käivita run-all või quality",
            )
        )
        return results

    status, started_at, trigger_source = row
    if status == "passed":
        results.append(
            CheckResult(
                "Quality viimane käivitus",
                Status.OK,
                f"{status} ({trigger_source}, {started_at})",
            )
        )
    elif status == "failed":
        fail_count = _query_count(
            cur,
            """
            SELECT COUNT(*)
            FROM quality.rule_results AS rr
            INNER JOIN quality.check_runs AS cr ON rr.check_run_id = cr.check_run_id
            WHERE cr.started_at = %s AND rr.severity = 'fail'
            """,
            (started_at,),
        )
        results.append(
            CheckResult(
                "Quality viimane käivitus",
                Status.FAIL,
                f"failed — {fail_count} reeglit severity=fail ({started_at})",
            )
        )
    else:
        results.append(
            CheckResult(
                "Quality viimane käivitus",
                Status.WARN,
                f"staatus={status} ({started_at})",
            )
        )
    return results


def print_results(results: list[CheckResult]) -> tuple[int, int]:
    ok_n = warn_n = fail_n = 0
    for item in results:
        if item.status == Status.OK:
            ok_n += 1
        elif item.status == Status.WARN:
            warn_n += 1
        else:
            fail_n += 1
        print(f"[{item.status.value:4}] {item.name}: {item.message}")
    print()
    print(f"Kokkuvõte: {ok_n} OK, {warn_n} WARN, {fail_n} FAIL")
    return fail_n, warn_n


def run_pipeline_check(*, strict: bool = False) -> int:
    """Käivita kõik kontrollid ja tagasta exit code."""
    print("Jupiteri toru kontroll (allikas -> staging -> mart -> Superseti vaated)")
    print()

    all_results: list[CheckResult] = []

    file_results = check_data_files()
    all_results.extend(file_results)

    conn_results = check_db_connection()
    all_results.extend(conn_results)
    if any(r.status == Status.FAIL for r in conn_results):
        print_results(all_results)
        return 1

    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                all_results.extend(check_schema(cur))
                all_results.extend(check_staging(cur))
                all_results.extend(check_mart(cur))
                all_results.extend(check_quality(cur))
    except Exception as exc:
        all_results.append(
            CheckResult("Kontroll", Status.FAIL, f"Ootamatu viga: {exc}")
        )
        print_results(all_results)
        return 1

    fail_n, warn_n = print_results(all_results)

    if fail_n:
        print("Tulemus: EBAÕNNESTUS — paranda FAIL read ja käivita uuesti.")
        return 1
    if strict and warn_n:
        print("Tulemus: EBAÕNNESTUS (--strict režiimis WARN loetakse veaks).")
        return 1
    if warn_n:
        print("Tulemus: HOIATUS — toru töötab, aga on tähelepanu vajavaid kohti.")
        return 0
    print("Tulemus: OK — andmevoog on terviklik.")
    return 0
