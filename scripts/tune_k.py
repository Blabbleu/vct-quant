"""Tune the Elo K-factor honestly.

    python scripts/tune_k.py

Three-way split by year:
    2021-2022   train        ratings warm up here, never scored
    2023-2024   validation   tune K against this, look as often as you like
    2025        test         scored ONCE, after K is locked

Elo has no separate "fit" step — it learns as it walks the history in order. So
"training" just means the matches before the ones we score. Every K runs over
the full history; only which matches get *scored* differs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vct_quant.eval import metrics
from vct_quant.features.build import match_sequence
from vct_quant.features.ratings import DEFAULT_K, compute_elo

VALIDATION_YEARS = (2023, 2024)
TEST_YEARS = (2025,)


def predict(df: pd.DataFrame, k: float) -> np.ndarray:
    """Run Elo over the whole history at this K, return P(team_a wins) per match."""
    rows, _ = compute_elo(
        df[["match_id", "team_a", "team_b", "score_a"]].itertuples(index=False, name=None),
        k=k,
    )
    return np.array([r["p_a_win"] for r in rows])


def score(df: pd.DataFrame, p: np.ndarray, years: tuple[int, ...]) -> tuple[float, int]:
    """Log loss over the given years. Bo2 draws are excluded: they have no
    binary label. Elo still *learns* from them, they just aren't scored."""
    m = df.year.isin(years).to_numpy() & (df.score_a.to_numpy() != 0.5)
    return metrics.log_loss(df.score_a.to_numpy()[m], p[m]), int(m.sum())


def main() -> None:
    df = match_sequence()

    base, n_val = score(df, predict(df, DEFAULT_K), VALIDATION_YEARS)
    print(f"validation years {VALIDATION_YEARS}  n={n_val}")
    print(f"baseline K={DEFAULT_K:g}: log loss {base:.4f}\n")

    # ---------------------------------------------------------------------
    # YOUR TURN.
    #
    # 1. Sweep K over a range (start coarse: 4 to 128) and print each K's
    #    validation log loss. Watch the shape of the curve, not just the winner
    #    -- a flat curve means K barely matters, a sharp one means it matters a
    #    lot and you should sweep finer near the bottom.
    #
    # 2. Pick the best K. Ask yourself: is it better than the baseline by more
    #    than the noise? n=765 validation matches gives roughly +/- 0.015. An
    #    improvement smaller than that is not an improvement, it is luck.
    #
    # 3. ONLY when K is locked, uncomment the test block below and run it once.
    #    If you find yourself re-running the sweep after seeing the test number,
    #    stop -- that is how a test set quietly becomes a validation set.
    # ---------------------------------------------------------------------

    # best_k = ...
    # test_loss, n_test = score(df, predict(df, best_k), TEST_YEARS)
    # print(f"\nTEST {TEST_YEARS}  n={n_test}  K={best_k:g}: log loss {test_loss:.4f}")
    best_k, best_loss = None, float("inf")
    
    for k in range(4,129,4):
        loss,_ = score(df, predict(df, k), VALIDATION_YEARS)
        print(f"K={k:3d} log loss {loss:.4f}")
        if loss < best_loss:
            best_k, best_loss = k, loss
    print(f"\n best K = {best_k} log loss = {best_loss:.4f} (baseline {base:.4f})")        
        

if __name__ == "__main__":
    main()
