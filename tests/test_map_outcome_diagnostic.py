"""Conditional played-map diagnostic: no update from an earlier map in the series."""
import pandas as pd
import pytest

from scripts.map_outcome_diagnostic import replay_maps
from vct_quant.features.maps import map_probabilities


def test_replay_maps_predicts_whole_series_before_any_map_rating_update():
    matches = pd.DataFrame([
        (10, 2023, 3, "A", "B", 0.5),
        (11, 2023, 3, "A", "B", 0.5),
    ], columns=["match_id", "year", "best_of", "team_a", "team_b", "p_global"])
    maps = pd.DataFrame([
        (10, 1, "haven", "A", "B", 1.0),
        (10, 2, "haven", "A", "B", 0.0),
        (11, 1, "haven", "A", "B", 1.0),
    ], columns=["match_id", "map_number", "map_name", "team_a", "team_b", "score_a"])

    result = replay_maps(matches, maps, k=8, prior=0)
    assert result.p_candidate.iloc[0] == result.p_candidate.iloc[1] == 0.5
    # Prior match does update ratings, even though its opposite results nearly cancel.
    assert result.p_candidate.iloc[2] < 0.5
    assert result.match_id.tolist() == [10, 10, 11]


def test_bo1_map_history_trains_only_later_bo3_forecast():
    matches = pd.DataFrame([
        (10, 2023, 1, "A", "B", 0.5),
        (11, 2024, 3, "A", "B", 0.5),
    ], columns=["match_id", "year", "best_of", "team_a", "team_b", "p_global"])
    maps = pd.DataFrame([
        (10, 1, "haven", "A", "B", 1.0),
        (11, 1, "haven", "A", "B", 0.0),
    ], columns=["match_id", "map_number", "map_name", "team_a", "team_b", "score_a"])
    out = replay_maps(matches, maps)
    assert out.match_id.tolist() == [11]
    assert out.prior_min.tolist() == [1]
    assert out.p_candidate.iloc[0] > 0.5


def test_replay_matches_existing_known_map_forecast_from_prior_series():
    matches = pd.DataFrame([
        (10, 2023, 3, "A", "B", 0.5),
        (11, 2024, 3, "A", "B", 0.65),
    ], columns=["match_id", "year", "best_of", "team_a", "team_b", "p_global"])
    maps = pd.DataFrame([
        (10, 1, "haven", "A", "B", 1.0),
        (11, 1, "haven", "A", "B", 0.0),
    ], columns=["match_id", "map_number", "map_name", "team_a", "team_b", "score_a"])
    out = replay_maps(matches, maps)
    from vct_quant.features.ratings import implied_map_probability
    expected = map_probabilities(
        maps.iloc[:1], "A", "B", ["haven"],
        implied_map_probability(0.65, 3),
    )[0]["p_team_a_win"]
    assert out.p_candidate.iloc[1] == pytest.approx(expected)
    assert out.p_base.iloc[1] == pytest.approx(implied_map_probability(0.65, 3))
    assert out.prior_min.iloc[1] == 1
