"""Read-only, sampled pre-start probability movement for a match."""
from __future__ import annotations

import argparse
import json
import math

import pandas as pd

from .config import PROCESSED_DIR


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
            "team_b": latest.team_b_name, "scheduled_at": latest.scheduled_at.isoformat(),
            "points": points, "note": "Sampled refreshes, not exchange open/close prices."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("match_id", type=int)
    args = parser.parse_args()
    if args.match_id <= 0:
        parser.error("match_id must be positive")
    path = PROCESSED_DIR / "prediction_log.parquet"
    data = pd.read_parquet(path, filters=[("match_id", "==", args.match_id)]) if path.exists() else pd.DataFrame()
    print(json.dumps(movement(data, args.match_id), allow_nan=False))


if __name__ == "__main__":
    main()
