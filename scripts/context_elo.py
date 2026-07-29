"""Test whether match context deserves a different Elo K-factor.

    python scripts/context_elo.py

Tune on 2023-24, then check the untouched 2025 and partial-2026 periods.
Production changes require a consistent gain with paired |t| > 2.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vct_quant import db
from vct_quant.features.build import BEST_K, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo


def international_event(names: pd.Series) -> pd.Series:
    """The global events; avoid the regional 2021 events also named Masters."""
    return names.str.lower().str.match(
        r"^(valorant champions [0-9]{4}$"
        r"|valorant champions tour stage .*masters"
        r"|valorant masters "
        r"|champions tour [0-9]{4}: (masters|lock//in))"
    )


def predictions(df: pd.DataFrame, multiplier: np.ndarray) -> np.ndarray:
    k = np.where(df.tier.eq(1), BEST_K * multiplier, 0.0)
    rows, _ = compute_elo(
        zip(df.match_id, df.team_a, df.team_b, margin_signal(df)),
        k=k,
    )
    return np.array([row["p_a_win"] for row in rows])


def score(
    df: pd.DataFrame,
    baseline: np.ndarray,
    candidate: np.ndarray,
    years: tuple[int, ...],
) -> tuple[float, float, float]:
    y = df.score_a.to_numpy()
    mask = df.tier.eq(1).to_numpy() & (y != 0.5) & df.year.isin(years).to_numpy()
    y, p0, p = y[mask], baseline[mask], candidate[mask]
    base_loss = -(y * np.log(p0) + (1 - y) * np.log(1 - p0))
    loss = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    improvement = base_loss - loss
    std = improvement.std(ddof=1)
    t = improvement.mean() / (std / np.sqrt(len(improvement))) if std else 0.0
    return float(loss.mean()), float(improvement.mean()), float(t)


def main() -> None:
    # One runnable guard against accidentally classifying regional Masters events
    # as international and invalidating the comparison.
    sample = pd.Series([
        "Valorant Champions 2025",
        "Champions Tour 2024: Masters Madrid",
        "Champions Tour Brazil Stage 1: Masters",
    ])
    assert international_event(sample).tolist() == [True, True, False]

    df = match_sequence()
    con = db.connect(read_only=True)
    try:
        context = con.execute("""
            SELECT match_id, coalesce(event_name, '') AS event_name,
                   coalesce(event_series, '') AS event_series
            FROM match
        """).df()
    finally:
        con.close()
    df = df.merge(context, on="match_id", how="left")

    international = international_event(df.event_name)
    playoffs = df.event_series.str.lower().str.contains(
        "playoff|bracket|main event", regex=True
    )
    showmatch = df.event_series.str.lower().eq("showmatch")
    one = np.ones(len(df))
    variants = {
        "baseline": one,
        "no showmatches": np.where(showmatch, 0.0, 1.0),
        "playoffs 1.25x": np.where(playoffs, 1.25, 1.0),
        "international 1.25x": np.where(international, 1.25, 1.0),
        "tiered": np.select(
            [showmatch, international & playoffs, international, playoffs],
            [0.0, 1.25, 1.10, 1.10],
            default=1.0,
        ),
    }
    forecasts = {name: predictions(df, weight) for name, weight in variants.items()}

    for label, years in (
        ("validation", (2023, 2024)),
        ("test", (2025,)),
        ("confirmation", (2026,)),
    ):
        print(f"\n{label}: {', '.join(map(str, years))}")
        print(f"{'variant':24} {'log loss':>10} {'improvement':>12} {'paired t':>9}")
        for name, forecast in forecasts.items():
            loss, improvement, t = score(df, forecasts["baseline"], forecast, years)
            print(f"{name:24} {loss:10.6f} {improvement:+12.6f} {t:+9.2f}")


if __name__ == "__main__":
    main()
