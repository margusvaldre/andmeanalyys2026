"""Sünkroniseeri andmestikud YAML-ist (pärast dashboard importi).

- YAML-is `sql` olemas: virtuaalne päring (vanem käitumine).
- YAML-is `sql` puudub: füüsiline vaade mart.skeemas, `fetch_metadata()` veergudega.
- Eemaldab metaandmetest veerud, mida YAML-is enam pole (nt grain_period_key).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml
from superset.app import create_app

DATASET_DIR = Path(__file__).resolve().parent / "dashboard_export" / "datasets" / "Jupiter_PostgreSQL"
PLACEHOLDERS = {
    "__POSTGRES_USER__": os.environ.get("POSTGRES_USER", "praktikum"),
    "__POSTGRES_PASSWORD__": os.environ.get("POSTGRES_PASSWORD", "praktikum"),
    "__POSTGRES_DB__": os.environ.get("POSTGRES_DB", "praktikum"),
    "__POSTGRES_HOST__": os.environ.get("POSTGRES_HOST", "db"),
    "__POSTGRES_PORT__": os.environ.get("POSTGRES_PORT", "5432"),
}


def render(text: str) -> str:
    for placeholder, value in PLACEHOLDERS.items():
        text = text.replace(placeholder, value)
    return text


def sync_columns_from_yaml(dataset, column_defs: list[dict[str, Any]]) -> int:
    from superset.connectors.sqla.models import TableColumn

    if not column_defs:
        return 0

    existing = {col.column_name: col for col in dataset.columns}
    added = 0
    for spec in column_defs:
        name = spec.get("column_name")
        if not name or name in existing:
            continue
        dataset.columns.append(
            TableColumn(
                column_name=name,
                verbose_name=spec.get("verbose_name") or name,
                is_dttm=bool(spec.get("is_dttm", False)),
                is_active=bool(spec.get("is_active", True)),
                type=spec.get("type") or "STRING",
                groupby=bool(spec.get("groupby", True)),
                filterable=bool(spec.get("filterable", True)),
            )
        )
        added += 1
    return added


def prune_columns_not_in_yaml(dataset, column_defs: list[dict[str, Any]]) -> int:
    allowed = {spec.get("column_name") for spec in column_defs if spec.get("column_name")}
    if not allowed:
        return 0
    removed = 0
    for col in list(dataset.columns):
        if col.column_name not in allowed:
            dataset.columns.remove(col)
            removed += 1
    return removed


def main() -> int:
    app = create_app()
    with app.app_context():
        from superset import db
        from superset.connectors.sqla.models import SqlaTable

        if not DATASET_DIR.is_dir():
            print(f"Dataset kaust puudub: {DATASET_DIR}", file=sys.stderr)
            return 1

        virtual_count = 0
        physical_count = 0
        for path in sorted(DATASET_DIR.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            schema = data.get("schema", "mart")
            table_name = data["table_name"]
            column_defs = data.get("columns") or []
            sql = data.get("sql")
            has_sql = bool(sql and str(sql).strip())

            dataset = (
                db.session.query(SqlaTable)
                .filter_by(schema=schema, table_name=table_name)
                .one_or_none()
            )
            if dataset is None:
                print(f"  {table_name}: andmestik puudub, jäetakse vahele", file=sys.stderr)
                continue

            if has_sql:
                dataset.sql = render(str(sql))
                added = sync_columns_from_yaml(dataset, column_defs)
                removed = prune_columns_not_in_yaml(dataset, column_defs)
                db.session.commit()
                virtual_count += 1
                print(f"  {table_name}: virtual SQL (+{added}/-{removed} veergu)")
            else:
                dataset.sql = None
                try:
                    dataset.fetch_metadata()
                except Exception as exc:  # noqa: BLE001
                    db.session.rollback()
                    print(f"  {table_name}: fetch_metadata ebaõnnestus ({exc!r})", file=sys.stderr)
                    continue
                added = sync_columns_from_yaml(dataset, column_defs)
                removed = prune_columns_not_in_yaml(dataset, column_defs)
                db.session.commit()
                physical_count += 1
                print(
                    f"  {table_name}: füüsiline vaade "
                    f"({len(dataset.columns)} veergu, +{added}/-{removed})"
                )

        print(f"Kokku: {virtual_count} virtual, {physical_count} füüsiline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
