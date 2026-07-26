"""Normalize raw source data into the canonical DuckDB schema.

Two source families feed the same tables:
  * data/raw/vlrgg/*.json   — live harvests from the unofficial API
  * data/raw/kaggle/**.csv  — historical scrape (2021-2026)

Run `vct inspect-kaggle` after the first download to see the actual CSV
layout, then implement the per-file loaders here against what exists rather
than guessing column names.
"""
from __future__ import annotations

import pandas as pd

from ..config import RAW_KAGGLE_DIR
from ..ingest.kaggle import list_csvs


def inspect_kaggle(preview_rows: int = 3) -> None:
    """Print every Kaggle CSV with its columns — the starting point for
    writing loaders."""
    csvs = list_csvs()
    if not csvs:
        print(f"No CSVs under {RAW_KAGGLE_DIR}. Run `vct download-kaggle` first.")
        return
    for path in csvs:
        rel = path.relative_to(RAW_KAGGLE_DIR)
        try:
            df = pd.read_csv(path, nrows=preview_rows)
        except Exception as exc:  # some scrape files can be malformed
            print(f"{rel}: FAILED to read ({exc})")
            continue
        print(f"{rel}: {list(df.columns)}")


# TODO: load_kaggle_matches(con), load_kaggle_player_stats(con), ...
# TODO: load_vlrgg_match_results(con) parsing data/raw/vlrgg/match_results_*.json
