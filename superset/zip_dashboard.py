"""Paki Superseti dashboard imporditavaks ZIP-failiks."""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

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


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit("Kasutus: python zip_dashboard.py <source_dir> <target_zip>")

    source_dir = Path(argv[0]).resolve()
    target_zip = Path(argv[1]).resolve()
    root_name = "dashboard_export_jupiter"

    if not source_dir.exists():
        raise SystemExit(f"Kausta ei leitud: {source_dir}")

    target_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file():
                continue
            relative_path = path.relative_to(source_dir)
            archive_name = Path(root_name) / relative_path
            content = render(path.read_text(encoding="utf-8"))
            archive.writestr(str(archive_name), content)

    print(f"Kirjutasin Superseti impordifaili: {target_zip}")


if __name__ == "__main__":
    main(sys.argv[1:])
