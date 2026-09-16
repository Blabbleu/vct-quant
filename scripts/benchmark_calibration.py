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
    # TODO (you): two lines.
    raise NotImplementedError


def fit_a(y: np.ndarray, p: np.ndarray) -> float:
    """The `a` with the lowest mean log loss on (y, p).

    Grid search is fine: try np.linspace(0.3, 2.0, 171) and keep the best.
    Sanity check: fit_a on data that is already calibrated should return ~1.0.
    """
    # TODO (you)
    raise NotImplementedError


def main() -> None:
    df = match_sequence()
    elo = pd.DataFrame(compute_elo(
        zip(df.match_id, df.team_a, df.team_b, margin_signal(df).to_numpy()),
        k=elo_k(df.tier),
    )[0])
    scored = df.tier.eq(1) & df.score_a.ne(0.5)
    d = pd.DataFrame({"year": df.year, "y": df.score_a, "p": elo.p_a_win})[scored]

    # TODO (you): for each year in SCORED_YEARS
    #   1. take last year's rows, a = fit_a(their y, their p)
    #   2. take this year's rows, p_cal = shrink(their p, a)
    #   3. diff = per_match_loss(y, p) - per_match_loss(y, p_cal)   (positive = calibration helps)
    #      t = diff.mean() / (diff.std(ddof=1) / sqrt(n))
    #   4. print year, a, raw loss, calibrated loss, t


if __name__ == "__main__":
    main()
