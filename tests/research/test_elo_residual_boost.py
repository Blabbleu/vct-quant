import numpy as np
import pandas as pd

from research.elo_residual_boost import FEATURES, build_matrix, fit_path, mirror, predict


def sample():
    matches = pd.DataFrame({
        "match_id": [1, 2, 3, 4], "team_a": ["A", "A", "B", "A"],
        "team_b": ["B", "C", "C", "B"], "year": [2023]*4,
        "tier": [1]*4, "score_a": [1., 0., 1., 0.],
        "p_elo": [.6, .7, .55, .65], "best_of": [3]*4,
        "completed_at": pd.to_datetime(["2023-01-01", "2023-01-03", None,
                                        "2023-01-08"], utc=True),
    })
    extras = pd.DataFrame({"match_id": [1, 2, 3, 4],
                           "churn_a": [.1]*4, "churn_b": [.2]*4,
                           "player_form_diff": [.3]*4})
    maps = {1: [(13, 5)], 2: [(3, 13)], 3: [(13, 8)], 4: [(8, 13)]}
    return matches, maps, extras


def test_zero_rounds_are_exact_elo():
    matches, maps, extras = sample()
    frame = build_matrix(matches, maps, extras)
    x = frame[list(FEATURES)].to_numpy(float)
    np.testing.assert_array_equal(predict(x, []), frame.p_elo.to_numpy())


def test_side_swap_complements_prediction():
    matches, maps, extras = sample()
    frame = build_matrix(matches, maps, extras)
    x = frame[list(FEATURES)].to_numpy(float)
    trees = fit_path(x, frame.y.to_numpy(float), depth=1, leaf=2, rounds=3)
    np.testing.assert_allclose(predict(mirror(x), trees), 1-predict(x, trees), atol=1e-15)


def test_current_outcome_and_maps_do_not_change_own_features():
    matches, maps, extras = sample()
    original = build_matrix(matches, maps, extras)
    changed = matches.copy()
    changed.loc[1, "score_a"] = 1.
    replacement_maps = dict(maps)
    replacement_maps[2] = [(13, 1), (13, 1)]
    revised = build_matrix(changed, replacement_maps, extras)
    pd.testing.assert_series_equal(original.loc[1, list(FEATURES)],
                                   revised.loc[1, list(FEATURES)])
    assert original.loc[3, "form_a"] != revised.loc[3, "form_a"]
    assert original.loc[3, "map_share_a"] != revised.loc[3, "map_share_a"]


def test_form_and_rest_use_only_earlier_matches():
    matches, maps, extras = sample()
    frame = build_matrix(matches, maps, extras)
    assert frame.loc[0, "form_a"] == 0
    assert frame.loc[0, "days_a"] == -1
    assert frame.loc[0, "days_missing_a"] == 1
    assert frame.loc[1, "form_a"] == .4
    assert frame.loc[1, "days_a"] == 2
    assert frame.loc[2, "days_b"] == -1  # current date is missing
    assert frame.loc[3, "days_a"] == 5
    assert frame.loc[3, "form_a"] == np.mean([.4, -.7])
