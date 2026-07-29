"""Test shrinking team Elo when its known lineup changes.

    python scripts/roster_elo.py

Tune on 2023-24, then check 2025 and partial 2026 untouched. Current-match
lineups are pre-match information; missing roster data means no adjustment.
"""
from __future__ import annotations

import numpy as np

from vct_quant import db
from vct_quant.features.build import _roster_churn, margin_signal, match_sequence
from vct_quant.features.ratings import DEFAULT_BASE, compute_elo, expected_score, update

ALPHAS = (0.025, 0.05, 0.075, 0.10, 0.25, 0.50, 0.75, 1.0)
K_VALUES = (40.0, 44.0, 48.0, 52.0, 56.0, 60.0, 64.0)


def predictions(df, churn, alpha: float, k: float) -> np.ndarray:
    """Regress rating toward 1500 in proportion to changed lineup share."""
    churn = churn.fillna(0.0)
    signal = margin_signal(df)
    ratings: dict = {}
    out = []
    for row, score, churn_a, churn_b in zip(
        df.itertuples(index=False), signal, churn.churn_a, churn.churn_b
    ):
        rating_a = ratings.get(row.team_a, DEFAULT_BASE)
        rating_b = ratings.get(row.team_b, DEFAULT_BASE)
        match_k = k if row.tier == 1 else 0.0
        if match_k:
            rating_a = DEFAULT_BASE + (rating_a - DEFAULT_BASE) * (1 - alpha * churn_a)
            rating_b = DEFAULT_BASE + (rating_b - DEFAULT_BASE) * (1 - alpha * churn_b)
        out.append(expected_score(rating_a, rating_b))
        ratings[row.team_a], ratings[row.team_b] = update(
            rating_a, rating_b, score, match_k
        )
    return np.asarray(out)


def losses(df, forecast: np.ndarray, years: tuple[int, ...]) -> np.ndarray:
    y = df.score_a.to_numpy()
    mask = df.tier.eq(1).to_numpy() & (y != 0.5) & df.year.isin(years).to_numpy()
    y, forecast = y[mask], forecast[mask]
    return -(y * np.log(forecast) + (1 - y) * np.log(1 - forecast))


def main() -> None:
    con = db.connect(read_only=True)
    try:
        df = match_sequence(con)
        churn = _roster_churn(df, con)
    finally:
        con.close()

    baseline = predictions(df, churn, 0.0, 48.0)
    existing = compute_elo(
        zip(df.match_id, df.team_a, df.team_b, margin_signal(df)),
        k=np.where(df.tier.eq(1), 48.0, 0.0),
    )[0]
    assert np.allclose(baseline, [row["p_a_win"] for row in existing])

    validation = (2023, 2024)
    candidates = [
        (losses(df, forecast, validation).mean(), alpha, k, forecast)
        for alpha in ALPHAS
        for k in K_VALUES
        for forecast in [predictions(df, churn, alpha, k)]
    ]
    _, alpha, k, candidate = min(candidates, key=lambda row: row[0])
    print(f"selected on 2023-24: alpha={alpha:g}, K={k:g}\n")
    print(f"{'period':14} {'coverage':>9} {'baseline':>10} {'roster':>10} {'improvement':>12} {'paired t':>9}")
    for label, years in (
        ("validation", validation),
        ("test 2025", (2025,)),
        ("confirm 2026", (2026,)),
    ):
        in_period = df.tier.eq(1) & df.year.isin(years)
        coverage = churn.loc[in_period].notna().to_numpy().mean()
        base_loss = losses(df, baseline, years)
        roster_loss = losses(df, candidate, years)
        improvement = base_loss - roster_loss
        t = improvement.mean() / (
            improvement.std(ddof=1) / np.sqrt(len(improvement))
        )
        print(
            f"{label:14} {coverage:9.1%} {base_loss.mean():10.6f}"
            f" {roster_loss.mean():10.6f} {improvement.mean():+12.6f} {t:+9.2f}"
        )


if __name__ == "__main__":
    main()
