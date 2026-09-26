"""Frozen GC blend/shrink protocol: leakage-safe replay and selection."""
import numpy as np
import pandas as pd

from scripts.gc_ensemble_lab import candidate_probabilities, choose, scored_mask, decide


def toy():
    return pd.DataFrame({
        "match_id": [1, 2, 3, 4], "team_a": ["a", "a", "b", "a"],
        "team_b": ["b", "b", "a", "b"], "maps_a": [2, 0, 1, 1],
        "maps_b": [0, 0, 2, 0], "score_a": [1., .5, 1., 0.],
        "year": [2024, 2024, 2025, 2026],
    })


def test_replay_predicts_before_current_result_and_blends_in_logit_space():
    p = candidate_probabilities(toy())
    assert all(np.isclose(v[0], .5) for v in p.values())
    # A different last result cannot change earlier forecasts, even the draw
    changed = toy()
    changed.loc[3, "maps_a"] = 0
    changed.loc[3, "maps_b"] = 2
    for key in p:
        np.testing.assert_allclose(p[key][:4], candidate_probabilities(changed)[key][:4])
    assert np.all((p["blend_0.5"] > 0) & (p["blend_0.5"] < 1))
    odds96 = p["k_96"] / (1 - p["k_96"])
    odds256 = p["k_256"] / (1 - p["k_256"])
    expected = np.sqrt(odds96 * odds256) / (1 + np.sqrt(odds96 * odds256))
    np.testing.assert_allclose(p["blend_0.5"], expected, atol=1e-12)


def test_scoring_excludes_draws_but_keeps_them_in_replay():
    train, test = scored_mask(toy())
    assert train.tolist() == [True, False, False, False]
    assert test.tolist() == [False, False, True, True]
    p = candidate_probabilities(toy())
    without_draw = candidate_probabilities(toy().drop(index=1).reset_index(drop=True))
    assert p["reference"][2] != without_draw["reference"][1]


def test_reference_wins_exact_tie_and_selection_never_uses_test_year():
    forecasts = {"reference": np.array([.5, .1]), "shrink_1.2": np.array([.5, .9])}
    assert choose(np.array([1., 0.]), forecasts, np.array([True, False]))[0] == "reference"


def test_shadow_rule_needs_both_years_and_two_sigma():
    assert decide(2.1, {2025: .001, 2026: .002})
    assert not decide(2.1, {2025: .001, 2026: -.001})
    assert not decide(1.9, {2025: .001, 2026: .002})
