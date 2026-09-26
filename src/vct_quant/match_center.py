"""Read-only, sampled pre-start probability movement for a match."""
from __future__ import annotations

import argparse
import json
import math

import pandas as pd

from . import db
from .config import PROCESSED_DIR
from .features.build import match_sequence
from .logos import load_logos, load_tags


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



def map_pool_from_rows(rows: pd.DataFrame, team_a_key: str, team_b_key: str,
                       match_id: int, as_of: str, limit: int = 20) -> dict:
    """Descriptive last-N played Tier-1 maps, strictly before the forecast day/ID.

    Identity keys are the same as match_sequence. Do not interpret these
    empirical map wins as forecast odds or silently include Game Changers.
    """
    empty = {"a": [], "b": []}
    if rows.empty:
        return empty
    cutoff = pd.to_datetime(as_of, utc=True)
    dates = pd.to_datetime(rows.completed_at, utc=True, errors="coerce")
    names = rows.map_name.astype("string").str.strip()
    valid = rows.loc[
        rows.tier.eq(1) & rows.match_id.lt(match_id) & dates.dt.normalize().lt(cutoff.normalize())
        & rows.team_a.ne(rows.team_b)
        & rows.team_a_name.ne("TBD") & rows.team_b_name.ne("TBD")
        & names.notna() & names.ne("") & names.str.lower().ne("tbd")
        & rows.rounds_a.notna() & rows.rounds_b.notna()
        & (rows.rounds_a + rows.rounds_b).gt(0) & rows.rounds_a.ne(rows.rounds_b)
    ].copy()
    valid["completed_at"] = dates.loc[valid.index]
    valid["map_name"] = names.loc[valid.index].str.title()
    sort = ["completed_at", "match_id"] + (["map_number"] if "map_number" in valid else [])
    result = {}
    for side, key in (("a", team_a_key), ("b", team_b_key)):
        selected = valid.loc[valid.team_a.eq(key) | valid.team_b.eq(key)].sort_values(
            sort, ascending=False).head(limit)
        totals: dict[str, dict] = {}
        for row in selected.itertuples():
            left = row.team_a == key
            ours = int(row.rounds_a if left else row.rounds_b)
            theirs = int(row.rounds_b if left else row.rounds_a)
            record = totals.setdefault(row.map_name, {"map": row.map_name, "played": 0,
                                                       "won": 0, "round_share": 0, "_rounds": 0})
            record["played"] += 1
            record["won"] += ours > theirs
            record["round_share"] += ours
            record["_rounds"] += ours + theirs
        result[side] = sorted(({
            "map": r["map"], "played": r["played"], "won": r["won"],
            "round_share": r["round_share"] / r["_rounds"],
        } for r in totals.values()), key=lambda r: (-r["played"], r["map"]))
    return result


def map_pool(team_a_key: str, team_b_key: str, match_id: int, as_of: str) -> dict:
    """Read only map-level results for these exact identities from the dev/live DB."""
    with db.connect(read_only=True) as con:
        rows = con.execute("""
            SELECT mm.match_id, mm.map_number, mm.map_name, m.completed_at, e.tier,
                   coalesce(CAST(a.team_id AS VARCHAR), 'name:' || lower(trim(a.team_name))) AS team_a,
                   coalesce(CAST(b.team_id AS VARCHAR), 'name:' || lower(trim(b.team_name))) AS team_b,
                   a.team_name AS team_a_name, b.team_name AS team_b_name,
                   sa.total_rounds AS rounds_a, sb.total_rounds AS rounds_b
            FROM match_map mm
            JOIN match m ON m.match_id = mm.match_id
            JOIN event e ON e.event_id = m.event_id AND e.tier = 1
            JOIN match_team a ON a.match_id = m.match_id AND a.team_number = 1
            JOIN match_team b ON b.match_id = m.match_id AND b.team_number = 2
            JOIN match_map_team_score sa ON sa.match_map_id = mm.match_map_id AND sa.team_number = 1
            JOIN match_map_team_score sb ON sb.match_map_id = mm.match_map_id AND sb.team_number = 2
            WHERE m.match_id < ? AND CAST(m.completed_at AS DATE) < ?
              AND (coalesce(CAST(a.team_id AS VARCHAR), 'name:' || lower(trim(a.team_name))) IN (?, ?)
                OR coalesce(CAST(b.team_id AS VARCHAR), 'name:' || lower(trim(b.team_name))) IN (?, ?))
        """, [match_id, pd.to_datetime(as_of, utc=True).date(), team_a_key, team_b_key,
              team_a_key, team_b_key]).df()
    return map_pool_from_rows(rows, team_a_key, team_b_key, match_id, as_of)


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
        as_of = result["points"][-1]["observed_at"]
        result["recent_form"] = recent_form(
            match_sequence(tiers=(1,)), result["team_a_key"], result["team_b_key"],
            args.match_id, as_of,
        )
        result["map_pool"] = map_pool(
            result["team_a_key"], result["team_b_key"], args.match_id, as_of,
        )
        logos = load_logos()
        result["logo_a"] = logos.get(result["team_a_key"])
        result["logo_b"] = logos.get(result["team_b_key"])
        tags = load_tags()
        result["tag_a"] = tags.get(result["team_a_key"])
        result["tag_b"] = tags.get(result["team_b_key"])
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
