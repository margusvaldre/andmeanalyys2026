"""Unpack Superset native dashboard ZIP into ``dashboard_export/`` for automated import.

Superset UI export uses filenames like ``Paritolumaad_4.yaml``. This script strips the
numeric suffix, copies YAML into the repo layout, and applies Postgres placeholders on
the database connection file.

Default source: ``dashboard_export_source.zip`` (symlink or copy of the dated export).
Rollback: restore ``dashboard_export_backup_20260519/`` (see docs/superset.md).
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_ZIP = ROOT / "dashboard_export_source.zip"
DEFAULT_TARGET = ROOT / "dashboard_export"
BACKUP_DIR = ROOT / "dashboard_export_backup_20260519"

PLACEHOLDERS = {
    "__POSTGRES_USER__": "praktikum",
    "__POSTGRES_PASSWORD__": "praktikum",
    "__POSTGRES_DB__": "praktikum",
    "__POSTGRES_HOST__": "db",
    "__POSTGRES_PORT__": "5432",
}

SUFFIX_RE = re.compile(r"_(\d+)$")


def normalize_stem(name: str) -> str:
    """``Paritolumaad_4`` -> ``Paritolumaad``."""
    stem = Path(name).stem
    while True:
        match = SUFFIX_RE.search(stem)
        if not match:
            break
        stem = stem[: match.start()]
    return stem


def target_name(relative: Path) -> Path:
    if relative.suffix.lower() not in {".yaml", ".yml"}:
        return relative
    parent = relative.parent
    return parent / f"{normalize_stem(relative.name)}{relative.suffix}"


def strip_native_filters_from_dashboard_yaml(text: str) -> str:
    """UI ekspordi filtrid kasutavad teammate chartId-sid; jäta tühjaks (loo käsitsi)."""
    import yaml

    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return text
    meta = data.setdefault("metadata", {})
    meta["native_filter_configuration"] = []
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def render_database_yaml(text: str) -> str:
    """Ensure import uses env placeholders, not a teammate's local SQLAlchemy URI."""
    if "__POSTGRES_USER__" in text:
        return text
    # Replace concrete postgresql URI from UI export with placeholders.
    text = re.sub(
        r"sqlalchemy_uri:\s*postgresql\+psycopg2://[^\n]+",
        "sqlalchemy_uri: postgresql+psycopg2://__POSTGRES_USER__:__POSTGRES_PASSWORD__@"
        "__POSTGRES_HOST__:__POSTGRES_PORT__/__POSTGRES_DB__",
        text,
        count=1,
    )
    return text


def find_export_root(extracted: Path) -> Path:
    if (extracted / "metadata.yaml").is_file():
        return extracted
    children = [p for p in extracted.iterdir() if p.is_dir()]
    if len(children) == 1 and (children[0] / "metadata.yaml").is_file():
        return children[0]
    for child in children:
        if (child / "metadata.yaml").is_file():
            return child
    raise FileNotFoundError(f"metadata.yaml not found under {extracted}")


def unpack_zip(zip_path: Path, target_dir: Path, *, dry_run: bool) -> list[str]:
    actions: list[str] = []
    with tempfile.TemporaryDirectory(prefix="superset_export_") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(tmp_path)
        export_root = find_export_root(tmp_path)

        if target_dir.exists():
            if not dry_run:
                shutil.rmtree(target_dir)
            actions.append(f"removed {target_dir}")

        for src in sorted(export_root.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(export_root)
            dest_rel = target_name(rel)
            dest = target_dir / dest_rel
            actions.append(f"{rel.as_posix()} -> {dest_rel.as_posix()}")
            if dry_run:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = src.read_text(encoding="utf-8")
            if dest_rel.as_posix() == "databases/Jupiter_PostgreSQL.yaml":
                content = render_database_yaml(content)
            if dest_rel.as_posix() == "dashboards/Jupiteri_analuus.yaml":
                content = strip_native_filters_from_dashboard_yaml(content)
            dest.write_text(content, encoding="utf-8", newline="\n")

    return actions


def ensure_source_zip(zip_path: Path) -> None:
    if zip_path.is_file():
        return
    dated = ROOT / "dashboard_export_20260603T213354.zip"
    if dated.is_file():
        shutil.copy2(dated, zip_path)
        print(f"Kopeerisin {dated.name} -> {zip_path.name}")
        return
    raise FileNotFoundError(
        f"ZIP puudub: {zip_path} (või lisa {dated.name} kausta superset/)"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--zip",
        type=Path,
        default=DEFAULT_ZIP,
        help=f"Superset export ZIP (default: {DEFAULT_ZIP.name})",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
        help="Output directory (default: dashboard_export/)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print planned copies")
    args = parser.parse_args(argv)

    zip_path = args.zip.resolve()
    target_dir = args.target.resolve()

    if not args.dry_run:
        ensure_source_zip(zip_path)
    elif not zip_path.is_file():
        print(f"ZIP puudub (dry-run): {zip_path}", file=sys.stderr)
        return 1

    if not BACKUP_DIR.is_dir():
        print(
            f"Hoiatus: tagasipöördumise kaust puudub: {BACKUP_DIR}",
            file=sys.stderr,
        )

    actions = unpack_zip(zip_path, target_dir, dry_run=args.dry_run)
    print(f"{'[dry-run] ' if args.dry_run else ''}Valmis: {len(actions)} faili -> {target_dir}")
    for line in actions[:12]:
        print(f"  {line}")
    if len(actions) > 12:
        print(f"  ... ja veel {len(actions) - 12}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
