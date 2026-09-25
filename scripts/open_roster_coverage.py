"""Read-only 2027 open-stage roster coverage and targeted detail backlog.

    python scripts/open_roster_coverage.py
    python scripts/open_roster_coverage.py --season 2027 --per-team 3

The November 2026 qualifiers belong to the *2027 event title*, not the UTC
calendar year. Missing map/player rows prevent the carry-over shadow from
recognising a newly promoted team's prior lineup. This script never fetches or
writes raw data; it enumerates detail IDs to harvest after official events land.
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from collections.abc import Mapping

import pandas as pd

from vct_quant import db
from vct_quant.etl.events import LAST_CHANCE, OPEN_STAGE
from vct_quant.features.build import load_rosters, match_sequence

META_SQL = """
SELECT m.match_id, e.name AS event_name, m.completed_at
FROM match m JOIN event e USING (event_id)
WHERE e.tier IN (1, 2)
"""


def season_open_matches(history: pd.DataFrame, metadata: pd.DataFrame, season: int) -> pd.DataFrame:
    """Completed 2027-season open-stage matches, ordered by match ID."""
    title = metadata.event_name.fillna("").str.lower()
    season_token = re.compile(rf"(?<!\d){season}(?!\d)")
    eligible = metadata.loc[
        title.map(lambda text: bool(season_token.search(text) and
                                    (OPEN_STAGE.search(text) or LAST_CHANCE.search(text))))
        & metadata.completed_at.notna(),
        ["match_id"],
    ]
    return history.loc[history.tier.eq(2) & history.match_id.isin(eligible.match_id)]


def detail_backlog(
    matches: pd.DataFrame,
    rosters: Mapping[tuple[int, int], frozenset],
    per_team: int = 3,
) -> tuple[list[int], int, int]:
    """Latest N matches per named team, deduped; fetch if either side lacks 5.

    Returns (match IDs needing detail, eligible sides, sides already with >=5
    players). Rank the latest *before* filtering for missing stats, so an old
    match cannot displace the actual last lineup just because its data is absent.
    """
    if per_team < 1:
        raise ValueError("per_team must be positive")
    ranked: dict[str, list[int]] = defaultdict(list)
    sides = covered = 0
    for row in matches.sort_values("match_id", ascending=False).itertuples(index=False):
        match_id = int(row.match_id)
        for side, team in ((1, row.team_a), (2, row.team_b)):
            if team is None or str(team).startswith("name:tbd"):
                continue
            sides += 1
            covered += len(rosters.get((match_id, side), ())) >= 5
            if len(ranked[str(team)]) < per_team:
                ranked[str(team)].append(match_id)
    selected = {m for ids in ranked.values() for m in ids}
    missing = [
        int(row.match_id) for row in matches.itertuples(index=False)
        if int(row.match_id) in selected and any(
            len(rosters.get((int(row.match_id), side), ())) < 5
            for side in (1, 2)
        )
    ]
    return sorted(set(missing)), sides, covered


def calendar_coverage(
    history: pd.DataFrame,
    metadata: pd.DataFrame,
    rosters: Mapping[tuple[int, int], frozenset],
    years: tuple[int, ...] = (2023, 2024, 2025, 2026),
) -> list[tuple[int, int, int, int, int]]:
    """(calendar year, tier, matches, eligible sides, full-lineup sides)."""
    dated = history.merge(metadata[["match_id", "completed_at"]], on="match_id", how="left")
    dated["calendar_year"] = pd.to_datetime(dated.completed_at, utc=True).dt.year
    out = []
    for year in years:
        for tier in (1, 2):
            rows = dated.loc[dated.calendar_year.eq(year) & dated.tier.eq(tier)]
            full = sum(
                len(rosters.get((int(match_id), side), ())) >= 5
                for match_id in rows.match_id for side in (1, 2)
            )
            out.append((year, tier, len(rows), len(rows) * 2, full))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2027)
    parser.add_argument("--per-team", type=int, default=3)
    args = parser.parse_args()
    if args.per_team < 1 or args.season < 2027:
        parser.error("per-team must be positive and season must be 2027 or later")
    with db.connect(read_only=True) as con:
        history = match_sequence(con)
        metadata = con.execute(META_SQL).df()
        rosters = load_rosters(con)
    for year, tier, n, sides_count, full in calendar_coverage(history, metadata, rosters):
        print(f"{year} tier {tier}: {n} dated matches, >=5 players on {full}/{sides_count} sides")
    matches = season_open_matches(history, metadata, args.season)
    backlog, sides, covered = detail_backlog(matches, rosters, args.per_team)
    print(f"{args.season} open-stage completed matches: {len(matches)}")
    print(f"eligible sides with >=5 player IDs/handles: {covered}/{sides}")
    print(f"last {args.per_team} per team, missing roster detail: {len(backlog)} matches")
    print("detail match IDs:", " ".join(map(str, backlog[:100])))
    if len(backlog) > 100:
        print(f"... {len(backlog) - 100} more; use the Python function for full list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
