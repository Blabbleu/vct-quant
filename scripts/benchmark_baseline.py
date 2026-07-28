"""Reproduce the rejected logistic calibration experiment on Tier 1.

    python scripts/benchmark_baseline.py

Train on 2022-2023 and score 2024. The year split is fixed deliberately: tuning
against 2024 and then reporting 2024 again would turn the holdout into training.
"""
from __future__ import annotations

import numpy as np

from vct_quant.eval import metrics
from vct_quant.features.build import build_features
from vct_quant.models.baseline import train_baseline

TRAIN_YEARS = (2022, 2023)
TEST_YEAR = 2024


def main() -> None:
    df = build_features()
    train = df.year.isin(TRAIN_YEARS) & df.tier.eq(1)
    test = df.year.eq(TEST_YEAR) & df.tier.eq(1)

    model = train_baseline(
        df.loc[train, ["elo_diff"]].to_numpy(),
        df.loc[train, "label"].to_numpy(),
    )
    y = df.loc[test, "label"].to_numpy()
    p = model.predict_proba(df.loc[test, ["elo_diff"]].to_numpy())[:, 1]
    elo = df.loc[test, "elo_p_a_win"].to_numpy()

    logistic_loss = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    elo_loss = -(y * np.log(elo) + (1 - y) * np.log(1 - elo))
    improvement = elo_loss - logistic_loss
    paired_t = improvement.mean() / (improvement.std(ddof=1) / np.sqrt(len(y)))

    print(f"train={TRAIN_YEARS} n={train.sum():,}  test={TEST_YEAR} n={test.sum():,}")
    print(
        f"logistic  log loss={metrics.log_loss(y, p):.4f}"
        f"  brier={metrics.brier_score(y, p):.4f}"
    )
    print(
        f"raw Elo   log loss={metrics.log_loss(y, elo):.4f}"
        f"  brier={metrics.brier_score(y, elo):.4f}"
    )
    print(f"paired improvement={improvement.mean():.4f}  t={paired_t:.2f}")
    print(metrics.calibration_table(y, p).to_string(index=False))


if __name__ == "__main__":
    main()
