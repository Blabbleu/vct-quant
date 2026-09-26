"""Read-only, hypothetical flat-unit paper entries from archived pre-start quotes.

The first eligible snapshot of each match is frozen. These are sampled
midpoints, not orders or fills; estimated ask includes half the observed spread.
No live outcomes are used to select the entry, threshold, or side.
"""
from __future__ import annotations

import json

import pandas as pd

from . import db
from .config import PROCESSED_DIR

GAP = 0.10
MAX_SPREAD = 0.10
MIN_VOLUME = 1000


def _valid_result(row: pd.Series, observed: pd.Series) -> bool:
    if row.tier != 1 or pd.isna(row.completed_at) or pd.to_datetime(row.completed_at, utc=True).normalize() < observed.predicted_at.normalize():
        return False
    if any(pd.isna(row[k]) for k in ("team_a_id", "team_b_id", "maps_a", "maps_b", "won_a", "won_b")):
        return False
    if {int(row.team_a_id), int(row.team_b_id)} != {int(observed.team_a_id), int(observed.team_b_id)}:
        return False
    a, b = int(row.maps_a), int(row.maps_b)
    return (a, b) in ((1, 0), (0, 1), (2, 0), (0, 2), (2, 1), (1, 2),
                       (3, 0), (0, 3), (3, 1), (1, 3), (3, 2), (2, 3)) and bool(row.won_a) == (a > b) and bool(row.won_b) == (b > a)


def paper_ledger(log: pd.DataFrame, results: pd.DataFrame) -> dict:
    """Return one frozen entry per qualified match, with unresolved rows explicit."""
    empty = {"n": 0, "settled": 0, "net_units": 0., "rows": [],
             "note": "Hypothetical, no orders or fills; ask estimated from sampled midpoint + half-spread. CLV is last comparable pre-start sample, not an exchange close."}
    if log.empty:
        return empty
    rows = log.copy()
    rows["predicted_at"] = pd.to_datetime(rows.predicted_at, utc=True, errors="coerce")
    rows["scheduled_at"] = pd.to_datetime(rows.scheduled_at, utc=True, errors="coerce")
    # Exact IDs only. An unresolved name key may refer to a different team.
    for column in ("team_a_id", "team_b_id", "p_market_a", "p_team_a_win", "market_spread", "market_volume"):
        rows[column] = pd.to_numeric(rows[column], errors="coerce")
    rows = rows.loc[
        rows.tier.eq(1) & rows.match_id.gt(0) & rows.predicted_at.lt(rows.scheduled_at)
        & rows.team_a_id.gt(0) & rows.team_b_id.gt(0) & rows.team_a_id.ne(rows.team_b_id)
        & rows.p_market_a.gt(0) & rows.p_market_a.lt(1)
        & rows.p_team_a_win.between(0, 1)
        & rows.market_spread.ge(0) & rows.market_spread.le(MAX_SPREAD)
        & rows.market_volume.ge(MIN_VOLUME)
        & rows.market_slug.notna() & rows.market_slug.ne("").fillna(False).astype(bool)
    ].sort_values(["predicted_at", "match_id"])
    rows = rows.loc[(rows.p_team_a_win - rows.p_market_a).abs().ge(GAP - 1e-12)]
    if rows.empty:
        return empty
    result_by_id = {int(r.match_id): r for _, r in results.iterrows()} if not results.empty else {}
    entries = []
    for match_id, group in rows.groupby("match_id", sort=False):
        entry = group.iloc[0]
        simultaneous = group.loc[group.predicted_at.eq(entry.predicted_at)]
        identity_and_price = ["team_a_id", "team_b_id", "p_team_a_win", "p_market_a", "market_spread", "market_slug"]
        if len(simultaneous[identity_and_price].drop_duplicates()) != 1:
            continue
        side_a = entry.p_team_a_win > entry.p_market_a
        side = "A" if side_a else "B"
        mid = float(entry.p_market_a if side_a else 1 - entry.p_market_a)
        ask = mid + float(entry.market_spread) / 2
        if not 0 < ask < 1:
            continue
        # Quotes with a different orientation/contract cannot be connected.
        all_quotes = log.loc[log.match_id.eq(match_id)].copy()
        all_quotes["predicted_at"] = pd.to_datetime(all_quotes.predicted_at, utc=True, errors="coerce")
        all_quotes["scheduled_at"] = pd.to_datetime(all_quotes.scheduled_at, utc=True, errors="coerce")
        later_mid = pd.to_numeric(all_quotes.p_market_a, errors="coerce")
        later_spread = pd.to_numeric(all_quotes.market_spread, errors="coerce")
        later_volume = pd.to_numeric(all_quotes.market_volume, errors="coerce")
        comparable = all_quotes.loc[
            all_quotes.predicted_at.gt(entry.predicted_at)
            & all_quotes.predicted_at.lt(all_quotes.scheduled_at)
            & all_quotes.predicted_at.lt(entry.scheduled_at)
            & all_quotes.team_a_id.eq(entry.team_a_id) & all_quotes.team_b_id.eq(entry.team_b_id)
            & all_quotes.market_slug.eq(entry.market_slug).fillna(False).astype(bool)
            & later_mid.gt(0) & later_mid.lt(1)
            & later_spread.ge(0) & later_spread.le(MAX_SPREAD)
            & later_volume.ge(MIN_VOLUME)
        ].sort_values("predicted_at")
        last = comparable.iloc[-1] if not comparable.empty else None
        last_mid = float(last.p_market_a if side_a else 1 - last.p_market_a) if last is not None else None
        outcome = result_by_id.get(int(match_id))
        status = "open" if outcome is None else "unverified"
        pnl = None
        if outcome is not None and _valid_result(outcome, entry):
            status = "settled"
            won = bool(outcome.won_a) if int(outcome.team_a_id) == int(entry.team_a_id) else bool(outcome.won_b)
            if not side_a:
                won = not won
            pnl = 1 / ask - 1 if won else -1.
        entries.append({"match_id": int(match_id), "team_a": str(entry.team_a_name),
                        "team_b": str(entry.team_b_name), "side": side,
                        "entry_at": entry.predicted_at.isoformat(),
                        "model": float(entry.p_team_a_win if side_a else 1 - entry.p_team_a_win),
                        "market_mid": mid, "entry_price": ask,
                        "last_sampled_market": last_mid,
                        "sampled_clv": round(last_mid - mid, 12) if last_mid is not None else None,
                        "status": status, "return_per_unit": pnl})
    return {**empty, "n": len(entries), "settled": sum(r["status"] == "settled" for r in entries),
            "net_units": sum(r["return_per_unit"] or 0 for r in entries), "rows": entries}


def main() -> None:
    path = PROCESSED_DIR / "prediction_log.parquet"
    log = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    with db.connect(read_only=True) as con:
        results = con.execute("""
            SELECT m.match_id, m.completed_at, e.tier,
                   a.team_id AS team_a_id, b.team_id AS team_b_id,
                   a.team_name AS team_a_name, b.team_name AS team_b_name,
                   a.series_score AS maps_a, b.series_score AS maps_b,
                   a.is_winner AS won_a, b.is_winner AS won_b
            FROM match m JOIN event e ON e.event_id = m.event_id
            JOIN match_team a ON a.match_id = m.match_id AND a.team_number = 1
            JOIN match_team b ON b.match_id = m.match_id AND b.team_number = 2
            WHERE m.match_id IN (SELECT unnest(?))
        """, [log.match_id.dropna().unique().tolist() if not log.empty else []]).df()
    print(json.dumps(paper_ledger(log, results), allow_nan=False))


if __name__ == "__main__":
    main()
