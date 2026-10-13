import numpy as np
import pandas as pd
import pytest

from research.experience_gated_stack import (
    align_counts, blend, fit_gate, fit_weight, predictions, prior_experience,
)


def history():
    return pd.DataFrame({
        "match_id": [1, 2, 3, 4, 5],
        "team_a": ["A", "A", "B", "A", "B"],
        "team_b": ["B", "C", "C", "B", "C"],
        "tier": [1, 1, 2, 1, 1],
        "score_a": [1, 0, 1, 0, 1],
    })


def frame():
    rng = np.random.default_rng(14)
    n = 120
    result = pd.DataFrame({
        "match_id": np.arange(1, n + 1), "tier": 1,
        "year": np.repeat([2023, 2024, 2025, 2026], 30),
        "y": rng.integers(0, 2, n),
        "prior_min": np.tile(np.arange(30), 4),
        **{name: rng.uniform(.15, .85, n)
           for name in ("p_elo", "p_rs", "p_ls", "p_fs")},
    })
    return result


def test_prior_counts_are_chronological_and_outcome_independent():
    original = prior_experience(history())
    assert original.prior_min.tolist()[:2] == [0, 0]
    assert np.isnan(original.prior_min.iloc[2])
    assert original.prior_min.tolist()[3:] == [1, 1]
    altered = history()
    altered.loc[4, "score_a"] = 0
    pd.testing.assert_frame_equal(original, prior_experience(altered))
    reversed_sides = history().rename(columns={"team_a": "team_b", "team_b": "team_a"})
    pd.testing.assert_frame_equal(original, prior_experience(reversed_sides))


def test_training_only_threshold_and_weights():
    original = fit_gate(frame())
    assert original["threshold"] == 14.5
    assert original["train_groups"] == {"low": 30, "high": 30}
    altered = frame()
    altered.loc[altered.year >= 2025, "y"] = 1 - altered.loc[altered.year >= 2025, "y"]
    altered.loc[altered.year >= 2025, "prior_min"] += 1000
    revised = fit_gate(altered)
    assert original["threshold"] == revised["threshold"]
    assert original["global_weight"] == revised["global_weight"]
    assert original["weights"] == revised["weights"]
    np.testing.assert_array_equal(original["three"], revised["three"])
    np.testing.assert_array_equal(original["four"], revised["four"])


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate"])
def test_count_alignment_requires_one_to_one_ids(change):
    components = frame().iloc[:3]
    counts = components[["match_id", "prior_min"]].copy()
    if change == "missing":
        counts = counts.iloc[:-1]
    elif change == "extra":
        counts.loc[len(counts)] = [99, 0]
    else:
        counts = pd.concat([counts, counts.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError):
        align_counts(components.drop(columns="prior_min"), counts)


def test_gate_uses_each_side_of_train_threshold_and_reverses_sides():
    fitted = fit_gate(frame())
    fitted["weights"] = {"low": 0.0, "high": 1.0}
    part = frame().iloc[[0, 29]].copy()
    part["prior_min"] = [fitted["threshold"], fitted["threshold"] + 1]
    p = predictions(part, fitted)
    assert p["experience gate"][0] == pytest.approx(p["fast/slow"][0])
    assert p["experience gate"][1] == pytest.approx(p["three-input"][1])
    np.testing.assert_allclose(blend(1 - p["three-input"], 1 - p["fast/slow"], [0, 1]),
                               1 - p["experience gate"], atol=1e-15)


def test_flat_blend_uses_preregistered_tie_anchor():
    p = np.array([.3, .7])
    y = np.array([0., 1.])
    assert fit_weight(y, p, p) == .5
    assert fit_weight(y, p, p, anchor=.2, penalty=.01) == .2
