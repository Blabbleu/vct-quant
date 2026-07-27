"""Walk-forward Elo benchmark — the number every later model must beat.

    python scripts/benchmark_elo.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vct_quant.eval import metrics
from vct_quant.eval.backtest import walk_forward_splits
from vct_quant.features.build import margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo

BEST_K = 48.0


def main(n_splits: int = 5) -> None:
    df = match_sequence()
    # The winning configuration, found by scripts/margin_elo.py and tune_k.py on a
    # 2023-24 validation holdout: feed Elo the *share of maps won* rather than a
    # binary win, at K=48. A 2-1 win by a heavy favourite then scores below its
    # own expectation and costs that team rating -- plain Elo cannot express that.
    # Round-level share and margin-weighted K were both tried and both lost.
    signal = margin_signal(df).to_numpy()
    elo = pd.DataFrame(
        compute_elo(zip(df.match_id, df.team_a, df.team_b, signal), k=BEST_K)[0]
    )
    y_all = df.score_a.to_numpy()
    # Bo2 draws carry no binary label; Elo still learns from them (score 0.5),
    # they are only excluded from scoring.
    binary = y_all != 0.5

    ys, ps = [], []
    for i, (_, test) in enumerate(walk_forward_splits(elo.match_id, n_splits=n_splits)):
        m = test & binary
        y, p = y_all[m], elo.p_a_win.to_numpy()[m]
        ys.append(y)
        ps.append(p)
        print(
            f"fold{i}  n={m.sum():5d}  log loss={metrics.log_loss(y, p):.4f}"
            f"  brier={metrics.brier_score(y, p):.4f}"
            f"  acc={((p > 0.5) == (y > 0.5)).mean():.3f}"
        )

    y, p = np.concatenate(ys), np.concatenate(ps)
    print(
        f"\nPOOLED  n={len(y)}  log loss={metrics.log_loss(y, p):.4f}"
        f"  brier={metrics.brier_score(y, p):.4f}"
        f"  acc={((p > 0.5) == (y > 0.5)).mean():.3f}"
    )
    print(f"coin flip log loss={metrics.log_loss(y, np.full(len(y), 0.5)):.4f}\n")
    print(metrics.calibration_table(y, p).to_string(index=False))


if __name__ == "__main__":
    main()
