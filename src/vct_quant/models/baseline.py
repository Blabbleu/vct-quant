"""Rejected comparison model: logistic calibration of pre-match Elo difference.

Raw Elo beats this model on the official Tier-1 holdout; the implementation is
kept so that result remains reproducible.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression


def train_baseline(X: np.ndarray, y: np.ndarray) -> LogisticRegression:
    model = LogisticRegression(max_iter=1000)
    model.fit(X, y)
    return model
