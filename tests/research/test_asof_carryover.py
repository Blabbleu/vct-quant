"""Synthetic timing checks for the read-only carry-over audit."""
import copy

import numpy as np

from research.asof_carryover import replay


SOURCE = [f"s{i}" for i in range(5)]
OTHER = [f"o{i}" for i in range(5)]
MOVED = SOURCE[:3] + ["new1", "new2"]


def history():
    return {
        "match_id": np.array([10, 20, 30]),
        "tier": np.array([1, 2, 1]),
        "year": np.array([2024, 2024, 2025]),
        "team_a": np.array(["source", "new", "new"]),
        "team_b": np.array(["other", "tier2_opponent", "other"]),
        "signal": np.array([1.0, 1.0, 0.0]),
        "y": np.array([1.0, 1.0, 0.0]),
        "lineup_a": [SOURCE, MOVED, MOVED],
        "lineup_b": [OTHER, ["t1", "t2", "t3", "t4", "t5"], OTHER],
    }


def test_debut_prediction_ignores_own_match_lineup_and_result():
    d = history()
    p, debuts = replay(d)
    changed = copy.deepcopy(d)
    changed["lineup_a"][2] = ["unrelated1", "unrelated2", "unrelated3"]
    changed["lineup_b"][2] = ["different"]
    changed["signal"][2] = 1.0
    changed["y"][2] = 1.0
    altered, _ = replay(changed)
    assert p[2] == altered[2]
    assert next(x for x in debuts if x["team"] == "new")["source"] == "source"


def test_prior_tier2_roster_changes_debut_source_without_rating_update():
    d = history()
    p, debuts = replay(d)
    assert next(x for x in debuts if x["team"] == "new")["prior_size"] == 5
    assert next(x for x in debuts if x["team"] == "new")["source"] == "source"

    no_roster = copy.deepcopy(d)
    no_roster["lineup_a"][1] = []
    missing, missing_debuts = replay(no_roster)
    assert next(x for x in missing_debuts if x["team"] == "new")["source"] is None
    assert p[2] > missing[2]

    changed_result = copy.deepcopy(d)
    changed_result["signal"][1] = 0.0
    changed_result["y"][1] = 0.0
    unchanged, _ = replay(changed_result)
    np.testing.assert_array_equal(p[[0, 2]], unchanged[[0, 2]])


def test_match_ids_must_increase():
    d = history()
    d["match_id"][1] = 9
    try:
        replay(d)
    except ValueError as error:
        assert "strictly increasing" in str(error)
    else:
        raise AssertionError("unordered replay accepted")
