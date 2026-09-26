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


def eligible_pre_start(log: pd.DataFrame) -> pd.DataFrame:
    """Conservative cutoff: use the earliest logged kickoff for each match.

    A later feed may reschedule a match; without an actual kickoff timestamp we
    cannot prove that a newly logged prediction after the original kickoff was
    pre-match. Preserve the earlier eligible call instead of rehabilitating it.
    """
    rows = log.copy()
    rows["predicted_at"] = pd.to_datetime(rows.predicted_at, utc=True, errors="coerce")
    rows["scheduled_at"] = pd.to_datetime(rows.scheduled_at, utc=True, errors="coerce")
    first_start = rows.groupby("match_id")["scheduled_at"].transform("min")
    rows["p_team_a_win"] = pd.to_numeric(rows["p_team_a_win"], errors="coerce")
    return rows.loc[rows.predicted_at.lt(rows.scheduled_at)
                    & rows.predicted_at.lt(first_start)
                    & rows["p_team_a_win"].between(0, 1)].copy()


def latest_unambiguous(pre: pd.DataFrame) -> tuple[pd.DataFrame, set]:
    """Select last eligible calls; flag tied, contradictory scoring payloads.

    A duplicate timestamp with a different shadow or market quote must not
    score an arbitrary row depending on parquet order. Compare only inputs to
    grading/display, rather than irrelevant raw metadata or fetch provenance.
    """
    last = pre.sort_values("predicted_at").groupby("match_id").tail(1)
    latest = pre.merge(last[["match_id", "predicted_at"]], on=["match_id", "predicted_at"])
    fields = ["team_a_key", "team_b_key", "scheduled_at", "tier", "best_of",
              "p_market_a", "market_spread", "market_volume"]
    fields += [c for c in pre if c.startswith(("p_", "elo"))]
    fields = [c for c in dict.fromkeys(fields) if c in latest]
    conflicting = set(latest.groupby("match_id").filter(
        lambda rows: len(rows[fields].drop_duplicates()) > 1
    ).match_id)
    return last, conflicting


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
    pre = eligible_pre_start(log)
    last, conflicting = latest_unambiguous(pre)
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
