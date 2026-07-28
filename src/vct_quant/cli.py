"""Command-line entrypoints. Installed as `vct` (see pyproject.toml)."""
from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="vct", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Create the DuckDB database from sql/schema.sql")
    p = sub.add_parser("ingest-vlrgg", help="Fetch from vlrggapi into data/raw/vlrgg")
    p.add_argument(
        "--what", choices=["results", "upcoming"], default="results",
        help="Which match feed to fetch",
    )
    sub.add_parser("download-kaggle", help="Download/refresh the Kaggle VCT dataset")
    sub.add_parser("inspect-kaggle", help="List Kaggle CSVs and their columns")
    sub.add_parser("load-kaggle", help="Load Kaggle CSVs into the canonical tables")
    sub.add_parser("load-vlrgg", help="Merge the vlrggapi event harvest into match/match_team")

    args = parser.parse_args()

    if args.cmd == "init-db":
        from . import db

        db.init_db()
        print(f"Initialized {db.DB_PATH}")
    elif args.cmd == "ingest-vlrgg":
        from .ingest import vlrgg

        if args.what == "results":
            data = vlrgg.fetch_match_results()
        else:
            data = vlrgg.fetch_upcoming_matches()
        segments = data.get("data", {}).get("segments", [])
        print(f"Fetched {len(segments)} {args.what} entries -> data/raw/vlrgg/")
    elif args.cmd == "download-kaggle":
        from .ingest import kaggle

        kaggle.download()
        print(f"Downloaded {kaggle.DATASET} -> data/raw/kaggle/")
    elif args.cmd == "inspect-kaggle":
        from .etl import normalize

        normalize.inspect_kaggle()
    elif args.cmd == "load-kaggle":
        from .etl import normalize

        print(normalize.load_kaggle())

    elif args.cmd == "load-vlrgg":
        from .etl import normalize

        print(normalize.load_vlrgg_match_results())


if __name__ == "__main__":
    main()
