import math

import duckdb
import pandas as pd

from research.round_share_series import (
    load_maps, map_probability, predict_sequence, series_probability, valid_map_rows,
)


def test_valid_scores_and_identity():
    rows = [(1, 13, 10, "Alpha", 10), (2, 9, None, " Beta ", None)]
    assert valid_map_rows(rows, ("10", "name:beta")) == (13, 9)
    assert valid_map_rows(rows, ("name:beta", "10")) is None
    assert valid_map_rows(rows[:1], ("10", "name:beta")) is None
    assert valid_map_rows([(1, -1, 10, "Alpha", 10), rows[1]], ("10", "name:beta")) is None
    assert valid_map_rows([(1, None, 10, "Alpha", 10), rows[1]], ("10", "name:beta")) is None
    assert valid_map_rows([(1, 13, 10, "Alpha", 11), rows[1]], ("10", "name:beta")) is None


def test_load_maps_rejects_misalignment_and_one_sided_map():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE match_map (match_map_id INTEGER, match_id INTEGER)")
    con.execute("CREATE TABLE match_map_team_score (match_map_id INTEGER, team_number INTEGER, total_rounds INTEGER, team_id INTEGER)")
    con.execute("CREATE TABLE match_team (match_id INTEGER, team_number INTEGER, team_id INTEGER, team_name VARCHAR)")
    con.executemany("INSERT INTO match_map VALUES (?, ?)", [(1, 1), (2, 2), (3, 1)])
    con.executemany("INSERT INTO match_team VALUES (?, ?, ?, ?)", [
        (1, 1, 10, "A"), (1, 2, 20, "B"), (2, 1, 20, "B"), (2, 2, 10, "A")])
    con.executemany("INSERT INTO match_map_team_score VALUES (?, ?, ?, ?)", [
        (1, 1, 13, 10), (1, 2, 8, 20), (2, 1, 9, 20), (2, 2, 13, 10), (3, 1, 13, 10)])
    maps, counts = load_maps(con, {1: ("10", "20"), 2: ("10", "20")})
    assert maps == {1: [(13, 8)]}
    assert counts == {"total": 3, "valid": 1, "rejected": 2, "alignment_rejected": 1, "skipped": 0}


def test_history_updates_after_series_and_first_appearance_falls_back():
    matches = pd.DataFrame([
        (1, "a", "b", 3, .6), (2, "a", "b", 3, .6), (3, "a", "b", 3, .6),
    ], columns=["match_id", "team_a", "team_b", "best_of", "p_elo"])
    maps = {1: [(13, 0)], 2: [(13, 0), (13, 0)], 3: [(0, 13)]}
    out = predict_sequence(matches, maps, (10, 100, 1.0))
    assert out.p_model.iloc[0] == .6
    assert not out.covered.iloc[0]
    assert out.covered.iloc[1]
    assert out.p_model.iloc[1] > .5
    assert out.valid_maps.tolist() == [1, 2, 1]
    # Changing later maps in match 2 cannot influence match 2's own forecast.
    changed = {1: [(13, 0)], 2: [(0, 13), (0, 13)]}
    assert predict_sequence(matches, changed, (10, 100, 1.0)).p_model.iloc[1] == out.p_model.iloc[1]


def test_zero_round_history_uses_elo():
    matches = pd.DataFrame([(1, "a", "b", 3, .6), (2, "a", "b", 3, .6)],
                           columns=["match_id", "team_a", "team_b", "best_of", "p_elo"])
    out = predict_sequence(matches, {1: [(0, 0)]}, (10, 100, 1.0))
    assert out.p_model.tolist() == [.6, .6]
    assert out.covered.tolist() == [False, False]


def test_map_and_series_symmetry_monotonicity():
    assert math.isclose(map_probability(.5), .5, abs_tol=1e-12)
    for p in (.1, .3, .7, .9):
        assert math.isclose(map_probability(p) + map_probability(1-p), 1, abs_tol=1e-12)
    for best_of in (1, 3, 5):
        values = [series_probability(p, best_of) for p in (.1, .3, .5, .7, .9)]
        assert all(0 <= p <= 1 for p in values)
        assert values == sorted(values)
        assert math.isclose(values[2], .5, abs_tol=1e-12)
