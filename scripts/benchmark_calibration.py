"""Does shrinking Elo's probabilities toward 50% help? Calibration, done honestly.

    python scripts/benchmark_calibration.py

Elo is overconfident lately: its 65% favourites win ~58%. One number fixes the
*shape* of that:

    p' = sigmoid(a * logit(p))      a < 1 pulls toward 50%, a > 1 pushes away

But the best `a` drifts by era (computed per year, in hindsight):

    2021 2.00 | 2022 1.44 | 2023 1.10 | 2024 0.76 | 2025 0.76 | 2026 0.70

2021-22 Elo was UNDERconfident (lopsided regional qualifiers); since the 2023
partner leagues it is OVERconfident (closer parity). That is why the rejected
logistic calibration, fit on 2022-23, made 2024 worse.

Protocol: for each scored year, fit `a` on the PREVIOUS year only, apply it to
the scored year, compare to raw Elo with a paired t-test. The scored year never
touches its own `a`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo

SCORED_YEARS = (2024, 2025, 2026)


def per_match_loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def shrink(p: np.ndarray, a: float) -> np.ndarray:
    """sigmoid(a * logit(p)).

    logit(p) = log(p / (1 - p))     probability -> log-odds
    sigmoid(z) = 1 / (1 + exp(-z))  log-odds -> probability
    """
    z = np.log(p / (1 - p))
    return 1 / (1 + np.exp(-a * z))


def fit_a(y: np.ndarray, p: np.ndarray) -> float:
    """The `a` with the lowest mean log loss on (y, p).

    Grid search is fine: try np.linspace(0.3, 2.0, 171) and keep the best.
    Sanity check: fit_a on data that is already calibrated should return ~1.0.
    """
    grid = np.linspace(0.3, 2.0, 171)
    losses = [per_match_loss(y, shrink(p, a)).mean() for a in grid]
    return grid[np.argmin(losses)]


def main() -> None:
    df = match_sequence()
    elo = pd.DataFrame(compute_elo(
        zip(df.match_id, df.team_a, df.team_b, margin_signal(df).to_numpy()),
        k=elo_k(df.tier),
    )[0])
    scored = df.tier.eq(1) & df.score_a.ne(0.5)
    d = pd.DataFrame({"year": df.year, "y": df.score_a, "p": elo.p_a_win})[scored]
    years = d.year.to_numpy()
    outcomes = d.y.to_numpy()
    probabilities = d.p.to_numpy()

    for year in SCORED_YEARS:
        previous = years == year - 1
        current = years == year
        a = fit_a(outcomes[previous], probabilities[previous])
        y = outcomes[current]
        p = probabilities[current]
        raw_loss = per_match_loss(y, p)
        calibrated_loss = per_match_loss(y, shrink(p, a))
        diff = raw_loss - calibrated_loss
        t = diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))
        print(year, a, raw_loss.mean(), calibrated_loss.mean(), t)

if __name__ == "__main__":
    main()
