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
FEATURED_DIR = DATA_ROOT / "featured"
CATALOG_DAILY_DIR = DATA_ROOT / "catalog_daily"
METADATA_FILE = DATA_ROOT / "metadata" / "jupiter_metadata.csv"

REQUIRED_TABLES = (
    "staging.catalog",
    "staging.catalog_daily",
    "staging.featured_daily",
    "staging.viewers_raw",
    "staging.content_metadata",
    "mart.dim_content",
    "mart.content_structure_pct",
    "mart.content_structure_period_pct",
    "mart.fact_content_daily",
    "mart.title_match_daily",
)

REQUIRED_VIEWS = (
    "mart.v_featured_viewership",
    "mart.v_featured_viewership_period",
    "mart.v_superset_origin_pct",
    "mart.v_superset_content_type_pct",
    "mart.v_superset_featured_top",
    "mart.v_superset_featured_viewership",
    "mart.v_superset_featured_correlation",
)

# Varasem versioon lõikas vaates globaalselt 500 rida; kontroll tuvastab taassissetuleku.
SUPERSET_TOP_VIEW_ROW_LIMIT = 500
# Hoiatus, kui perioodi 20. koha globaalne järk läheneb limiidile (TOP graafik võib katki minna).
SUPERSET_TOP_WARN_GLOBAL_RANK = 450
STRUCTURE_VIEWED_META_WARN_PCT = 80.0
VIEWERS_MATCH_WARN_PCT = 70.0
VIEWERS_MATCH_FAIL_PCT = 50.0
CORR_PAIR_COUNT_WARN = 50
CORR_PAIR_COUNT_FAIL = 20
STRUCTURE_PCT_SUM_WARN_LO = 99.5
STRUCTURE_PCT_SUM_WARN_HI = 100.5
STRUCTURE_PCT_SUM_FAIL_LO = 99.0
STRUCTURE_PCT_SUM_FAIL_HI = 101.0


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

    featured_archives = (
        list(FEATURED_DIR.glob("jupiter_f_*.csv")) if FEATURED_DIR.is_dir() else []
    )
    if featured_archives:
        results.append(
            CheckResult(
                "Failid featured arhiiv",
                Status.OK,
                f"{len(featured_archives)} faili kaustas data/featured/",
            )
        )
    else:
        results.append(
            CheckResult(
                "Failid featured arhiiv",
                Status.WARN,
                "puuduvad jupiter_f_*.csv — nädalavaates võib esiletõstmine puududa",
            )
        )

    catalog_archives = (
        list(CATALOG_DAILY_DIR.glob("jupiter_c_*.csv"))
        if CATALOG_DAILY_DIR.is_dir()
        else []
    )
    if catalog_archives:
        results.append(
            CheckResult(
                "Failid catalog_daily arhiiv",
                Status.OK,
                f"{len(catalog_archives)} faili kaustas data/catalog_daily/",
            )
        )
    else:
        results.append(
            CheckResult(
                "Failid catalog_daily arhiiv",
                Status.WARN,
                "puuduvad jupiter_c_*.csv — nädalavaates võib kataloog puududa",
            )
        )
    return results


