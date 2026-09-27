"""Read-only audit: Kaggle scores.csv team labels that don't appear in the Match Name.

    python scripts/team_label_audit.py

The Match Name ("NRG vs EDward Gaming") is written by the scraper from the page
title, while Team A/B are separate columns. A label that matches neither side of
the name (after abbreviation mapping) is a mislabel. Found 2026-09-27: every NRG
row in vct_2025 and vct_2026 labelled "Mega Minors" (25 + 25). Reports labels
with >= 3 mismatches, after applying `KAGGLE_TEAM_LABEL_FIXES`.
"""
from __future__ import annotations

from collections import Counter

import pandas as pd

from vct_quant.config import RAW_KAGGLE_DIR
from vct_quant.etl.normalize import _read_year, _year_dirs


def mismatches(scores: pd.DataFrame, full2abbr: dict[str, set[str]]) -> Counter:
    bad: Counter = Counter()
    for r in scores.itertuples(index=False):
        parts = [p.strip() for p in str(r[3]).split(" vs ")]
        if len(parts) != 2:
            continue
        for team in (r[4], r[5]):
            if team not in parts and not any(a in parts for a in full2abbr.get(team, ())):
                bad[team] += 1
    return bad


def main() -> int:
    mapping = pd.read_csv(RAW_KAGGLE_DIR / "all_ids" / "all_teams_mapping.csv").dropna()
    full2abbr: dict[str, set[str]] = {}
    for abbr, full in mapping.itertuples(index=False):
        full2abbr.setdefault(full, set()).add(abbr)
    found = 0
    for year_dir in _year_dirs():
        scores = _read_year(year_dir, "matches/scores.csv")
        if scores.empty:
            continue
        for team, n in mismatches(scores, full2abbr).most_common():
            if n >= 3:
                found += 1
                print(f"{year_dir.name}: {team!r} x{n} not in its Match Name")
        print(f"{year_dir.name}: {len(scores)} rows checked")
    print("no systematic mislabels" if not found else f"{found} systematic mislabel(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
