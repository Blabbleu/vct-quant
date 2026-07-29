"""Test point-in-time-safe recency decay for Elo.

    python scripts/recency_elo.py

Dates are unavailable, so half-life is measured in each team's Tier-1 match
appearances. Tune on 2023-24, then check 2025 and partial 2026 untouched.
"""
from __future__ import annotations

import numpy as np

from vct_quant.features.build import margin_signal, match_sequence
from vct_quant.features.ratings import DEFAULT_BASE, compute_elo, expected_score, update

HALF_LIVES = (40, 80, 160, 320, 640)
K_VALUES = (40.0, 48.0, 56.0, 64.0)


def predictions(df, half_life: int | None, k: float) -> np.ndarray:
    """Decay old rating evidence once per subsequent Tier-1 appearance."""
    carry = 1.0 if half_life is None else 0.5 ** (1.0 / half_life)
    ratings: dict = {}
    out = []
    for row, score in zip(df.itertuples(index=False), margin_signal(df)):
        rating_a = ratings.get(row.team_a, DEFAULT_BASE)
        rating_b = ratings.get(row.team_b, DEFAULT_BASE)
        match_k = k if row.tier == 1 else 0.0
        if match_k:
            rating_a = DEFAULT_BASE + carry * (rating_a - DEFAULT_BASE)
            rating_b = DEFAULT_BASE + carry * (rating_b - DEFAULT_BASE)
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
    df = match_sequence()
    baseline = predictions(df, None, 48.0)
    existing = compute_elo(
        zip(df.match_id, df.team_a, df.team_b, margin_signal(df)),
        k=np.where(df.tier.eq(1), 48.0, 0.0),
    )[0]
    assert np.allclose(baseline, [row["p_a_win"] for row in existing])

    validation = (2023, 2024)
    candidates = [
        (losses(df, forecast, validation).mean(), half_life, k, forecast)
        for half_life in HALF_LIVES
        for k in K_VALUES
        for forecast in [predictions(df, half_life, k)]
    ]
    _, half_life, k, candidate = min(candidates, key=lambda row: row[0])
    print(f"selected on 2023-24: half-life={half_life} matches, K={k:g}\n")
    print(f"{'period':14} {'baseline':>10} {'decay':>10} {'improvement':>12} {'paired t':>9}")
    for label, years in (
        ("validation", validation),
        ("test 2025", (2025,)),
        ("confirm 2026", (2026,)),
    ):
        base_loss = losses(df, baseline, years)
        decay_loss = losses(df, candidate, years)
        improvement = base_loss - decay_loss
        t = improvement.mean() / (
            improvement.std(ddof=1) / np.sqrt(len(improvement))
        )
        print(
            f"{label:14} {base_loss.mean():10.6f} {decay_loss.mean():10.6f}"
            f" {improvement.mean():+12.6f} {t:+9.2f}"
        )


if __name__ == "__main__":
    main()
