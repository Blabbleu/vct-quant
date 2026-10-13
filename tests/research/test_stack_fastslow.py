import numpy as np
import pandas as pd
import pytest

from research.stack_fastslow import align, fit_frozen, replay
from research.stack_ensemble import logits, sigmoid


def history():
    return pd.DataFrame({
        "match_id": [1, 2, 3, 4], "team_a": ["A", "A", "B", "A"],
        "team_b": ["B", "C", "C", "B"], "tier": [1, 1, 2, 1],
        "score_a": [1., 0., 1., 0.], "maps_a": [2, 0, 2, 1],
        "maps_b": [0, 2, 0, 2],
    })


def test_first_match_and_pre_match_chronology():
    original = replay(history())
    assert original.loc[0, "p_fs"] == pytest.approx(.5)
    changed = history()
    changed.loc[3, ["score_a", "maps_a", "maps_b"]] = [1., 2, 0]
    revised = replay(changed)
    np.testing.assert_allclose(original[["p_16", "p_256", "p_fs"]],
                               revised[["p_16", "p_256", "p_fs"]])
    changed.loc[2, ["score_a", "maps_a", "maps_b"]] = [0., 0, 2]
    revised = replay(changed)
    np.testing.assert_allclose(original.loc[:2, ["p_16", "p_256", "p_fs"]],
                               revised.loc[:2, ["p_16", "p_256", "p_fs"]])


def test_frozen_blend_and_side_reversal():
    original = replay(history())
    expected = sigmoid(.7 * logits(original.p_16) + .3 * logits(original.p_256))
    np.testing.assert_allclose(original.p_fs, expected, rtol=0, atol=1e-15)
    reversed_history = history()
    reversed_history[["team_a", "team_b"]] = reversed_history[["team_b", "team_a"]]
    reversed_history[["maps_a", "maps_b"]] = reversed_history[["maps_b", "maps_a"]]
    reversed_history.score_a = 1 - reversed_history.score_a
    reversed_p = replay(reversed_history)
    for name in ("p_elo_check", "p_16", "p_256", "p_fs"):
        np.testing.assert_allclose(reversed_p[name], 1 - original[name], atol=1e-14)


@pytest.mark.parametrize("change, message", [
    ("missing", "missing or extra"), ("duplicate", "duplicate"),
    ("outcome", "outcomes"), ("baseline", "baseline"),
])
def test_alignment_refuses_mismatch(change, message):
    shadow = replay(history())
    components = pd.DataFrame({
        "match_id": shadow.match_id, "y": shadow.y_check,
        "p_elo": shadow.p_elo_check, "p_rs": .5, "p_ls": .5,
        "tier": 1, "year": 2023,
    })
    if change == "missing":
        shadow = shadow.iloc[:-1]
    elif change == "duplicate":
        shadow = pd.concat([shadow, shadow.iloc[[-1]]], ignore_index=True)
    elif change == "outcome":
        shadow.loc[0, "y_check"] = 0.
    else:
        shadow.loc[0, "p_elo_check"] = .6
    with pytest.raises(ValueError, match=message):
        align(components, shadow)


def test_test_year_labels_cannot_change_fitted_weights():
    rng = np.random.default_rng(12)
    n = 100
    frame = pd.DataFrame({
        "tier": np.ones(n), "year": np.repeat([2023, 2024, 2025, 2026], 25),
        "y": rng.integers(0, 2, n),
        **{name: rng.uniform(.15, .85, n) for name in ("p_elo", "p_rs", "p_ls", "p_fs")},
    })
    original = fit_frozen(frame)
    altered = frame.copy()
    altered.loc[altered.year >= 2025, "y"] = 1 - altered.loc[altered.year >= 2025, "y"]
    for first, second in zip(original, fit_frozen(altered)):
        np.testing.assert_array_equal(first, second)
