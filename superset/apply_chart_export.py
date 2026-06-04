"""Rakenda graafikute ja dashboardi seaded YAML-ist Superseti andmebaasis (pärast importi).

Superseti ``import-dashboards`` ei kirjuta üle olemasoleva dashboardi paigutust ega
native filtreid (need jäävad Superseti metadata DB-sse). See skript:
- uuendab chartide (slice) params / datasource uuid järgi;
- asendab dashboardi ``position_json`` ja ``json_metadata`` YAML-ist;
- mapib ``chartId`` väärtused kohalike slice ID-dega.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from superset.app import create_app

CHARTS_DIR = Path(__file__).resolve().parent / "dashboard_export" / "charts"
DASHBOARD_YAML = (
    Path(__file__).resolve().parent / "dashboard_export" / "dashboards" / "Jupiteri_analuus.yaml"
)
DASHBOARD_TITLE = "Jupiteri analüüs"

# Superset 6: legacy "bar" eemaldatud; frontend ootab echarts_timeseries_bar.
VIZ_TYPE_ALIASES = {
    "bar": "echarts_timeseries_bar",
}


def normalize_viz_type(viz_type: str | None) -> str | None:
    if not viz_type:
        return viz_type
    return VIZ_TYPE_ALIASES.get(viz_type, viz_type)


def load_chart_specs() -> list[dict]:
    specs = []
    for path in sorted(CHARTS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not data.get("uuid"):
            print(f"  {path.name}: uuid puudub, jäetakse vahele", file=sys.stderr)
            continue
        specs.append(data)
    return specs


def resolve_datasource_id(dataset_uuid: str, uuid_to_id: dict[str, int]) -> int | None:
    key = str(dataset_uuid).strip().lower()
    return uuid_to_id.get(key)


def build_params(data: dict, dataset_id: int) -> dict:
    params = dict(data.get("params") or {})
    params["datasource"] = f"{dataset_id}__table"
    viz_type = normalize_viz_type(data.get("viz_type") or params.get("viz_type"))
    if viz_type:
        params["viz_type"] = viz_type
    return params


def sanitize_dashboard_metadata(metadata: dict) -> dict:
    """Ära impordi teammate UI filtreid — scope chartId-d on valesti (Apply jääb halliks).

    Filtreid loo käsitsi vastavalt docs/superset.md.
    """
    meta = dict(metadata)
    meta["native_filter_configuration"] = []
    return meta


def load_dashboard_spec() -> dict | None:
    if not DASHBOARD_YAML.is_file():
        print(f"  dashboard YAML puudub: {DASHBOARD_YAML}", file=sys.stderr)
        return None
    return yaml.safe_load(DASHBOARD_YAML.read_text(encoding="utf-8"))


def remap_position_chart_ids(
    position: dict,
    uuid_to_slice_id: dict[str, int],
    slice_names_by_uuid: dict[str, str],
) -> int:
    """Asenda YAML-i teammate chartId kohalike slice.id väärtustega."""
    remapped = 0
    for node in position.values():
        if not isinstance(node, dict) or node.get("type") != "CHART":
            continue
        meta = node.get("meta") or {}
        chart_uuid = str(meta.get("uuid") or "").lower()
        slice_id = uuid_to_slice_id.get(chart_uuid)
        if slice_id is not None:
            meta["chartId"] = slice_id
            remapped += 1
        new_name = slice_names_by_uuid.get(chart_uuid)
        if new_name:
            meta["sliceName"] = new_name
    return remapped


def sync_dashboard_from_yaml(
    dashboard_spec: dict,
    uuid_to_slice_id: dict[str, int],
    slice_names_by_uuid: dict[str, str],
) -> bool:
    from superset import db
    from superset.models.dashboard import Dashboard

    dash_uuid = dashboard_spec.get("uuid")
    dashboard = None
    if dash_uuid:
        dashboard = (
            db.session.query(Dashboard)
            .filter(Dashboard.uuid == dash_uuid)
            .one_or_none()
        )
    if dashboard is None:
        dashboard = (
            db.session.query(Dashboard)
            .filter(Dashboard.dashboard_title == DASHBOARD_TITLE)
            .one_or_none()
        )
    if dashboard is None:
        print(f"  dashboard {DASHBOARD_TITLE!r} puudub", file=sys.stderr)
        return False

    position = dashboard_spec.get("position") or {}
    remapped = remap_position_chart_ids(
        position, uuid_to_slice_id, slice_names_by_uuid
    )
    dashboard.position_json = json.dumps(position)

    metadata = dashboard_spec.get("metadata")
    if metadata is not None:
        metadata = sanitize_dashboard_metadata(metadata)
        dashboard.json_metadata = json.dumps(metadata)

    title = dashboard_spec.get("dashboard_title")
    if title:
        dashboard.dashboard_title = title

    print(
        f"  dashboard layout: position_json asendatud, chartId mapitud {remapped} graafikule"
    )
    return True


def main() -> int:
    if not CHARTS_DIR.is_dir():
        print(f"Chart kaust puudub: {CHARTS_DIR}", file=sys.stderr)
        return 1

    specs = load_chart_specs()
    if not specs:
        print("Graafikute YAML-e ei leitud.", file=sys.stderr)
        return 1

    app = create_app()
    with app.app_context():
        from superset import db
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.slice import Slice

        uuid_to_dataset_id = {
            str(ds.uuid).lower(): ds.id for ds in db.session.query(SqlaTable).all()
        }

        applied = 0
        missing = 0
        slice_names_by_uuid: dict[str, str] = {}

        for data in specs:
            chart_uuid = str(data["uuid"]).lower()
            slice_names_by_uuid[chart_uuid] = data["slice_name"]

            dataset_uuid = data.get("dataset_uuid")
            if not dataset_uuid:
                print(f"  {data['slice_name']}: dataset_uuid puudub", file=sys.stderr)
                continue

            dataset_id = resolve_datasource_id(dataset_uuid, uuid_to_dataset_id)
            if dataset_id is None:
                print(
                    f"  {data['slice_name']}: andmestik {dataset_uuid} puudub",
                    file=sys.stderr,
                )
                continue

            slc = (
                db.session.query(Slice)
                .filter(Slice.uuid == data["uuid"])
                .one_or_none()
            )
            if slc is None:
                print(f"  {data['slice_name']}: slice uuid={data['uuid']} puudub", file=sys.stderr)
                missing += 1
                continue

            params = build_params(data, dataset_id)
            slc.slice_name = data["slice_name"]
            slc.viz_type = normalize_viz_type(data.get("viz_type")) or slc.viz_type
            slc.description = data.get("description") or ""
            slc.params = json.dumps(params)
            slc.cache_timeout = data.get("cache_timeout")
            slc.datasource_id = dataset_id
            slc.datasource_type = "table"
            slc.query_context = None

            applied += 1
            print(f"  {data['slice_name']}: datasource={dataset_id}__table")

        uuid_to_slice_id: dict[str, int] = {}
        for data in specs:
            slc = (
                db.session.query(Slice)
                .filter(Slice.uuid == data["uuid"])
                .one_or_none()
            )
            if slc is not None:
                uuid_to_slice_id[str(data["uuid"]).lower()] = slc.id

        dashboard_spec = load_dashboard_spec()
        if dashboard_spec:
            sync_dashboard_from_yaml(
                dashboard_spec, uuid_to_slice_id, slice_names_by_uuid
            )

        db.session.commit()

        print(f"Kokku: {applied} graafikut uuendatud, {missing} puudub Supersetis")
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
