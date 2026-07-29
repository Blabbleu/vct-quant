"""Command-line entrypoints. Installed as `vct` (see pyproject.toml)."""
from __future__ import annotations

import argparse


def _materialize_upcoming(data):
    from .config import PROCESSED_DIR
    from .etl.normalize import official_upcoming
    from .features.build import predict_upcoming

    fixtures = predict_upcoming(official_upcoming(data))
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / "upcoming_tier1.parquet"
    fixtures.to_parquet(path, index=False)
    return fixtures, path


def _predict_match_details(data):
    from .etl.normalize import official_match_details
    from .features.build import predict_upcoming

    fixture = official_match_details(data)
    return predict_upcoming(fixture) if not fixture.empty else fixture


def _refresh_prediction(match_id):
    from .ingest import vlrgg

    return _predict_match_details(vlrgg.fetch_match_details(match_id))


def _print_predictions(fixtures) -> None:
    display = fixtures[[
        "match_id", "scheduled_at", "event_name", "team_a_name",
        "p_team_a_win", "team_b_name", "p_team_b_win",
        "most_likely_score", "p_most_likely_score",
    ]].copy()
    display["p_team_a_win"] = display.p_team_a_win.map("{:.1%}".format)
    display["p_team_b_win"] = display.p_team_b_win.map("{:.1%}".format)
    display["p_most_likely_score"] = display.p_most_likely_score.map("{:.1%}".format)
    print(display.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(prog="vct", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Create the DuckDB database from sql/schema.sql")
    sub.add_parser("update", help="Refresh results, ratings, fixtures, and predictions")
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
    p = sub.add_parser(
        "predict", aliases=["prediction"],
        help="Predict one upcoming official Tier-1 match",
    )
    p.add_argument("match_id", type=int, help="Numeric vlr.gg match ID")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p.add_argument(
        "--maps", nargs="+", metavar="MAP",
        help="Ordered map picks (three for Bo3, five for Bo5)",
    )
    p = sub.add_parser("predictions", help="List all upcoming official Tier-1 predictions")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p = sub.add_parser("ranking", help="Rank current VCT teams by Elo")
    p.add_argument("--top", type=int, default=25, help="Number of teams to show (default: 25)")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    args = parser.parse_args()

    if args.cmd == "init-db":
        from . import db

        db.init_db()
        print(f"Initialized {db.DB_PATH}")
    elif args.cmd == "update":
        from .etl import normalize
        from .ingest import vlrgg

        results = vlrgg.fetch_match_results()
        result_count = len(results.get("data", {}).get("segments", []))
        print(f"Fetched {result_count} recent results")
        print(normalize.load_vlrgg_match_results())

        upcoming = vlrgg.fetch_upcoming_matches()
        fixtures, path = _materialize_upcoming(upcoming)
        upcoming_count = len(upcoming.get("data", {}).get("segments", []))
        print(
            f"Fetched {upcoming_count} upcoming entries; retained "
            f"{len(fixtures)} Tier-1 -> {path}"
        )
    elif args.cmd == "ingest-vlrgg":
        from .ingest import vlrgg

        if args.what == "results":
            data = vlrgg.fetch_match_results()
            segments = data.get("data", {}).get("segments", [])
            print(f"Fetched {len(segments)} results entries -> data/raw/vlrgg/")
        else:
            data = vlrgg.fetch_upcoming_matches()
            fixtures, path = _materialize_upcoming(data)
            total = len(data.get("data", {}).get("segments", []))
            print(f"Fetched {total} upcoming entries; retained {len(fixtures)} Tier-1 -> {path}")
            if not fixtures.empty:
                _print_predictions(fixtures)
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
    elif args.cmd in ("predict", "prediction"):
        import pandas as pd

        from .config import PROCESSED_DIR

        if args.match_id <= 0:
            parser.error("match_id must be positive")
        path = PROCESSED_DIR / "upcoming_tier1.parquet"
        fixtures = pd.read_parquet(path) if path.exists() else pd.DataFrame()
        found = fixtures[fixtures.match_id.eq(args.match_id)] if not fixtures.empty else fixtures
        if found.empty or not args.maps:
            from requests import RequestException

            try:
                refreshed = _refresh_prediction(args.match_id)
            except RequestException:
                if found.empty:
                    raise
            else:
                if not refreshed.empty:
                    found = refreshed
        if found.empty:
            parser.error(
                f"{args.match_id} is not an upcoming official Tier-1 match"
            )

        from .features.build import add_map_predictions, add_score_predictions

        found = add_score_predictions(found)
        selected_maps = args.maps
        detected_maps = False
        if not selected_maps and "map_picks" in found:
            picks = found.map_picks.iloc[0]
            if isinstance(picks, list) and len(picks) == int(found.best_of.iloc[0]):
                selected_maps = picks
                detected_maps = True
        if selected_maps:
            try:
                found = add_map_predictions(found, selected_maps)
            except ValueError as exc:
                parser.error(str(exc))
        match = found.iloc[0]
        if args.json:
            print(match.to_json(date_format="iso"))
        else:
            print(f"{match.event_name} — {match.event_series}")
            print(f"{match.team_a_name}: {match.p_team_a_win:.1%}")
            print(f"{match.team_b_name}: {match.p_team_b_win:.1%}")
            if selected_maps:
                print(f"Maps{' (detected)' if detected_maps else ''}:")
                for map_prediction in match.map_predictions:
                    print(
                        f"  {map_prediction['map'].title()}: "
                        f"{match.team_a_name} {map_prediction['p_team_a_win']:.1%} | "
                        f"{match.team_b_name} {map_prediction['p_team_b_win']:.1%} "
                        f"(history {map_prediction['team_a_map_matches']}/"
                        f"{map_prediction['team_b_map_matches']})"
                    )
            print(f"Exact score (Bo{match.best_of}):")
            for score, probability in match.score_probabilities.items():
                a_maps, b_maps = map(int, score.split("-"))
                winner = match.team_a_name if a_maps > b_maps else match.team_b_name
                print(f"  {winner} {max(a_maps, b_maps)}-{min(a_maps, b_maps)}: {probability:.1%}")
            print(
                f"Sweep: {match.p_sweep:.1%} | Full distance: "
                f"{match.p_full_distance:.1%} | Expected maps: {match.expected_maps:.2f}"
            )
            print(f"Starts: {match.scheduled_at}")
            print(f"Ratings through match {match.ratings_through_match_id}")
            print(match.vlr_url)
    elif args.cmd == "predictions":
        import pandas as pd

        from .config import PROCESSED_DIR

        path = PROCESSED_DIR / "upcoming_tier1.parquet"
        if path.exists():
            fixtures = pd.read_parquet(path)
        else:
            from .ingest import vlrgg

            fixtures, _ = _materialize_upcoming(vlrgg.fetch_upcoming_matches())
        if fixtures.empty:
            parser.error("no official Tier-1 fixtures in the current upcoming feed")
        from .features.build import add_score_predictions

        fixtures = add_score_predictions(fixtures)
        if args.json:
            print(fixtures.to_json(orient="records", date_format="iso"))
        else:
            _print_predictions(fixtures)
    elif args.cmd == "ranking":
        from .features.build import current_rankings

        if args.top <= 0:
            parser.error("--top must be positive")
        rankings = current_rankings().head(args.top)
        if rankings.empty:
            parser.error("no completed official Tier-1 matches found")
        if args.json:
            print(rankings.to_json(orient="records"))
        else:
            display = rankings[["rank", "team_name", "elo", "season_matches"]].copy()
            display["elo"] = display.elo.map("{:.1f}".format)
            print(f"VCT {rankings.season.iloc[0]} power ranking")
            print(display.to_string(index=False))


if __name__ == "__main__":
    main()
