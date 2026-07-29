"""Backtest Bo3 exact-score probabilities and their calibration.

    python scripts/benchmark_exact_scores.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vct_quant import db
from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo, series_score_probabilities

SCORES = ("2-0", "2-1", "1-2", "0-2")


def predictions() -> pd.DataFrame:
    matches = match_sequence()
    con = db.connect(read_only=True)
    try:
        formats = con.execute("SELECT match_id, best_of FROM match").df()
    finally:
        con.close()

    elo = pd.DataFrame(
        compute_elo(
            zip(
                matches.match_id,
                matches.team_a,
                matches.team_b,
                margin_signal(matches),
            ),
            k=elo_k(matches.tier),
        )[0]
    )
    matches = matches.merge(
        elo[["match_id", "p_a_win"]], on="match_id", validate="one_to_one"
    ).merge(formats, on="match_id", validate="one_to_one")
    matches["score"] = (
        matches.maps_a.astype("Int64").astype(str)
        + "-"
        + matches.maps_b.astype("Int64").astype(str)
    )
    return matches.loc[
        matches.tier.eq(1)
        & matches.year.ge(2023)
        & matches.best_of.eq(3)
        & matches.score.isin(SCORES)
    ].copy()


def multiclass_brier(y: np.ndarray, probabilities: np.ndarray) -> np.ndarray:
    observed = np.eye(probabilities.shape[1])[y]
    return np.square(probabilities - observed).sum(axis=1)


def calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    frame = pd.DataFrame({"actual": y, "predicted": p})
    frame["bin"] = pd.cut(
        frame.predicted, np.linspace(0, 1, bins + 1), include_lowest=True
    )
    grouped = frame.groupby("bin", observed=True).agg(
        n=("actual", "size"),
        predicted=("predicted", "mean"),
        actual=("actual", "mean"),
    )
    return float(
        ((grouped.predicted - grouped.actual).abs() * grouped.n).sum()
        / len(frame)
    )


def evaluate(matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    model = np.array(
        [
            [series_score_probabilities(p, 3)[score] for score in SCORES]
            for p in matches.p_a_win
        ]
    )
    baseline = np.column_stack(
        [
            matches.p_a_win / 2,
            matches.p_a_win / 2,
            (1 - matches.p_a_win) / 2,
            (1 - matches.p_a_win) / 2,
        ]
    )
    y = matches.score.map({score: i for i, score in enumerate(SCORES)}).to_numpy()

    if not np.allclose(model.sum(axis=1), 1):
        raise AssertionError("exact-score probabilities do not sum to one")
    if not np.allclose(model[:, :2].sum(axis=1), matches.p_a_win):
        raise AssertionError("exact-score probabilities changed the series win chance")

    actual_p = model[np.arange(len(y)), y]
    baseline_actual_p = baseline[np.arange(len(y)), y]
    rows = []
    groups = [
        ("POOLED", np.ones(len(matches), dtype=bool)),
        ("2025+", matches.year.ge(2025).to_numpy()),
    ]
    groups += [
        (str(year), matches.year.eq(year).to_numpy())
        for year in sorted(matches.year.unique())
    ]
    for period, selected in groups:
        loss_delta = -np.log(baseline_actual_p[selected]) + np.log(
            actual_p[selected]
        )
        rows.append(
            {
                "period": period,
                "n": selected.sum(),
                "log_loss": -np.log(actual_p[selected]).mean(),
                "baseline_loss": -np.log(baseline_actual_p[selected]).mean(),
                "loss_improvement": loss_delta.mean(),
                "paired_t": loss_delta.mean()
                / (loss_delta.std(ddof=1) / np.sqrt(selected.sum())),
                "brier": multiclass_brier(y[selected], model[selected]).mean(),
                "baseline_brier": multiclass_brier(
                    y[selected], baseline[selected]
                ).mean(),
                "accuracy": (model[selected].argmax(axis=1) == y[selected]).mean(),
            }
        )

    calibration = []
    for i, score in enumerate(SCORES):
        observed = (y == i).astype(float)
        calibration.append(
            {
                "score": score,
                "n": len(y),
                "predicted": model[:, i].mean(),
                "actual": observed.mean(),
                "gap": observed.mean() - model[:, i].mean(),
                "ece": calibration_error(observed, model[:, i]),
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(calibration)


def main() -> None:
    matches = predictions()
    results, calibration = evaluate(matches)
    print("Bo3 exact-score backtest (Tier 1, 2023+)")
    print(results.to_string(index=False, float_format=lambda value: f"{value:.4f}"))
    print("\nCalibration (positive gap = underprediction)")
    print(calibration.to_string(index=False, float_format=lambda value: f"{value:.4f}"))
    print(f"\nMacro classwise ECE: {calibration.ece.mean():.4f}")


if __name__ == "__main__":
    main()
