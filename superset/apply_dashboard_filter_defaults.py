"""Sünkroniseeri dashboardi native filtrid YAML-ist; sea vaikeväärtused andmebaasist."""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path

import psycopg2
import yaml
from superset.app import create_app

DASHBOARD_TITLE = "Jupiteri analüüs"
FILTER_GRAIN = "NATIVE_FILTER_GRAIN"
FILTER_PERIOD = "NATIVE_FILTER_PERIOD"
DASHBOARD_YAML = (
    Path(__file__).resolve().parent / "dashboard_export" / "dashboards" / "Jupiteri_analuus.yaml"
)


def pg_connect():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "db"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        user=os.environ.get("POSTGRES_USER", "praktikum"),
        password=os.environ.get("POSTGRES_PASSWORD", "praktikum"),
        dbname=os.environ.get("POSTGRES_DB", "praktikum"),
    )


def latest_period_key(grain: str = "daily") -> str | None:
    with pg_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT period_start_key
            FROM mart.v_superset_origin_pct
            WHERE grain = %s
            ORDER BY period_start_key DESC
            LIMIT 1
            """,
            (grain,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def load_filter_config_from_yaml() -> list[dict]:
    data = yaml.safe_load(DASHBOARD_YAML.read_text(encoding="utf-8"))
    return deepcopy(data.get("metadata", {}).get("native_filter_configuration") or [])


def apply_default_masks(filters: list[dict], grain: str, period_key: str) -> None:
    for flt in filters:
        if flt.get("id") == FILTER_GRAIN:
            flt["defaultDataMask"] = {
                "extraFormData": {"filters": [{"col": "grain", "op": "IN", "val": [grain]}]},
                "filterState": {"label": grain, "value": [grain]},
            }
        elif flt.get("id") == FILTER_PERIOD:
            flt["defaultDataMask"] = {
                "extraFormData": {
                    "filters": [{"col": "period_start_key", "op": "IN", "val": [period_key]}],
                },
                "filterState": {"label": period_key, "value": [period_key]},
            }


def resolve_dataset_ids(filters: list[dict]) -> int:
    from superset import db
    from superset.connectors.sqla.models import SqlaTable

    uuid_to_id = {str(ds.uuid): ds.id for ds in db.session.query(SqlaTable).all()}
    resolved = 0
    for flt in filters:
        for target in flt.get("targets") or []:
            uid = target.get("datasetUuid")
            if not uid:
                continue
            dataset_id = uuid_to_id.get(str(uid))
            if dataset_id is None:
                print(f"  hoiatus: datasetUuid {uid} ei leitud", file=sys.stderr)
                continue
            target["datasetId"] = dataset_id
            resolved += 1
    return resolved


def main() -> int:
    if not DASHBOARD_YAML.is_file():
        print(f"Dashboard YAML puudub: {DASHBOARD_YAML}", file=sys.stderr)
        return 1

    grain = "daily"
    period_key = latest_period_key(grain)
    if not period_key:
        print("period_start_key puudub.", file=sys.stderr)
        return 1

    filters = load_filter_config_from_yaml()
    apply_default_masks(filters, grain, period_key)

    app = create_app()
    with app.app_context():
        from superset import db
        from superset.models.dashboard import Dashboard

        n_targets = resolve_dataset_ids(filters)

        dashboard = (
            db.session.query(Dashboard)
            .filter(Dashboard.dashboard_title == DASHBOARD_TITLE)
            .one_or_none()
        )
        if dashboard is None:
            print(f"Dashboard {DASHBOARD_TITLE!r} puudub.", file=sys.stderr)
            return 1

        meta = json.loads(dashboard.json_metadata or "{}")
        meta["native_filter_configuration"] = filters
        dashboard.json_metadata = json.dumps(meta)
        db.session.commit()
        excluded = filters[0].get("scope", {}).get("excluded", []) if filters else []
        print(
            f"Dashboard: grain={grain}, period={period_key}, "
            f"filtreid={len(filters)}, sihtmärke={n_targets}, excluded={excluded}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
