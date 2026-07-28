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
    sub.add_parser("load-vlrgg-details", help="Load harvested maps and player stats")

    args = parser.parse_args()

    if args.cmd == "init-db":
        from . import db

        db.init_db()
        print(f"Initialized {db.DB_PATH}")
    elif args.cmd == "ingest-vlrgg":
        from .ingest import vlrgg

        if args.what == "results":
            data = vlrgg.fetch_match_results()
            segments = data.get("data", {}).get("segments", [])
            print(f"Fetched {len(segments)} results entries -> data/raw/vlrgg/")
        else:
            data = vlrgg.fetch_upcoming_matches()
            from .config import PROCESSED_DIR
            from .etl.normalize import official_upcoming
            from .features.build import predict_upcoming

            fixtures = predict_upcoming(official_upcoming(data))
            PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
            path = PROCESSED_DIR / "upcoming_tier1.parquet"
            fixtures.to_parquet(path, index=False)
            total = len(data.get("data", {}).get("segments", []))
            print(f"Fetched {total} upcoming entries; retained {len(fixtures)} Tier-1 -> {path}")
            if not fixtures.empty:
                display = fixtures[[
                    "scheduled_at", "event_name", "team_a_name",
                    "p_team_a_win", "team_b_name", "p_team_b_win",
                ]].copy()
                display["p_team_a_win"] = display.p_team_a_win.map("{:.1%}".format)
                display["p_team_b_win"] = display.p_team_b_win.map("{:.1%}".format)
                print(display.to_string(index=False))
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
    elif args.cmd == "load-vlrgg-details":
        from .etl import normalize

        print(normalize.load_vlrgg_match_details())


if __name__ == "__main__":
    main()
