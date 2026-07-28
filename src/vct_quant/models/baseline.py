"""Baseline model: logistic calibration of the pre-match Elo difference.

This is the benchmark every fancier model must beat on walk-forward log loss
and calibration — in esports prediction, well-tuned Elo is hard to beat.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression


def train_baseline(X: np.ndarray, y: np.ndarray) -> LogisticRegression:
    model = LogisticRegression(max_iter=1000)
    model.fit(X, y)
    return model
