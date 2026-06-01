"""Lae päevased arhiivid (featured + catalog_daily) CSV-failidest — varukoopia taastamine.

Käivitus (uus andmebaas, kõik failid):
    docker compose exec pipeline python scripts/ingest_daily_archives.py --all

Ainult päevad, mida stagingus veel pole:
    docker compose exec pipeline python scripts/ingest_daily_archives.py --missing-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from daily_archive import ingest_all_archives


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lae featured/catalog_daily arhiivid CSV-st (ükshaaval, mitte run-all osa)."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--all",
        action="store_true",
        help="Lae kõik arhiivfailid (soovitatav uue andmebaasi puhul).",
    )
    mode.add_argument(
        "--missing-only",
        action="store_true",
        help="Lae ainult päevad, mida staging.featured_daily / catalog_daily veel ei sisalda.",
    )
    args = parser.parse_args()
    if args.all and args.missing_only:
        parser.error("Vali kas --all või --missing-only, mitte mõlemad.")
    missing_only = args.missing_only
    if not args.all and not args.missing_only:
        print("Vaikimisi: --all (kõik arhiivfailid).")
    return ingest_all_archives(missing_only=missing_only)


if __name__ == "__main__":
    raise SystemExit(main())
