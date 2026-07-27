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
    order: pd.Series, n_splits: int = 5, min_train_frac: float = 0.5
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield (train_mask, test_mask) boolean arrays over any sortable key.

    `order` is dates where they exist, and ascending vlr.gg match_id for the
    Kaggle corpus, which carries no date column at all. Cuts are by rank, not
    by value, so the key only has to be comparable — and every test window
    holds the same number of matches regardless of how clumped the key is.

    The first min_train_frac of the timeline is always training data; the
    remainder is cut into n_splits consecutive test windows, each trained on
    all data strictly before it.
    """
    # ponytail: rank ties broken by row position; matches on the same day (or
    # sharing a match_id, which cannot happen — it is a PK) land in whichever
    # window their row order puts them.
    rank = pd.Series(order).rank(method="first").to_numpy()
    cuts = np.linspace(len(rank) * min_train_frac, len(rank), n_splits + 1)
    for lo, hi in zip(cuts[:-1], cuts[1:]):
        train = rank <= lo
        test = (rank > lo) & (rank <= hi)
        if train.any() and test.any():
            yield train, test
