"""Does margin of victory help? A 2-0 and a 2-1 are the same to plain Elo.

    python scripts/margin_elo.py

The trick: `compute_elo` reads the score out of the tuples you give it, so a
fractional training signal needs no library change. What must NOT change is the
evaluation label -- we are still predicting *who wins*, so log loss is always
scored against the binary df.score_a. Score against fractional labels and the
number will look better while measuring a different task.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vct_quant.eval import metrics
from vct_quant.features.build import match_sequence
from vct_quant.features.ratings import DEFAULT_K, compute_elo

VALIDATION_YEARS = (2023, 2024)


def predict(df: pd.DataFrame, train_score: np.ndarray, k: float = DEFAULT_K) -> np.ndarray:
    """Run Elo using `train_score` as the learning signal, one value per match.

    Pass df.score_a for plain Elo, or a margin-aware signal to test this idea.
    """
    tuples = zip(df.match_id, df.team_a, df.team_b, train_score)
    rows, _ = compute_elo(tuples, k=k)
    return np.array([r["p_a_win"] for r in rows])


def evaluate(df: pd.DataFrame, p: np.ndarray, label: str, baseline: np.ndarray | None = None):
    """Log loss on the validation years, always against the BINARY label."""
    m = df.year.isin(VALIDATION_YEARS).to_numpy() & (df.score_a.to_numpy() != 0.5)
    y, pv = df.score_a.to_numpy()[m], p[m]
    per_match = -np.log(np.where(y > 0.5, pv, 1 - pv))
    out = f"{label:28} log loss {per_match.mean():.4f}"
    if baseline is not None:
        # Paired: both models saw the same matches, so compare match by match.
        d = baseline - per_match
        t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
        out += f"   diff {d.mean():+.4f}  t={t:+.2f}{'  SIGNIFICANT' if abs(t) > 2 else ''}"
    print(out)
    return per_match


def main() -> None:
    df = match_sequence()
    base = evaluate(df, predict(df, df.score_a.to_numpy()), "plain Elo (baseline)")

    # ---------------------------------------------------------------------
    # YOUR TURN. Build a margin-aware training signal and evaluate it:
    #
    #     evaluate(df, predict(df, my_signal), "variant A", baseline=base)
    #
    # Variant A -- fractional score:  maps_a / (maps_a + maps_b)
    #     2-0 -> 1.00, 2-1 -> 0.67, 1-2 -> 0.33
    #
    # Variant B -- keep the score binary, scale K by the map margin instead.
    #     Needs predict() to take a per-match k, which compute_elo does not
    #     support. Try A first; only build that if A shows promise.
    #
    # The design question, and it is a real one: 1,708 Bo1 matches are recorded
    # 1-0. Under variant A that feeds 1.0 -- scored as dominant as a 2-0 sweep,
    # which it plainly is not. Decide what to do with them and be able to say
    # why. There is no clean answer, only tradeoffs.
    #
    # Judge by t, not by whether the loss went down. t > 2 or it did not happen.
    # ---------------------------------------------------------------------
    signal = df.maps_a / (df.maps_a + df.maps_b)
    evaluate(df, predict(df, signal.to_numpy()), "variant A: fractional", baseline=base)
    
    margin = (df.maps_a - df.maps_b).abs()
    weights = BASE_K * (1 + alpha * (margin - 1))      # your call what this looks like
    evaluate(df, predict(df, binary, k=weights.to_numpy()), "B: weighted K", baseline=base)


if __name__ == "__main__":
    main()