def check_staging(cur) -> list[CheckResult]:
    results: list[CheckResult] = []
    thresholds = (
        ("staging.catalog", "SELECT COUNT(*) FROM staging.catalog", 1),
        ("staging.catalog_daily", "SELECT COUNT(*) FROM staging.catalog_daily", 1),
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

    weekly_without_featured = _query_count(
        cur,
        """
        SELECT COUNT(*)
        FROM (
            SELECT DISTINCT period_start, period_end
            FROM staging.viewers_raw
            WHERE grain = 'weekly'
        ) AS w
        WHERE NOT EXISTS (
            SELECT 1
            FROM staging.featured_daily AS f
            WHERE f.feature_date BETWEEN w.period_start AND w.period_end
        )
        """,
    )
    if weekly_without_featured:
        results.append(
            CheckResult(
                "Nädalad ilma featured andmeteta",
                Status.WARN,
                f"{weekly_without_featured} weekly perioodi viewers fail on olemas, "
                "aga featured arhiiv puudub — esiletõstmise graafikud jäävad tühjaks",
            )
        )
    elif _query_count(cur, "SELECT COUNT(*) FROM staging.viewers_raw WHERE grain = 'weekly'") > 0:
        results.append(
            CheckResult(
                "Nädalad ilma featured andmeteta",
                Status.OK,
                "weekly perioodidel on featured katvus",
            )
        )
    return results


def check_title_match_viewers_pct(cur) -> list[CheckResult]:
    """Viimase päeva featured → viewers kattuvus (mart.title_match_daily)."""
    cur.execute("SELECT to_regclass('mart.title_match_daily')")
    if cur.fetchone()[0] is None:
        return []

    row = _query_one(
        cur,
        """
        SELECT activity_date, viewers_match_pct, featured_count
        FROM mart.title_match_daily
        WHERE viewers_match_count > 0
        ORDER BY activity_date DESC
        LIMIT 1
        """,
    )
    if not row:
        row = _query_one(
            cur,
            """
            SELECT activity_date, viewers_match_pct, featured_count
            FROM mart.title_match_daily
            ORDER BY activity_date DESC
            LIMIT 1
            """,
        )
    if not row:
        return [
            CheckResult(
                "Ühendus: viewers_match_pct (viimane päev)",
                Status.WARN,
                "title_match_daily on tühi — käivita transform",
            )
        ]

    activity_date, viewers_match_pct, featured_count = row
    if viewers_match_pct is None:
        return [
            CheckResult(
                "Ühendus: viewers_match_pct (viimane päev)",
                Status.WARN,
                f"{activity_date}: featured_count={featured_count}, viewers_match_pct puudub",
            )
        ]

    pct = float(viewers_match_pct)
    if pct < VIEWERS_MATCH_FAIL_PCT:
        return [
            CheckResult(
                "Ühendus: viewers_match_pct (viimane päev)",
                Status.FAIL,
                f"{activity_date}: {pct:.1f}% (< {VIEWERS_MATCH_FAIL_PCT:.0f}%) — "
                f"{featured_count} esiletõstetud pealkirja",
            )
        ]
    if pct < VIEWERS_MATCH_WARN_PCT:
        return [
            CheckResult(
                "Ühendus: viewers_match_pct (viimane päev)",
                Status.WARN,
                f"{activity_date}: {pct:.1f}% (< {VIEWERS_MATCH_WARN_PCT:.0f}%) — "
                f"paljud read jäävad ilma views_total",
            )
        ]
    return [
        CheckResult(
            "Ühendus: viewers_match_pct (viimane päev)",
            Status.OK,
            f"{activity_date}: {pct:.1f}% ({featured_count} pealkirja)",
        )
    ]


def check_correlation_pair_count(cur) -> list[CheckResult]:
    """Viimase daily perioodi pair_count (korrelatsioonigraafik)."""
    cur.execute("SELECT to_regclass('mart.v_superset_featured_correlation')")
    if cur.fetchone()[0] is None:
        return []

    row = _query_one(
        cur,
        """
        SELECT period_start, pair_count
        FROM mart.v_superset_featured_correlation
        WHERE grain = 'daily'
          AND pair_count > 0
        ORDER BY period_start DESC
        LIMIT 1
        """,
    )
    if not row:
        row = _query_one(
            cur,
            """
            SELECT period_start, pair_count
            FROM mart.v_superset_featured_correlation
            WHERE grain = 'daily'
            ORDER BY period_start DESC
            LIMIT 1
            """,
        )
    if not row:
        return [
            CheckResult(
                "Korrelatsioon: pair_count (viimane päev)",
                Status.WARN,
                "daily korrelatsiooni ridu pole",
            )
        ]

    period_start, pair_count = row
    count = int(pair_count or 0)
    if count < CORR_PAIR_COUNT_FAIL:
        return [
            CheckResult(
                "Korrelatsioon: pair_count (viimane päev)",
                Status.FAIL,
                f"{period_start}: pair_count={count} (< {CORR_PAIR_COUNT_FAIL}) — "
                "korrelatsioon ei ole usaldusväärne",
            )
        ]
    if count < CORR_PAIR_COUNT_WARN:
        return [
            CheckResult(
                "Korrelatsioon: pair_count (viimane päev)",
                Status.WARN,
                f"{period_start}: pair_count={count} (< {CORR_PAIR_COUNT_WARN})",
            )
        ]
    return [
        CheckResult(
            "Korrelatsioon: pair_count (viimane päev)",
            Status.OK,
            f"{period_start}: pair_count={count}",
        )
    ]


def check_structure_pct_sums(cur) -> list[CheckResult]:
    """Struktuuri virn: SUM(pct) ≈ 100% iga (periood, struktuur, dimensioon) kohta."""
    cur.execute("SELECT to_regclass('mart.content_structure_period_pct')")
    if cur.fetchone()[0] is None:
        return []

    fail_count = _query_count(
        cur,
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT 1
            FROM mart.content_structure_period_pct
            GROUP BY grain, period_start, period_end, structure_type, dimension
            HAVING ROUND(SUM(pct)::numeric, 2) < {STRUCTURE_PCT_SUM_FAIL_LO}
                OR ROUND(SUM(pct)::numeric, 2) > {STRUCTURE_PCT_SUM_FAIL_HI}
        ) AS bad
        """,
    )
    warn_count = _query_count(
        cur,
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT 1
            FROM mart.content_structure_period_pct
            GROUP BY grain, period_start, period_end, structure_type, dimension
            HAVING ROUND(SUM(pct)::numeric, 2) < {STRUCTURE_PCT_SUM_WARN_LO}
                OR ROUND(SUM(pct)::numeric, 2) > {STRUCTURE_PCT_SUM_WARN_HI}
        ) AS bad
        """,
    )
    if fail_count == 0 and warn_count == 0:
        return [
            CheckResult(
                "Struktuur: SUM(pct) ≈ 100%",
                Status.OK,
                "kõik virnad jäävad vahemikku 99.5–100.5",
            )
        ]

    sample = _query_one(
        cur,
        """
        SELECT
            grain,
            period_start,
            period_end,
            structure_type,
            dimension,
            ROUND(SUM(pct)::numeric, 2) AS pct_sum
        FROM mart.content_structure_period_pct
        GROUP BY grain, period_start, period_end, structure_type, dimension
        HAVING ROUND(SUM(pct)::numeric, 2) < %s
            OR ROUND(SUM(pct)::numeric, 2) > %s
        ORDER BY ABS(ROUND(SUM(pct)::numeric, 2) - 100) DESC
        LIMIT 1
        """,
        (STRUCTURE_PCT_SUM_WARN_LO, STRUCTURE_PCT_SUM_WARN_HI),
    )
    sample_msg = ""
    if sample:
        sample_msg = (
            f" Näide: {sample[0]} {sample[1]}..{sample[2]} {sample[3]}/{sample[4]} "
            f"sum={sample[5]}"
        )

    if fail_count:
        return [
            CheckResult(
                "Struktuur: SUM(pct) ≈ 100%",
                Status.FAIL,
                f"{fail_count} virna väljaspool {STRUCTURE_PCT_SUM_FAIL_LO}–"
                f"{STRUCTURE_PCT_SUM_FAIL_HI}%; "
                f"{warn_count} väljaspool {STRUCTURE_PCT_SUM_WARN_LO}–"
                f"{STRUCTURE_PCT_SUM_WARN_HI}.{sample_msg}",
            )
        ]
    return [
        CheckResult(
            "Struktuur: SUM(pct) ≈ 100%",
            Status.WARN,
            f"{warn_count} virna väljaspool {STRUCTURE_PCT_SUM_WARN_LO}–"
            f"{STRUCTURE_PCT_SUM_WARN_HI}.{sample_msg}",
        )
    ]


