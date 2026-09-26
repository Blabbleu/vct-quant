"""Audit pre-start logged side order against later canonical order (read-only).

    vctdev python -m scripts.prospective_side_order

This is a provenance gate for the proposed GC side-order shadow, NOT a
backtest. A log timestamp before a *scheduled* start is not definitive proof
of actual kickoff when a match was rescheduled; completion dates earlier than
the scheduled day are withheld, and the remaining scheduling risk is reported.
Neither the log nor canonical DB is modified.
"""
from __future__ import annotations

import json

import pandas as pd

from vct_quant.match_result import identity_key

STATES = ("same", "flipped", "unmatched", "ambiguous", "pending", "stale_start")


def _orientation(row: pd.Series, sides: pd.DataFrame) -> str:
    if len(sides) != 2 or set(sides.team_number) != {1, 2}:
        return "ambiguous"
    first, second = [sides[sides.team_number.eq(n)].iloc[0] for n in (1, 2)]
    keys = []
    for side in (first, second):
        keys.append({identity_key(side.team_id, side.team_name),
                     identity_key(None, side.team_name)} - {None})
    a, b = str(row.team_a_key), str(row.team_b_key)
    if not a or not b or a == b or not keys[0] or not keys[1]:
        return "ambiguous"
    straight = a in keys[0] and b in keys[1]
    flipped = a in keys[1] and b in keys[0]
    if straight and flipped:
        return "ambiguous"
    return "same" if straight else "flipped" if flipped else "unmatched"


def audit_orientation(log: pd.DataFrame, canonical: pd.DataFrame) -> dict:
    """Count last strictly pre-scheduled-start pairing against completed rows.

    Both sides must map one-to-one by canonical numeric ID or the *same side's*
    name fallback. Never fuzzy-match aliases, infer from winner, pool matches,
    or admit post-start forecasts. A match with missing/duplicate canonical
    rows is ambiguous, not evidence of same ordering.
    """
    out: dict = {"by_tier": {}, "issues": []}
    if log.empty:
        return out
    pre = log.copy()
    for col in ("predicted_at", "scheduled_at"):
        pre[col] = pd.to_datetime(pre[col], utc=True, errors="coerce")
    pre = pre.loc[pre.predicted_at.lt(pre.scheduled_at)].sort_values("predicted_at")
    if pre.empty:
        return out
    for match_id, history in pre.groupby("match_id", sort=True):
        row = history.iloc[-1]
        if pd.isna(row.tier):
            continue
        tier = int(row.tier)
        counts = out["by_tier"].setdefault(str(tier),
            {"logged_prestart": 0, "changed_prestart_order": 0,
             **dict.fromkeys(STATES, 0)})
        counts["logged_prestart"] += 1
        sides = canonical.loc[canonical.match_id.eq(match_id)]
        if sides.empty or not sides.status.eq("completed").all():
            label = "pending"
        elif len(sides) != 2 or set(sides.team_number) != {1, 2}:
            label = "ambiguous"
        else:
            completed = pd.to_datetime(sides.completed_at, utc=True, errors="coerce")
            if completed.isna().any() or completed.dt.normalize().lt(row.scheduled_at.normalize()).any():
                label = "stale_start"
            else:
                # Two conflicting pairings with the same last timestamp have
                # no well-defined latest pre-start orientation.
                latest = history.loc[history.predicted_at.eq(row.predicted_at)]
                label = ("ambiguous" if latest[["team_a_key", "team_b_key"]].drop_duplicates().shape[0] != 1
                         else _orientation(row, sides))
        counts[label] += 1
        # A pre-start order reversal can be hidden by the final log row.
        # Compare resolved orientations, not raw keys: name -> numeric-ID
        # upgrades on the same side are expected and are not reversals.
        seen = {_orientation(old, sides) for _, old in history.iterrows()}
        if label in {"same", "flipped"} and {"same", "flipped"}.issubset(seen):
            counts["changed_prestart_order"] += 1
            out["issues"].append({"match_id": int(match_id), "tier": tier,
                                  "orientation": "changed_prestart_order"})
        if label in {"flipped", "unmatched", "ambiguous", "stale_start"}:
            out["issues"].append({"match_id": int(match_id), "tier": tier, "orientation": label})
    return out


def main() -> None:
    from vct_quant import db
    from vct_quant.config import PROCESSED_DIR

    path = PROCESSED_DIR / "prediction_log.parquet"
    if not path.exists():
        print(json.dumps({"by_tier": {}, "issues": [], "note": "prediction log absent"}))
        return
    log = pd.read_parquet(path)
    if log.empty:
        print(json.dumps({"by_tier": {}, "issues": [], "note": "prediction log empty"}))
        return
    # Bind match IDs as parameters. No raw files or live DB writes.
    ids = sorted({int(x) for x in log.match_id.dropna() if int(x) > 0})
    with db.connect(read_only=True) as con:
        canonical = (con.execute("""
            SELECT m.match_id, m.status, m.completed_at, mt.team_number,
                   mt.team_id, mt.team_name
            FROM match m JOIN match_team mt USING (match_id)
            WHERE m.match_id IN (""" + ",".join("?" for _ in ids) + ")", ids).df()
            if ids else pd.DataFrame(columns=["match_id", "status", "completed_at",
                                               "team_number", "team_id", "team_name"]))
    report = audit_orientation(log, canonical)
    report["note"] = ("Pre-scheduled-start timestamps do not establish actual kickoff after a reschedule; "
                      "this is orientation provenance, not a forecast score or a clean holdout.")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
