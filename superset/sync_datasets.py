"""Sünkroniseeri mart-andmestike veerud PostgreSQL-ist Superseti metaandmebaasi."""

from __future__ import annotations

import os
import sys

from superset.app import create_app


def main() -> int:
    app = create_app()
    with app.app_context():
        from superset import db
        from superset.connectors.sqla.models import SqlaTable

        schema = os.environ.get("SUPERSET_MART_SCHEMA", "mart")
        datasets = (
            db.session.query(SqlaTable)
            .filter(SqlaTable.schema == schema)
            .order_by(SqlaTable.table_name)
            .all()
        )
        if not datasets:
            print(f"Andmestikke skeemis {schema!r} ei leitud.", file=sys.stderr)
            return 1

        for dataset in datasets:
            before = len(dataset.columns)
            try:
                dataset.fetch_metadata()
                db.session.commit()
            except Exception as exc:  # noqa: BLE001 — Superset võib visata NoSuchTableError
                db.session.rollback()
                print(
                    f"  {dataset.table_name}: jäeti vahele ({exc!r})",
                    file=sys.stderr,
                )
                continue
            after = len(dataset.columns)
            print(f"  {dataset.table_name}: {before} -> {after} veergu")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
