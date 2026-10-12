"""Retrospective temporal temperature check for the frozen three-input stack."""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research import stack_ensemble as stack


GRID = (0.70, 0.80, 0.90, 1.00, 1.10, 1.20)
COMPONENTS = ("p_elo", "p_rs", "p_ls")


def tempered_predict(x: np.ndarray, weights: np.ndarray, temperature: float) -> np.ndarray:
    """Multiply the no-intercept stack logit by a positive scalar."""
    return stack.sigmoid(temperature * (np.asarray(x) @ np.asarray(weights)))


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    z = stack.logits(p)
    return float(np.mean(np.logaddexp(0, z) - np.asarray(y) * z))


def prepared(frame: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    eligible = frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.between(2023, 2026)
    data = frame.loc[eligible].copy()
    if data.match_id.isna().any() or data.match_id.duplicated().any():
        raise ValueError("null or duplicate eligible match_id")
    x = stack.logits(data.loc[:, COMPONENTS].to_numpy(float))
    y = data.y.to_numpy(float)
    years = data.year.to_numpy(int)
    if not np.isfinite(x).all():
        raise ValueError("component logits must be finite")
    return data, x, y, years


def freeze(frame: pd.DataFrame) -> tuple[float, np.ndarray, dict[float, float], np.ndarray]:
    """Select on 2024 using a 2023 fit, then refit using 2023–24 only."""
    _, x, y, years = prepared(frame)
    train, calibration = years == 2023, years == 2024
    if not train.any() or not calibration.any():
        raise ValueError("both 2023 training and 2024 calibration rows are required")
    initial = stack.fit(x[train], y[train])
    losses = {t: log_loss(y[calibration], tempered_predict(x[calibration], initial, t)) for t in GRID}
    # Ordering is deterministic even when loss values tie exactly.
    chosen = min(GRID, key=lambda t: (losses[t], 0 if t == 1.0 else 1, abs(t - 1.0), t))
    frozen = stack.fit(x[train | calibration], y[train | calibration])
    return chosen, frozen, losses, initial


def evaluate(frame: pd.DataFrame) -> dict:
    data, x, y, years = prepared(frame)
    temperature, weights, calibration_losses, initial = freeze(frame)
    forecasts = {"calibrated": tempered_predict(x, weights, temperature),
                 "uncalibrated": stack.predict(x, weights),
                 "Elo": data.p_elo.to_numpy(float)}
    rows = {}
    for year in (2025, 2026):
        mask = years == year
        if not mask.any():
            raise ValueError(f"no eligible {year} rows")
        baseline = forecasts["Elo"][mask]
        rows[year] = {}
        for name, probabilities in forecasts.items():
            p = probabilities[mask]
            row = stack.metrics(y[mask], p, baseline)
            row["bins"] = stack.reliability(y[mask], p)
            rows[year][name] = row
    calibrated = [rows[year]["calibrated"] for year in (2025, 2026)]
    verdict = ("WIN" if all(r["t"] > 2 and r["ece"] <= r["elo_ece"] for r in calibrated)
               else "NOT PROVEN" if all(r["t"] > 0 for r in calibrated) else "REJECTED")
    return {"temperature": temperature, "weights_2023": initial, "weights": weights,
            "calibration_losses": calibration_losses, "rows": rows, "verdict": verdict}


def main() -> None:
    result = evaluate(stack.load_components())
    print("2023 weights:", np.array2string(result["weights_2023"], precision=6))
    print("2024 temperature grid log losses:", result["calibration_losses"])
    print("selected temperature:", result["temperature"])
    print("frozen 2023–24 weights:", np.array2string(result["weights"], precision=6))
    print("year model n log_loss brier accuracy paired_t_vs_Elo ECE")
    for year, models in result["rows"].items():
        for name, row in models.items():
            print(year, name, row["n"], *(f"{row[k]:.6f}" for k in
                  ("loss", "brier", "accuracy", "t", "ece")))
            print("  ten bins (index, n, mean forecast, observed win rate):", row["bins"])
        calibrated, uncalibrated = models["calibrated"], models["uncalibrated"]
        print(year, "calibration vs uncalibrated: log-loss delta",
              f"{calibrated['loss']-uncalibrated['loss']:+.6f}", "ECE delta",
              f"{calibrated['ece']-uncalibrated['ece']:+.6f}")
    print("Frozen verdict:", result["verdict"])


if __name__ == "__main__":
    main()