def check_structure_viewers_type_labels(cur) -> list[CheckResult]:
    """FAIL, kui viewers CSV toorkoodid S/Y jõuavad struktuuri diagrammi (ei tohiks pärast meta-only reeglit)."""
    raw = _query_count(
        cur,
        """
        SELECT COUNT(*)
        FROM mart.content_structure_period_pct
        WHERE dimension = 'content_type'
          AND category_code IN ('S', 'Y')
        """,
    )
    if raw:
        return [
            CheckResult(
                "Struktuur: viewers type S/Y",
                Status.FAIL,
                f"{raw} rida kasutab toorkoodi S või Y — "
                "käivita transform uuesti (viewers type ei tohiks struktuuris kasutada)",
            )
        ]
    short_segments = _query_count(
        cur,
        """
        SELECT COUNT(*)
        FROM mart.v_superset_content_type_pct
        WHERE segment IN ('S', 'Y')
        """,
    )
    if short_segments:
        return [
            CheckResult(
                "Struktuur: viewers type S/Y",
                Status.FAIL,
                f"Superseti vaates on segmente S/Y ({short_segments} rida)",
            )
        ]
    return [
        CheckResult(
            "Struktuur: viewers type S/Y",
            Status.OK,
            "struktuuris ei ole viewers CSV S/Y toorkoode",
        )
    ]


