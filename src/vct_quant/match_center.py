"""Read-only, sampled pre-start probability movement for a match."""
from __future__ import annotations

import argparse
import json
import math

import pandas as pd

from .config import PROCESSED_DIR
from .features.build import match_sequence


def recent_form(matches: pd.DataFrame, team_a_key: str, team_b_key: str,
                match_id: int, as_of: str, limit: int = 5) -> dict:
    """Last played Tier-1 series known at the forecast refresh, not at page load.

    Both the match-ID ordering and completion date must precede the forecast
    UTC day (source timestamps are often midnight placeholders, not final whistle).
    Undated, drawn, scoreless and anonymous-placeholder results are omitted.
    This is descriptive history, not a model input or a cross-pool rating.
    """
    empty = {"a": [], "b": []}
    if matches.empty:
        return empty
    cutoff = pd.to_datetime(as_of, utc=True)
    dates = pd.to_datetime(matches.completed_at, utc=True, errors="coerce")
    played = matches.loc[
        matches.tier.eq(1) & matches.match_id.lt(match_id) & dates.dt.normalize().lt(cutoff.normalize())
        & matches.score_a.isin((0., 1.))
        & matches.maps_a.notna() & matches.maps_b.notna()
        & (matches.maps_a + matches.maps_b).gt(0)
        & matches.team_a_name.ne("TBD") & matches.team_b_name.ne("TBD")
    ].copy()
    played["completed_at"] = dates.loc[played.index]
    result = {}
    for side, key in (("a", team_a_key), ("b", team_b_key)):
        # Use identity keys, never fuzzy names; one result per match even when
        # a malformed source lists the same team on both sides.
        subset = played.loc[
            (played.team_a.eq(key) | played.team_b.eq(key))
            & played.team_a.ne(played.team_b)
        ].sort_values(["completed_at", "match_id"], ascending=False).head(limit)
        result[side] = []
        for row in subset.itertuples():
            left = row.team_a == key
            won = (row.score_a == 1.) if left else (row.score_a == 0.)
            result[side].append({"match_id": int(row.match_id),
                                 "opponent": row.team_b_name if left else row.team_a_name,
                                 "result": "W" if won else "L",
                                 "completed_at": row.completed_at.isoformat()})
    return result



def movement(log: pd.DataFrame, match_id: int) -> dict | None:
    """Keep the latest pairing's orientation; never connect swapped sides."""
    if log.empty:
        return None
    rows = log.loc[log.match_id.eq(match_id)].copy()
    if rows.empty:
        return None
    rows["predicted_at"] = pd.to_datetime(rows.predicted_at, utc=True, errors="coerce")
    rows["scheduled_at"] = pd.to_datetime(rows.scheduled_at, utc=True, errors="coerce")
    rows = rows.loc[rows.predicted_at.lt(rows.scheduled_at) & rows.p_team_a_win.between(0, 1)]
    if rows.empty:
        return None
    rows = rows.sort_values("predicted_at")
    latest = rows.iloc[-1]
    rows = rows.loc[rows.team_a_key.eq(latest.team_a_key) & rows.team_b_key.eq(latest.team_b_key)]
    rows = rows.drop_duplicates("predicted_at", keep="last")
    points = []
    for r in rows.itertuples():
        market = r.p_market_a
        same_contract = pd.notna(latest.market_slug) and r.market_slug == latest.market_slug
        has_market = same_contract and pd.notna(market) and math.isfinite(float(market))
        points.append({
            "observed_at": r.predicted_at.isoformat(),
            "elo": float(r.p_team_a_win),
            "market": float(market) if has_market else None,
            "spread": float(r.market_spread) if has_market and pd.notna(r.market_spread) else None,
        })
    return {"match_id": int(match_id), "team_a": latest.team_a_name,
            "team_b": latest.team_b_name, "team_a_key": str(latest.team_a_key),
            "team_b_key": str(latest.team_b_key),
            "scheduled_at": latest.scheduled_at.isoformat(),
            "points": points, "note": "Sampled refreshes, not exchange open/close prices."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("match_id", type=int)
    args = parser.parse_args()
    if args.match_id <= 0:
        parser.error("match_id must be positive")
    path = PROCESSED_DIR / "prediction_log.parquet"
    data = pd.read_parquet(path, filters=[("match_id", "==", args.match_id)]) if path.exists() else pd.DataFrame()
    result = movement(data, args.match_id)
    if result is not None:
        result["recent_form"] = recent_form(
            match_sequence(tiers=(1,)), result["team_a_key"], result["team_b_key"],
            args.match_id, result["points"][-1]["observed_at"],
        )
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
