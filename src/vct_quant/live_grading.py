"""Shared eligibility gate for the live holdout and desk's graded record.

The Match Center's two-sided canonical verification is the source of truth for
finished results. A one-sided team-name match is not enough to score a call.
This reads the canonical DB only; it never fits or changes a forecast.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from .match_result import load_result

Loader = Callable[[int, str, str, float], dict | None]


def graded_forecasts(log: pd.DataFrame, load: Loader = load_result) -> pd.DataFrame:
    """Last strictly pre-scheduled-start row per match with a verified winner.

    Preserve all logged fields (including shadow probabilities) and attach y.
    An unverified/ambiguous result is excluded, not treated as a loss. The
    original scheduled date is also checked against the completion day: a
    later DB reschedule cannot validate a post-result logged prediction.
    """
    if log.empty:
        out = log.copy()
        out.attrs["logged"] = 0
        return out
    pre = log.copy()
    pre["predicted_at"] = pd.to_datetime(pre.predicted_at, utc=True, errors="coerce")
    pre["scheduled_at"] = pd.to_datetime(pre.scheduled_at, utc=True, errors="coerce")
    p = pd.to_numeric(pre["p_team_a_win"], errors="coerce")
    pre = pre.loc[pre.predicted_at.lt(pre.scheduled_at) & p.between(0, 1)].copy()
    last = pre.sort_values("predicted_at").groupby("match_id").tail(1)
    latest = pre.merge(last[["match_id", "predicted_at"]], on=["match_id", "predicted_at"])
    conflicting = set(latest.groupby("match_id").filter(
        lambda rows: len(rows[["team_a_key", "team_b_key", "scheduled_at",
                               "p_team_a_win"]].drop_duplicates()) > 1
    ).match_id)
    winners: dict[int, int] = {}
    for row in last.itertuples():
        if row.match_id in conflicting:
            continue
        result = load(int(row.match_id), str(row.team_a_key), str(row.team_b_key),
                      float(row.p_team_a_win))
        if not result or result.get("status") != "verified" or result.get("winner") not in ("a", "b"):
            continue
        completed = pd.to_datetime(result.get("completed_on"), utc=True, errors="coerce")
        if pd.isna(completed) or completed.normalize() < row.scheduled_at.normalize():
            continue
        winners[int(row.match_id)] = int(result["winner"] == "a")
    scored = last.loc[last.match_id.isin(winners)].copy()
    scored["y"] = scored.match_id.map(winners).astype(int)
    scored.attrs["logged"] = len(last)
    return scored