def check_structure_metadata_coverage(cur) -> list[CheckResult]:
    """Hoiata, kui vaadatavuse pealkirjad on meta CSV-ga halvasti kaetud."""
    cur.execute("SELECT to_regclass('staging.viewers_raw')")
    if cur.fetchone()[0] is None:
        return []

    cur.execute(
        """
        WITH meta AS (
            SELECT mart.normalize_title(title) AS title_normalized
            FROM staging.content_metadata
            WHERE mart.normalize_title(title) IS NOT NULL
        ),
        viewers AS (
            SELECT DISTINCT mart.normalize_title(title) AS title_normalized
            FROM staging.viewers_raw
            WHERE mart.normalize_title(title) IS NOT NULL
        ),
        featured AS (
            SELECT DISTINCT mart.normalize_title(title) AS title_normalized
            FROM staging.featured_daily
            WHERE mart.normalize_title(title) IS NOT NULL
        )
        SELECT
            (SELECT COUNT(*) FROM viewers) AS viewers_titles,
            (SELECT COUNT(*) FROM viewers v INNER JOIN meta m USING (title_normalized))
                AS viewers_with_meta,
            (SELECT COUNT(*) FROM featured) AS featured_titles,
            (SELECT COUNT(*) FROM featured f INNER JOIN meta m USING (title_normalized))
                AS featured_with_meta
        """
    )
    row = cur.fetchone()
    if not row or row[0] == 0:
        return []

    viewers_total, viewers_with_meta, featured_total, featured_with_meta = row
    viewers_pct = 100.0 * viewers_with_meta / viewers_total
    featured_pct = (
        100.0 * featured_with_meta / featured_total if featured_total else 100.0
    )

    unknown_viewed = _query_count(
        cur,
        """
        SELECT COUNT(*)
        FROM mart.content_structure_period_pct
        WHERE structure_type = 'viewed'
          AND dimension = 'origin_country'
          AND category_code = 'UNKNOWN'
        """,
    )

    if viewers_pct < STRUCTURE_VIEWED_META_WARN_PCT:
        return [
            CheckResult(
                "Struktuur: meta katvus (viewers)",
                Status.WARN,
                f"{viewers_with_meta}/{viewers_total} pealkirja ({viewers_pct:.1f}%) on meta CSV-s — "
                f"vaadatud struktuuris on UNKNOWN/Määramata segment "
                f"({unknown_viewed} rida perioodipõhises tabelis)",
            )
        ]

    return [
        CheckResult(
            "Struktuur: meta katvus (viewers)",
            Status.OK,
            f"{viewers_with_meta}/{viewers_total} pealkirja ({viewers_pct:.1f}%) meta CSV-s; "
            f"featured {featured_with_meta}/{featured_total} ({featured_pct:.1f}%)",
        )
    ]


