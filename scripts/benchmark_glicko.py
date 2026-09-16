"""Glicko vs raw Elo on the official Tier-1 holdouts.

    python scripts/benchmark_glicko.py

Protocol -- this is the lesson, not the plumbing:
* Tune Glicko's knobs (c, season_c, initial_rd) on 2024 ONLY.
* Report the single best setting on 2025, which tuning never looked at. Picking
  the best of 48 settings on a set always flatters that set; the 2025 number is
  the honest one.
* Compare with a PAIRED t-test: both models score the same matches, so test the
  per-match loss difference, not the two aggregate numbers.

Elo is the production baseline: map-share signal, K=48, Tier-2 weight 0. Glicko
gets the same signal and also ignores Tier-2 results.
"""
from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd

from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.glicko import compute_glicko
from vct_quant.features.ratings import compute_elo

TUNE_YEAR, TEST_YEAR = 2024, 2025
GRID = {"c": [0, 10, 25], "season_c": [50, 100, 150, 200], "initial_rd": [75, 100, 150, 250]}


def per_match_loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def compare(label: str, y, p_elo, p_glicko) -> None:
    loss_elo, loss_glicko = per_match_loss(y, p_elo), per_match_loss(y, p_glicko)
    diff = loss_elo - loss_glicko  # positive = Glicko better
    t = diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))
    print(f"{label}  n={len(y)}  elo={loss_elo.mean():.4f}  "
          f"glicko={loss_glicko.mean():.4f}  t={t:+.2f}")


def main() -> None:
    df = match_sequence()
    signal = margin_signal(df).to_numpy()
    elo = pd.DataFrame(compute_elo(
        zip(df.match_id, df.team_a, df.team_b, signal), k=elo_k(df.tier)
    )[0])

    tier1 = df.tier.eq(1).to_numpy()
    t1 = df[tier1]
    y = df.score_a.to_numpy()
    scored = tier1 & (y != 0.5)
    masks = {year: scored & df.year.eq(year).to_numpy() for year in (TUNE_YEAR, TEST_YEAR)}

    def run(params) -> np.ndarray:
        rows = compute_glicko(
            zip(t1.match_id, t1.year, t1.team_a, t1.team_b, signal[tier1]), **params
        )[0]
        p = np.full(len(df), np.nan)
        p[tier1] = [row["p_a_win"] for row in rows]
        return p

    results = []
    for values in product(*GRID.values()):
        params = dict(zip(GRID, values))
        p = run(params)
        m = masks[TUNE_YEAR]
        results.append((per_match_loss(y[m], p[m]).mean(), params))
    results.sort(key=lambda r: r[0])
    print(f"top settings on {TUNE_YEAR}:")
    for loss, params in results[:5]:
        print(f"  {loss:.4f}  {params}")

    best = results[0][1]
    p = run(best)
    print(f"\nbest = {best}")
    for year, m in masks.items():
        compare(str(year), y[m], elo.p_a_win.to_numpy()[m], p[m])


if __name__ == "__main__":
    main()
