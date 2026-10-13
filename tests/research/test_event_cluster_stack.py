import numpy as np
import pandas as pd
import pytest

from research import event_cluster_stack as audit


def test_event_alignment_rejects_duplicate_and_missing_ids():
    frame = pd.DataFrame({"match_id": [1, 2], "y": [0, 1]})
    events = pd.DataFrame({"match_id": [2, 1], "event_id": [8, None]})
    joined = audit.align_events(frame, events)
    assert joined.match_id.tolist() == [1, 2]
    assert pd.isna(joined.event_id.iloc[0])
    for bad in ([1, 1], [1, 3], [1], [1, None]):
        with pytest.raises(ValueError, match="match_id"):
            audit.align_events(frame, pd.DataFrame({"match_id": bad, "event_id": [8]*len(bad)}))
    with pytest.raises(ValueError, match="duplicate"):
        audit.align_events(pd.concat([frame, frame.iloc[:1]]), events)


def test_null_events_are_distinct_singletons():
    part = pd.DataFrame({"match_id": [1, 2, 3, 4], "event_id": [None, None, 9, 9]})
    assert audit.cluster_keys(part) == ["match:1", "match:2", "event:9", "event:9"]


def test_bootstrap_resamples_whole_events_and_seed_is_fixed():
    delta = np.array([1., 1., -1.])
    keys = ["event:1", "event:1", "event:2"]
    seed, count = 13, 200
    draws = np.random.default_rng(seed).integers(2, size=(count, 2))
    totals, sizes = np.array([2., -1.]), np.array([2, 1])
    expected = np.percentile(totals[draws].sum(axis=1) / sizes[draws].sum(axis=1), [2.5, 97.5])
    actual = audit.cluster_bootstrap(delta, keys, seed=seed, resamples=count)
    assert actual == pytest.approx(expected)
    assert actual == audit.cluster_bootstrap(delta, keys, seed=seed, resamples=count)
    assert audit.leave_one_event_out(delta, keys) == {"advantage": -1., "removed_event": "event:1"}


def test_frozen_weights_ignore_test_labels():
    # Use the real frozen fit; outcomes outside 2023-24 may change only scores.
    train = pd.DataFrame({"match_id": [1, 2, 3, 4], "tier": [1]*4,
                          "year": [2023, 2023, 2024, 2024], "y": [0, 1, 0, 1],
                          "event_id": [1, 1, 2, 2],
                          "p_elo": [.4, .6, .45, .55], "p_rs": [.3, .7, .4, .6],
                          "p_ls": [.35, .65, .42, .58], "p_fs": [.38, .62, .44, .56]})
    test = train.iloc[:4].copy()
    test["match_id"] = [5, 6, 7, 8]
    test["year"] = [2025, 2025, 2026, 2026]
    test["event_id"] = [3, 4, 5, 6]
    frame = pd.concat([train, test], ignore_index=True)
    first = audit.evaluate(frame)
    changed = frame.copy()
    changed.loc[changed.year >= 2025, "y"] = 1 - changed.loc[changed.year >= 2025, "y"]
    second = audit.evaluate(changed)
    assert first["weights_four"] == pytest.approx(second["weights_four"])