def check_superset_featured_top_pool(cur) -> list[CheckResult]:
    """Hoiata, kui v_superset_featured_top globaalne LIMIT võib TOP 20 moonutada."""
    cur.execute("SELECT to_regclass('mart.v_featured_viewership_period')")
    if cur.fetchone()[0] is None:
        return []

    period_rows = _query_count(cur, "SELECT COUNT(*) FROM mart.v_featured_viewership_period")
    if period_rows == 0:
        return []

    cur.execute(
        """
        WITH ranked AS (
            SELECT
                grain,
                period_start,
                period_end,
                title,
                ROW_NUMBER() OVER (
                    ORDER BY prominence_score_total DESC NULLS LAST
                ) AS global_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY grain, period_start, period_end
                    ORDER BY prominence_score_total DESC NULLS LAST
                ) AS period_rank
            FROM mart.v_featured_viewership_period
        ),
        day20 AS (
            SELECT grain, period_start, period_end, title, global_rank
            FROM ranked
            WHERE period_rank = 20
        ),
        risky AS (
            SELECT *
            FROM day20
            WHERE global_rank > %s
        ),
        broken AS (
            SELECT *
            FROM day20
            WHERE global_rank > %s
        )
        SELECT
            (SELECT COUNT(*) FROM day20) AS periods_with_top20,
            (SELECT COALESCE(MAX(global_rank), 0) FROM day20) AS max_global_rank_of_period_20,
            (SELECT COUNT(*) FROM risky) AS warn_period_count,
            (SELECT COUNT(*) FROM broken) AS fail_period_count,
            (
                SELECT string_agg(
                    grain || ' ' || period_start::text || ' #' || global_rank::text,
                    '; '
                    ORDER BY global_rank DESC
                )
                FROM (SELECT * FROM risky ORDER BY global_rank DESC LIMIT 5) AS r
            ) AS warn_sample
        """,
        (SUPERSET_TOP_WARN_GLOBAL_RANK, SUPERSET_TOP_VIEW_ROW_LIMIT),
    )
    summary = cur.fetchone()
    if not summary or summary[0] == 0:
        return [
            CheckResult(
                "TOP vaate globaalne limiit",
                Status.WARN,
                "ühelgi perioodil pole 20 esiletõstetud rida — TOP graafik võib olla tühi",
            )
        ]

    periods_with_top20, max_rank, warn_count, fail_count, warn_sample = summary

    mismatch_count = 0
    cur.execute("SELECT to_regclass('mart.v_superset_featured_top')")
    if cur.fetchone()[0] is not None:
        mismatch_count = _query_count(
            cur,
            """
            WITH true_top20 AS (
                SELECT
                    grain,
                    period_start,
                    period_end,
                    title,
                    ROW_NUMBER() OVER (
                        PARTITION BY grain, period_start, period_end
                        ORDER BY prominence_score_total DESC NULLS LAST
                    ) AS period_rank
                FROM mart.v_featured_viewership_period
            ),
            via_view AS (
                SELECT
                    grain,
                    period_start,
                    period_end,
                    title,
                    ROW_NUMBER() OVER (
                        PARTITION BY grain, period_start, period_end
                        ORDER BY prominence_score_total DESC NULLS LAST
                    ) AS period_rank
                FROM mart.v_superset_featured_top
            )
            SELECT COUNT(*)
            FROM true_top20 AS t
            LEFT JOIN via_view AS v
                ON t.grain = v.grain
               AND t.period_start = v.period_start
               AND t.period_end = v.period_end
               AND t.period_rank = v.period_rank
            WHERE t.period_rank <= 20
              AND (v.title IS NULL OR t.title <> v.title)
            """,
        )

    if fail_count > 0 or mismatch_count > 0:
        parts = []
        if fail_count:
            parts.append(
                f"{fail_count} perioodi 20. koht on globaalses TOP {SUPERSET_TOP_VIEW_ROW_LIMIT}st väljas"
            )
        if mismatch_count:
            parts.append(
                f"{mismatch_count} rea TOP 20 ei klapi v_superset_featured_top vaatega"
            )
        return [
            CheckResult(
                "TOP vaate globaalne limiit",
                Status.FAIL,
                "; ".join(parts)
                + " — eemalda vaatest globaalne LIMIT (Superset row_limit piisab)",
            )
        ]

    if warn_count > 0:
        sample = f" ({warn_sample})" if warn_sample else ""
        return [
            CheckResult(
                "TOP vaate globaalne limiit",
                Status.WARN,
                f"{warn_count}/{periods_with_top20} perioodi 20. koht on globaalses "
                f"järjekorras > {SUPERSET_TOP_WARN_GLOBAL_RANK} "
                f"(max {max_rank}, limiit {SUPERSET_TOP_VIEW_ROW_LIMIT}){sample}",
            )
        ]

    return [
        CheckResult(
            "TOP vaate globaalne limiit",
            Status.OK,
            f"{periods_with_top20} perioodi; 20. koha max globaalne järk {max_rank} "
            f"(< {SUPERSET_TOP_WARN_GLOBAL_RANK})",
        )
    ]


