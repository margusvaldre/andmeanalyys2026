"""Lae päevased arhiivid (featured + catalog_daily) CSV-failidest.

Käivitus:
    docker compose exec pipeline python scripts/ingest_daily_archives.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from daily_archive import ingest_all_archives


def main() -> int:
    return ingest_all_archives()


if __name__ == "__main__":
    raise SystemExit(main())
