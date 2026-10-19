"""Synthetic timing and baseline guards for season-start diagnostics."""
import copy

import numpy as np
import pandas as pd
import pytest

from research.season_start import production_probabilities, side_windows


OLD = ["a", "b", "c", "d", "e"]
CHANGED = ["a", "b", "c", "x", "y"]
OTHER = ["f", "g", "h", "i", "j"]


def sequence():
    return {
        "match_id": np.array([10, 20, 30, 40, 50, 60, 70]),
        "year": np.array([2024, 2025, 2025, 2025, 2025, 2025, 2025]),
        "tier": np.array([1, 1, 2, 1, 1, 1, 1]),
        "team_a": np.array(["old", "old", "old", "old", "old", "old", "new"]),
        "team_b": np.array(["other", "new", "other", "new", "new", "new", "other"]),
        "lineup_a": [OLD, CHANGED, CHANGED, CHANGED, CHANGED, CHANGED, OTHER],
        "lineup_b": [OTHER, OTHER, OTHER, OTHER, OTHER, OTHER, OTHER],
        "signal": np.array([1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0]),
        "y": np.array([1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0]),
    }


def test_windows_continuing_new_boundary_and_cap():
    sides = side_windows(sequence())
    assert [(s["match_id"], s["team"], s["rank"]) for s in sides] == [
        (20, "old", 1), (40, "old", 2), (50, "old", 3), (70, "other", 1)]
    assert sides[0]["asof"] is None
    assert sides[0]["oracle"] == 0.4


def test_strictly_prior_lineup_and_missing_current_year():
    d = sequence()
    sides = side_windows(d)
    assert sides[0]["asof"] is None  # own lineup cannot supply the feature
    assert sides[1]["asof"] == 0.4  # Tier-2 lineup at ID 30 is available
    changed = copy.deepcopy(d)
    changed["lineup_a"][3] = OLD
    changed["lineup_a"][4] = OLD
    later = side_windows(changed)
    assert later[1]["asof"] == sides[1]["asof"]
    assert later[1]["oracle"] == 0.0  # oracle uses the current match


def test_no_prior_lineup_remains_missing_after_current_and_later_changes():
    d = sequence()
    d["lineup_a"][2] = []
    assert side_windows(d)[1]["asof"] == 0.4  # ID 20 remains last observed
    d["lineup_a"][1] = []
    assert side_windows(d)[1]["asof"] is None


def test_draw_does_not_advance_decisive_window():
    d = sequence()
    d["tier"][2] = 1
    d["y"][2] = 0.5
    assert [(s["match_id"], s["rank"]) for s in side_windows(d) if s["team"] == "old"] == [
        (20, 1), (40, 2), (50, 3)]


def test_elo_equality_guard(monkeypatch):
    d = sequence()
    d["df"] = pd.DataFrame({"tier": d["tier"]})
    d["days"] = np.full(7, np.nan)
    from research import season_start

    assert len(production_probabilities(d)) == len(d["match_id"])
    monkeypatch.setattr(season_start, "run", lambda data, config: np.full(7, 0.5))
    with pytest.raises(AssertionError):
        production_probabilities(d)
