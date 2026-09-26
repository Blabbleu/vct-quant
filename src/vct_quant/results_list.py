"""Finished logged fixtures: the last pre-start forecast beside a verified result.

Descriptive and read-only. Each row is the forecast the desk actually showed
before kickoff (the last prediction-log row strictly before ``scheduled_at``),
next to the canonical result as verified by ``match_result.load_result``. A
result that fails verification is listed as ``unverified`` with its reason and
carries no score, winner or loss, rather than being guessed. Nothing here feeds
ratings, shadows, grading or the checkpoint rule; per-tier aggregates are a
running tally, not a significance test (see Track record for that).
"""
from __future__ import annotations

import json
import math
from typing import Callable

import pandas as pd

from .config import PROCESSED_DIR
from .paper_ledger import MAX_SPREAD, MIN_VOLUME

Loader = Callable[[int, str, str, float], dict | None]


def _float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _liquid_market(row) -> float | None:
    market, spread, volume = (_float(getattr(row, c, None))
                              for c in ("p_market_a", "market_spread", "market_volume"))
    if market is None or spread is None or volume is None:
        return None
    if not (0 <= market <= 1 and 0 <= spread <= MAX_SPREAD and volume >= MIN_VOLUME):
        return None
    return market


def finished_results(log: pd.DataFrame, load: Loader, limit: int | None = None) -> dict:
    """Rows for logged fixtures whose canonical match is marked completed."""
    out = {"rows": [], "verified": 0, "unverified": 0, "by_tier": {}}
    if log.empty:
        return out
    log = log.copy()
    log["predicted_at"] = pd.to_datetime(log.predicted_at, utc=True, errors="coerce")
    log["scheduled_at"] = pd.to_datetime(log.scheduled_at, utc=True, errors="coerce")
    pre = log.loc[log.predicted_at.lt(log.scheduled_at)
                  & pd.to_numeric(log.p_team_a_win, errors="coerce").between(0, 1)]
    if pre.empty:
        return out
    last = pre.sort_values("predicted_at").groupby("match_id").tail(1)
    rows = []
    for r in last.itertuples():
        p = float(r.p_team_a_win)
        result = load(int(r.match_id), str(r.team_a_key), str(r.team_b_key), p)
        if result is None:
            continue
        ok = result.get("status") == "verified" and result.get("winner") in ("a", "b")
        a_won = ok and result["winner"] == "a"
        loss = -math.log(max(p if a_won else 1 - p, 1e-12)) if ok else None
        favourite_won = None if not ok or p == 0.5 else (p > 0.5) == a_won
        tier = None if pd.isna(r.tier) else int(r.tier)
        rows.append({
            "match_id": int(r.match_id), "tier": tier,
            "event": r.event_name, "series": getattr(r, "event_series", None),
            "best_of": None if pd.isna(r.best_of) else int(r.best_of),
            "scheduled_at": r.scheduled_at.isoformat(),
            "forecast_at": r.predicted_at.isoformat(),
            "team_a": r.team_a_name, "team_b": r.team_b_name,
            "team_a_key": str(r.team_a_key), "team_b_key": str(r.team_b_key),
            "p_a": p, "market_a": _liquid_market(r),
            "url": getattr(r, "vlr_url", None),
            "result": result, "log_loss": loss, "favourite_won": favourite_won,
        })
        key = "verified" if ok else "unverified"
        out[key] += 1
        if ok and tier is not None:
            t = out["by_tier"].setdefault(str(tier), {"verified": 0, "favourite_won": 0, "_loss": 0.0})
            t["verified"] += 1
            t["favourite_won"] += bool(favourite_won)
            t["_loss"] += loss
    for t in out["by_tier"].values():
        t["log_loss"] = t.pop("_loss") / t["verified"]
    rows.sort(key=lambda x: (x["scheduled_at"], x["match_id"]), reverse=True)
    out["rows"] = rows[:limit] if limit else rows
    return out


def main() -> None:
    from .logos import load_logos, load_tags
    from .match_result import load_history_keys, load_result

    path = PROCESSED_DIR / "prediction_log.parquet"
    log = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    out = finished_results(log, load_result)
    logos, tags = load_logos(), load_tags()
    for row in out["rows"]:
        # A name key logged before team-ID resolution is upgraded only to the
        # numeric ID of the same canonical side (same rule as the Match Center).
        history = load_history_keys(row["match_id"], row["team_a_key"], row["team_b_key"])
        for side, resolved in zip(("a", "b"), history):
            key = row[f"team_{side}_key"]
            row[f"logo_{side}"] = logos.get(key) or logos.get(resolved)
            row[f"tag_{side}"] = tags.get(key) or tags.get(resolved)
            row[f"team_{side}_id"] = int(resolved) if resolved.isdigit() else None
    out["note"] = ("Last forecast logged before kickoff next to the verified canonical result. "
                   "Descriptive tally, not a significance test; unverified results are not scored.")
    print(json.dumps(out, allow_nan=False))


if __name__ == "__main__":
    main()
