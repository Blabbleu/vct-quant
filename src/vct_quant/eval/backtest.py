"""Walk-forward validation.

Never randomly split match data: teams' strength is autocorrelated, and a
random split trains on the future to predict the past. Always evaluate by
training on everything before a cutoff and predicting the window after it.
"""
from __future__ import annotations

from typing import Iterator

import numpy as np
import pandas as pd


def walk_forward_splits(
    dates: pd.Series, n_splits: int = 5, min_train_frac: float = 0.5
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield (train_mask, test_mask) boolean arrays over `dates`.

    The first min_train_frac of the timeline is always training data; the
    remainder is cut into n_splits consecutive test windows, each trained on
    all data strictly before it.
    """
    dates = pd.to_datetime(dates)
    t0, t1 = dates.min(), dates.max()
    start = t0 + (t1 - t0) * min_train_frac
    cuts = pd.date_range(start=start, end=t1, periods=n_splits + 1)
    for lo, hi in zip(cuts[:-1], cuts[1:]):
        train = (dates < lo).to_numpy()
        test = ((dates >= lo) & (dates <= hi)).to_numpy()
        if train.any() and test.any():
            yield train, test