def check_mart(cur) -> list[CheckResult]:
    results: list[CheckResult] = []
    mart_checks = (
        ("mart.dim_content", "SELECT COUNT(*) FROM mart.dim_content"),
        (
            "mart.dim_content (meta)",
            "SELECT COUNT(*) FROM mart.dim_content WHERE in_metadata",
        ),
        ("mart.content_structure_pct", "SELECT COUNT(*) FROM mart.content_structure_pct"),
        (
            "mart.content_structure_period_pct",
            "SELECT COUNT(*) FROM mart.content_structure_period_pct",
        ),
        (
            "mart.content_structure_period_pct (daily)",
            "SELECT COUNT(*) FROM mart.content_structure_period_pct WHERE grain = 'daily'",
        ),
        ("mart.fact_content_daily", "SELECT COUNT(*) FROM mart.fact_content_daily"),
        ("mart.v_featured_viewership", "SELECT COUNT(*) FROM mart.v_featured_viewership"),
        (
            "mart.v_featured_viewership_period (daily)",
            "SELECT COUNT(*) FROM mart.v_featured_viewership_period WHERE grain = 'daily'",
        ),
        ("mart.v_superset_origin_pct", "SELECT COUNT(*) FROM mart.v_superset_origin_pct"),
        (
            "mart.v_superset_content_type_pct",
            "SELECT COUNT(*) FROM mart.v_superset_content_type_pct",
        ),
        ("mart.v_superset_featured_top", "SELECT COUNT(*) FROM mart.v_superset_featured_top"),
        (
            "mart.v_superset_featured_viewership (daily)",
            "SELECT COUNT(*) FROM mart.v_superset_featured_viewership WHERE grain = 'daily'",
        ),
        (
            "mart.v_superset_featured_correlation (daily)",
            "SELECT COUNT(*) FROM mart.v_superset_featured_correlation WHERE grain = 'daily'",
        ),
    )
    warn_if_empty = {
        "mart.v_featured_viewership",
        "mart.v_featured_viewership_period (daily)",
        "mart.v_superset_featured_top",
        "mart.v_superset_featured_viewership (daily)",
        "mart.v_superset_featured_correlation (daily)",
    }
    for name, sql in mart_checks:
        count = _query_count(cur, sql)
        if count > 0:
            results.append(CheckResult(name, Status.OK, f"{count} rida"))
        elif name in warn_if_empty:
            results.append(
                CheckResult(
                    name,
                    Status.WARN,
                    "0 rida — kontrolli featured/viewers päevade kattumist või vali daily filter",
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
        FROM mart.content_structure_period_pct
        WHERE structure_type = 'viewed' AND grain = 'daily'
        """,
    )
    if viewed_rows == 0:
        results.append(
            CheckResult(
                "Struktuur: vaadatud rida (daily)",
                Status.WARN,
                "viewed struktuuri read puuduvad — viewers CSV võib puududa featured päeval",
            )
        )
    else:
        results.append(
            CheckResult(
                "Struktuur: vaadatud rida (daily)",
                Status.OK,
                f"{viewed_rows} segmenti",
            )
        )

    weekly_only_viewed = _query_count(
        cur,
        """
        SELECT COUNT(*)
        FROM (
            SELECT period_start
            FROM mart.content_structure_period_pct
            WHERE grain = 'weekly'
            GROUP BY period_start, period_end
            HAVING COUNT(DISTINCT structure_type) = 1
               AND MAX(structure_type) = 'viewed'
        ) AS w
        """,
    )
    if weekly_only_viewed:
        results.append(
            CheckResult(
                "Struktuur: weekly ainult viewed",
                Status.WARN,
                f"{weekly_only_viewed} nädalat ilma kataloogi/esitatud ridadeta — "
                "lisa featured ja catalog_daily arhiiv selle nädala päevadele",
            )
        )
    results.extend(check_structure_metadata_coverage(cur))
    results.extend(check_structure_viewers_type_labels(cur))
    results.extend(check_structure_pct_sums(cur))
    results.extend(check_title_match_viewers_pct(cur))
    results.extend(check_correlation_pair_count(cur))
    results.extend(check_superset_featured_top_pool(cur))
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
