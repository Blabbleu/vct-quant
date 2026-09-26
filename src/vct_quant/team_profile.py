"""Read-only Tier-1 team profile by exact vlr.gg team ID.

Recorded form is descriptive, not an input to the production Elo forecast.
Name-keyed unresolved teams are deliberately not fused into numeric identities.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import pandas as pd

from .config import PROCESSED_DIR
from .features.build import match_sequence
from .logos import load_logos, load_tags
from .recent_lineup import recent_lineup


def profile_from_rows(history: pd.DataFrame, fixtures: pd.DataFrame,
                      team_id: int, as_of: str, limit: int = 20) -> dict | None:
    """Return recent dated played Tier-1 series and future cached forecasts."""
    key = str(team_id)
    now = pd.to_datetime(as_of, utc=True)
    played = history.iloc[:0].copy()
    if not history.empty:
        dates = pd.to_datetime(history.completed_at, utc=True, errors="coerce")
        played = history.loc[
            history.tier.eq(1) & (history.team_a.eq(key) | history.team_b.eq(key))
            & history.team_a.ne(history.team_b)
            & dates.dt.normalize().le(now.normalize())
            & history.score_a.isin((0., 1.))
            & history.maps_a.notna() & history.maps_b.notna()
            & (history.maps_a + history.maps_b).gt(0)
            & history.team_a_name.ne("TBD") & history.team_b_name.ne("TBD")
        ].copy()
        played["completed_at"] = dates.loc[played.index]
        played = played.sort_values(["completed_at", "match_id"], ascending=False)

    upcoming = fixtures.iloc[:0].copy()
    if not fixtures.empty:
        starts = pd.to_datetime(fixtures.scheduled_at, utc=True, errors="coerce")
        tiers = fixtures.tier.fillna(1).eq(1) if "tier" in fixtures else pd.Series(True, index=fixtures.index)
        upcoming = fixtures.loc[
            tiers & (fixtures.team_a_key.eq(key) | fixtures.team_b_key.eq(key)) & starts.gt(now)
        ].copy()
        upcoming["scheduled_at"] = starts.loc[upcoming.index]
        upcoming = upcoming.sort_values(["scheduled_at", "match_id"]).drop_duplicates("match_id")
    if played.empty and upcoming.empty:
        return None

    if not upcoming.empty:
        first = upcoming.iloc[0]
        name = first.team_a_name if first.team_a_key == key else first.team_b_name
    else:
        first = played.iloc[0]
        name = first.team_a_name if first.team_a == key else first.team_b_name

    results = []
    for row in played.head(limit).itertuples():
        left = row.team_a == key
        results.append({
            "match_id": int(row.match_id), "completed_at": row.completed_at.isoformat(),
            "opponent": row.team_b_name if left else row.team_a_name,
            "opponent_id": int(row.team_b if left else row.team_a) if
            str(row.team_b if left else row.team_a).isdigit() else None,
            "result": "W" if (row.score_a == 1.) == left else "L",
            "maps_for": int(row.maps_a if left else row.maps_b),
            "maps_against": int(row.maps_b if left else row.maps_a),
        })
    scheduled = []
    for row in upcoming.head(limit).itertuples():
        left = row.team_a_key == key
        scheduled.append({
            "match_id": int(row.match_id), "scheduled_at": row.scheduled_at.isoformat(),
            "opponent": row.team_b_name if left else row.team_a_name,
            "opponent_id": int(row.team_b_key if left else row.team_a_key) if
            str(row.team_b_key if left else row.team_a_key).isdigit() else None,
            "p_win": float(row.p_team_a_win if left else 1 - row.p_team_a_win),
        })
    wins = int(((played.team_a.eq(key) & played.score_a.eq(1.)) |
                (played.team_b.eq(key) & played.score_a.eq(0.))).sum()) if not played.empty else 0
    return {"team_id": team_id, "name": name,
            "record": {"wins": wins, "losses": len(played) - wins},
            "results": results, "fixtures": scheduled,
            "note": "Dated played Tier-1 series with map scores; excludes draws, forfeits and unresolved team identities. Results may be incomplete."}


def team_profile(team_id: int) -> dict | None:
    path = PROCESSED_DIR / "upcoming_tier1.parquet"
    fixtures = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    now = datetime.now(timezone.utc)
    result = profile_from_rows(match_sequence(tiers=(1,)), fixtures, team_id,
                               now.isoformat())
    if result is not None:
        result["logo"] = load_logos().get(str(team_id))
        result["tag"] = load_tags().get(str(team_id))
        result["recent_lineup"] = recent_lineup(team_id, as_of=now)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("team_id", type=int)
    args = parser.parse_args()
    if args.team_id <= 0:
        parser.error("team_id must be positive")
    print(json.dumps(team_profile(args.team_id), allow_nan=False))


if __name__ == "__main__":
    main()
