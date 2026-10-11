"""Batch BT invariants on tiny match sequences; no live database needed."""
import numpy as np
import pandas as pd
import pytest

from research.batch_bt import Cell, assigned_days, fit_strengths, replay


def frame(rows):
    return pd.DataFrame(rows, columns=["match_id", "team_a", "team_b", "completed_at", "score_a", "maps_a", "maps_b"])


def test_forecast_excludes_own_same_day_and_later_results():
    base = frame([(1, "A", "B", "2025-01-01", 1., 2, 0),
                  (2, "A", "C", "2025-01-04", 1., 2, 0),
                  (3, "B", "C", "2025-01-04", 0., 0, 2),
                  (4, "A", "B", "2025-01-10", 1., 2, 0)])
    cell = Cell(90, 1, "maps")
    original = replay(base, cell)
    changed = base.copy()
    changed.loc[changed.match_id >= 2, ["score_a", "maps_a", "maps_b"]] = [0., 0, 2]
    other = replay(changed, cell)
    assert other[1] == pytest.approx(original[1])
    assert other[2] == pytest.approx(original[2])
    assert other[3] != pytest.approx(original[3])


def test_earlier_id_with_later_date_is_excluded():
    base = frame([(1, "A", "B", "2025-01-10", 1., 2, 0),
                  (2, "A", "B", "2025-01-04", 1., 2, 0)])
    changed = base.copy()
    changed.loc[0, ["score_a", "maps_a", "maps_b"]] = [0., 0, 2]
    cell = Cell(90, .1, "series")
    assert replay(base, cell)[1] == replay(changed, cell)[1] == .5


def test_swapping_teams_complements_probability():
    base = frame([(1, "A", "B", "2025-01-01", 1., 2, 0),
                  (2, "A", "B", "2025-01-10", 0., 0, 2)])
    flipped = base.copy()
    flipped.loc[1, ["team_a", "team_b"]] = ["B", "A"]
    assert replay(base, Cell(180, 1, "series"))[1] + replay(flipped, Cell(180, 1, "series"))[1] == pytest.approx(1)


def test_transitive_ranking_without_direct_game():
    rows = []
    for i in range(10):
        rows.extend([(2*i+1, "A", "B", "2025-01-01", 1., 2, 0),
                     (2*i+2, "B", "C", "2025-01-01", 1., 2, 0)])
    rows.append((21, "A", "C", "2025-01-10", 0., 0, 2))
    assert replay(frame(rows), Cell(365, .1, "series"))[-1] > .5


def test_half_life_halves_old_weight():
    age = np.array([0., 90.])
    np.testing.assert_allclose(np.exp2(-age / 90), [1., .5])
    a, b = np.array([0, 0]), np.array([1, 1])
    recent = fit_strengths(a, b, np.array([1., 0.]), np.ones(2), age, 90, .1, 2)
    old = fit_strengths(a, b, np.array([1., 0.]), np.ones(2), age[::-1], 90, .1, 2)
    assert recent[0] > recent[1]
    assert old[0] < old[1]


def test_undated_match_forward_fills_day():
    data = frame([(1, "A", "B", "2025-01-01", 1., 2, 0),
                  (2, "A", "C", None, 1., 2, 0)])
    assert assigned_days(data)[0] == assigned_days(data)[1]
