"""Descriptive progress toward the pre-registered shadow promotion rule.

The rule lives in `docs/model-lab-2026-09-24.md` section 3 and is fixed; this
module only *reports* where the live log stands against it. It never promotes
anything: promotion changes the primary forecast and needs the owner's approval.

Scores are same-row comparisons: a shadow is judged only on graded matches whose
last pre-start forecast carried both Elo and that shadow.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .event_bracket import load_bracket_spec

CHAMPIONS_2026_EVENT = 2766
CHECKPOINT_1_MIN_N = 25
CHECKPOINT_2_N = 300
# Differences this close to zero print as 0.0000 in the grader; the rule's
# "difference <= 0.0000" is ambiguous there, so the owner decides.
BOUNDARY = 0.00005


def per_match_loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-12, 1 - 1e-12)
    y = np.asarray(y, dtype=float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def paired_t(diff: np.ndarray) -> float | None:
    """Mean over its standard error; None when it cannot be computed."""
    diff = np.asarray(diff, dtype=float)
    if len(diff) < 2:
        return None
    sd = diff.std(ddof=1)
    return float(diff.mean() / (sd / np.sqrt(len(diff)))) if sd > 0 else 0.0


def grand_final_id(event_id: int = CHAMPIONS_2026_EVENT) -> int:
    spec = load_bracket_spec(event_id)
    finals = [s["match_id"] for s in spec["playoffs"] if s["stage"] == "Grand Final"]
    if len(finals) != 1:
        raise ValueError("bracket spec must pin exactly one Grand Final")
    return int(finals[0])


def _verdict(n: int, diff: float) -> str:
    if n < CHECKPOINT_1_MIN_N:
        return "too_few"
    if diff <= 0:
        return "no_worse"
    if diff < BOUNDARY:
        return "boundary"
    return "worse"


def checkpoint_status(scored: pd.DataFrame, final_id: int,
                      column: str = "p_team_a_win_ensemble") -> dict:
    """Where the ensemble stands against checkpoints 1 and 2.

    `scored` needs match_id, scheduled_at, y, p_team_a_win and `column`.
    Checkpoint 1 is scored on forecasts scheduled no later than the graded
    grand final, so matches played after it cannot move that verdict.
    """
    if column not in scored:
        scored = scored.assign(**{column: np.nan})
    rows = scored[scored[column].notna()]
    out: dict = {"min_n": CHECKPOINT_1_MIN_N, "checkpoint_2_n": CHECKPOINT_2_N,
                 "final_match_id": int(final_id), "n": int(len(rows))}
    final = rows[rows.match_id.eq(final_id)]
    out["final_graded"] = bool(len(final))
    if len(final):
        cutoff = final.scheduled_at.max()
        cohort = rows[rows.scheduled_at <= cutoff]
    else:
        cohort = rows
    y = cohort.y.to_numpy()
    diff = per_match_loss(y, cohort[column].to_numpy()) - per_match_loss(y, cohort.p_team_a_win.to_numpy())
    out["checkpoint_1"] = {
        "n": int(len(cohort)),
        "diff": float(diff.mean()) if len(diff) else None,  # shadow minus Elo; negative = shadow better
        "t": paired_t(-diff),                                 # positive = shadow better
        "state": ("final_graded" if len(final) else "awaiting_final"),
        "verdict": _verdict(len(cohort), float(diff.mean())) if len(diff) else "too_few",
    }
    out["checkpoint_2"] = {"n": int(len(rows)), "reached": bool(len(rows) >= CHECKPOINT_2_N)}
    return out
