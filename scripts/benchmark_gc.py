"""Game Changers: its own Elo pool, its own K.

    python scripts/benchmark_gc.py

GC teams never meet Tier-1 teams, so GC is a separate pool
(`match_sequence(tiers=(3,))`). Tier 1's K=48 was tuned for Tier 1's spread
of team strength; the GC pool looks different (open qualifiers full of one-off
teams that lose every match), so K must be retuned -- CLAUDE.md: "Retune K
whenever the training signal changes."

Protocol, same as always: tune K on years <= TUNE_THROUGH, then score
2025-2026 ONCE at the chosen K, paired against the untuned K=48.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vct_quant.eval import metrics
from vct_quant.features.build import margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo

TUNE_THROUGH = 2024
K_GRID = [16, 24, 32, 48, 64, 96, 128, 192, 256, 384]


def per_match_loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def paired_t(loss_base: np.ndarray, loss_new: np.ndarray) -> float:
    diff = loss_base - loss_new  # positive = new is better
    return diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))


def main() -> None:
    df = match_sequence(tiers=(3,))
    signal = margin_signal(df).to_numpy()
    y = df.score_a.to_numpy()
    scored = y != 0.5
    tune = scored & df.year.le(TUNE_THROUGH).to_numpy()
    test = scored & df.year.gt(TUNE_THROUGH).to_numpy()
    print(f"GC matches: {len(df):,}  tune n={tune.sum():,}  test n={test.sum():,}")

    def probabilities(k: float) -> np.ndarray:
        rows = compute_elo(zip(df.match_id, df.team_a, df.team_b, signal), k=k)[0]
        return np.array([row["p_a_win"] for row in rows])

    # TODO (you):
    #   1. for each k in K_GRID: mean per_match_loss on `tune`; print it
    #   2. best_k = the k with the lowest tune loss
    #   3. on `test`: loss at best_k vs loss at k=48, print both and paired_t
    #   4. print metrics.calibration_table(y[test], p_best[test])
    # Then ask: is GC Elo better or worse calibrated than Tier 1's, and why?


if __name__ == "__main__":
    main()
