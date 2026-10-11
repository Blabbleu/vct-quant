"""Focused invariants for the shadow state-space replay."""

import pytest

from research.state_space_bt import (Observation, Team, advance, ekf_update,
                                     map_probability, replay, series_forecast)
from research.round_share_series import series_probability

CELL = (0.002, 1.0, 0.3)


def obs(match_id, maps, *, outcome=1.0, best_of=3):
    return Observation(match_id, "a", "b", 100.0, 2025, best_of, 1, outcome, maps)


def test_forecast_precedes_all_maps_of_own_match():
    first_wins = [obs(1, (1, 1, 1)), obs(2, ())]
    first_loses = [obs(1, (0, 0, 0)), obs(2, ())]
    win_forecasts, _, _ = replay(first_wins, CELL)
    lose_forecasts, _, _ = replay(first_loses, CELL)
    assert win_forecasts[0] == lose_forecasts[0] == 0.5
    assert win_forecasts[1] > 0.5 > lose_forecasts[1]


def test_variance_grows_with_days_and_crossed_years():
    state = {}
    team = advance(state, "a", 100.0, 2023, *CELL)
    assert team.variance == 1.0
    team = advance(state, "a", 110.0, 2025, *CELL)
    assert team.variance == pytest.approx(1.0 + 10 * 0.002 + 2 * 0.3)
    assert team.mu == 0.0


def test_ekf_moves_winner_and_shrinks_both_variances():
    a, b = Team(0.0, 1.0, None, None), Team(0.0, 1.0, None, None)
    ekf_update(a, b, 1)
    assert a.mu > 0 > b.mu
    assert 0 < a.variance < 1
    assert 0 < b.variance < 1


def test_swapping_sides_complements_map_and_series_forecasts():
    a, b = Team(0.7, 0.4, None, None), Team(-0.2, 0.8, None, None)
    p, swapped = map_probability(a, b), map_probability(b, a)
    assert p + swapped == pytest.approx(1.0)
    assert series_forecast(p, 3) + series_forecast(swapped, 3) == pytest.approx(1.0)


def test_bo3_uses_series_probability_and_unknown_uses_map_probability():
    p = 0.63
    assert series_forecast(p, 3) == pytest.approx(series_probability(p, 3))
    assert series_forecast(p, None) == p
