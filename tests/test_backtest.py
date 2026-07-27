import numpy as np
import pandas as pd

from vct_quant.eval.backtest import walk_forward_splits


def test_splits_are_temporal_and_disjoint():
    order = pd.Series(range(100))
    splits = list(walk_forward_splits(order, n_splits=5, min_train_frac=0.5))
    assert len(splits) == 5
    seen = np.zeros(100, dtype=bool)
    for train, test in splits:
        # No test row may precede any training row: that is training on the future.
        assert order[train].max() < order[test].min()
        assert not (train & test).any()
        assert not (seen & test).any()  # test windows are disjoint
        seen |= test
    # The whole post-cutoff tail is tested exactly once.
    assert seen.sum() == 50


def test_accepts_non_date_keys():
    # Kaggle match_ids: large, sparse, clumped ints — pd.to_datetime would read
    # these as nanoseconds and silently produce garbage.
    ids = pd.Series([8756, 8757, 9000, 41000, 41001, 41002, 200000, 200001])
    splits = list(walk_forward_splits(ids, n_splits=2, min_train_frac=0.5))
    assert splits
    for train, test in splits:
        assert ids[train].max() < ids[test].min()
