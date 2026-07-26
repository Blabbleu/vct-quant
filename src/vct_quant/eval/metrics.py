"""Probability-forecast metrics: what a prediction quant model lives and dies by.

Accuracy is a poor target for match prediction — favorites winning 60% of the
time makes 60% accuracy trivial. Optimize log loss / Brier and check the
calibration table: a bucket predicted at 70% should win ~70% of the time.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def brier_score(y_true: np.ndarray, p: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=float)
    p = np.asarray(p, dtype=float)
    return float(np.mean((p - y_true) ** 2))


def log_loss(y_true: np.ndarray, p: np.ndarray, eps: float = 1e-15) -> float:
    y_true = np.asarray(y_true, dtype=float)
    p = np.clip(np.asarray(p, dtype=float), eps, 1.0 - eps)
    return float(-np.mean(y_true * np.log(p) + (1.0 - y_true) * np.log(1.0 - p)))


def calibration_table(y_true: np.ndarray, p: np.ndarray, bins: int = 10) -> pd.DataFrame:
    df = pd.DataFrame({"y": np.asarray(y_true, dtype=float), "p": np.asarray(p, dtype=float)})
    df["bucket"] = pd.cut(df["p"], np.linspace(0.0, 1.0, bins + 1), include_lowest=True)
    out = df.groupby("bucket", observed=True).agg(
        n=("y", "size"), predicted=("p", "mean"), actual=("y", "mean")
    )
    return out.reset_index()
