"""Shadow models: logged next to production Elo, never shown as the forecast.

Candidates that passed the backtest but not the ship bar (a consistent paired
gain with t > 2) are graded here on live matches, the only holdout never used for
model selection. `scripts/grade_predictions.py` scores them against Elo.

Settings were fixed in advance on 2023-24 validation (docs/model-lab-2026-09-24.md).
Do not retune them against the live log. That would turn the last clean test
into another tuning set.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..features.ratings import DEFAULT_BASE, compute_elo, expected_score

# Fast/slow Elo blend in logit space: slow tracks the organisation, fast tracks
# current form. This is the 2023-24 validation pick from scripts/ensemble_robustness.py.
# Backtest: walk-forward 0.6488 vs 0.6567; held-out 2025+26 paired t = +1.70.
ENSEMBLE: tuple[tuple[float, float], ...] = ((16.0, 0.7), (256.0, 0.3))

# Online shrink p' = sigmoid(a * logit(p)), with `a` refit on the trailing N scored
# Tier-1 production forecasts. Held-out 2025+26 t = +1.21 (scripts/model_lab.py).
CALIBRATION_WINDOW = 500
_A_GRID = np.linspace(0.4, 1.6, 61)


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def _replay(history: pd.DataFrame, k: float) -> dict:
    from ..features.build import margin_signal

    # Same pool as production: Tier-1 results only (Tier-2 at weight 0).
    ks = history.tier.map({1: k}).fillna(0.0)
    return compute_elo(
        zip(history.match_id, history.team_a, history.team_b, margin_signal(history)),
        k=ks,
    )[1]


def ensemble_probability(fixtures: pd.DataFrame, history: pd.DataFrame) -> pd.Series:
    """P(team A wins) from the fast/slow blend, for official-pool fixtures."""
    z = np.zeros(len(fixtures))
    for k, weight in ENSEMBLE:
        ratings = _replay(history, k)
        p = [
            expected_score(ratings.get(a, DEFAULT_BASE), ratings.get(b, DEFAULT_BASE))
            for a, b in zip(fixtures.team_a_key, fixtures.team_b_key)
        ]
        z += weight * _logit(p)
    return pd.Series(_sigmoid(z), index=fixtures.index)


def fit_shrink(y: np.ndarray, p: np.ndarray) -> float:
    """The `a` minimizing log loss of sigmoid(a * logit(p)); 1.0 means no change."""
    if len(y) == 0:
        return 1.0
    z = _logit(p)
    y = np.asarray(y, dtype=float)
    losses = []
    for a in _A_GRID:
        q = np.clip(_sigmoid(a * z), 1e-12, 1 - 1e-12)
        losses.append(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))
    return float(_A_GRID[int(np.argmin(losses))])


def calibration_a(history: pd.DataFrame, production_p: np.ndarray) -> float:
    """`a` fitted on the trailing CALIBRATION_WINDOW scored Tier-1 matches."""
    scored = history.tier.eq(1).to_numpy() & history.score_a.ne(0.5).to_numpy()
    y = history.score_a.to_numpy()[scored][-CALIBRATION_WINDOW:]
    p = np.asarray(production_p)[scored][-CALIBRATION_WINDOW:]
    return fit_shrink(y, p)


def calibrated_probability(p: pd.Series, a: float) -> pd.Series:
    return pd.Series(_sigmoid(a * _logit(p)), index=p.index)


def shadow_columns(
    fixtures: pd.DataFrame, history: pd.DataFrame, production_p: np.ndarray
) -> pd.DataFrame:
    """Add p_team_a_win_ensemble and p_team_a_win_calibrated to official fixtures."""
    out = fixtures.copy()
    if out.empty or history.empty:
        out["p_team_a_win_ensemble"] = math.nan
        out["p_team_a_win_calibrated"] = math.nan
        return out
    out["p_team_a_win_ensemble"] = ensemble_probability(out, history)
    a = calibration_a(history, production_p)
    out["calibration_a"] = a
    out["p_team_a_win_calibrated"] = calibrated_probability(out.p_team_a_win, a)
    return out
