"""The Match Center movement series uses only comparable pre-start observations."""
import pandas as pd

from vct_quant.match_center import movement, recent_form


def test_recent_form_is_point_in_time_and_separates_rating_pools():
    rows = pd.DataFrame([
        (3, 1, "1", "9", "A", "X", 1., 2, 0, "2026-09-20T10:00Z"),
        (4, 2, "1", "8", "A", "Y", 0., 0, 2, "2026-09-21T10:00Z"),
        (5, 1, "7", "1", "Z", "A", 1., 2, 1, "2026-09-22T10:00Z"),
        (6, 1, "1", "6", "A", "TBD", 1., 2, 0, "2026-09-23T10:00Z"),
        (7, 1, "1", "5", "A", "F", 1., None, None, "2026-09-23T11:00Z"),
        (8, 1, "1", "4", "A", "D", 0., 1, 2, "2026-09-26T10:00Z"),
        (9, 1, "1", "3", "A", "B", 1., 2, 0, "2026-09-24T10:00Z"),
        (10, 1, "1", "2", "A", "B", 1., 2, 0, "2026-09-23T10:00Z"),
        (11, 1, "1", "2", "A", "B", 1., 2, 0, None),
        (1, 1, "1", "2", "A", "B", 1., 2, 0, "2026-09-25T00:00Z"),
    ], columns=["match_id", "tier", "team_a", "team_b", "team_a_name",
                "team_b_name", "score_a", "maps_a", "maps_b", "completed_at"])
    result = recent_form(rows, "1", "2", 10, "2026-09-25T20:00Z")
    assert [(x["match_id"], x["result"], x["opponent"]) for x in result["a"]] == [
        (9, "W", "B"), (5, "L", "Z"), (3, "W", "X")]
    assert result["b"] == []


def test_recent_form_sorts_by_completion_date_not_match_id():
    rows = pd.DataFrame([
        (2, 1, "1", "3", "A", "Old", 1., 2, 0, "2026-09-22T00:00Z"),
        (3, 1, "1", "4", "A", "New ID", 1., 2, 0, "2026-09-21T00:00Z"),
    ], columns=["match_id", "tier", "team_a", "team_b", "team_a_name",
                "team_b_name", "score_a", "maps_a", "maps_b", "completed_at"])
    assert [x["match_id"] for x in recent_form(rows, "1", "5", 4, "2026-09-23T00:00Z")["a"]] == [2, 3]


def test_recent_form_excludes_gc_and_future_id_even_when_date_is_past():
    rows = pd.DataFrame([
        (1, 3, "1", "2", "A", "B", 1., 2, 0, "2026-09-20T10:00Z"),
        (21, 1, "1", "2", "A", "B", 1., 2, 0, "2026-09-20T10:00Z"),
    ], columns=["match_id", "tier", "team_a", "team_b", "team_a_name",
                "team_b_name", "score_a", "maps_a", "maps_b", "completed_at"])
    assert recent_form(rows, "1", "2", 10, "2026-09-25T00:00Z") == {"a": [], "b": []}



def test_movement_keeps_prestart_snapshots_of_the_latest_pairing():
    log = pd.DataFrame([
        {"match_id": 42, "predicted_at": "2026-09-25T08:00Z", "scheduled_at": "2026-09-25T12:00Z",
         "team_a_name": "A", "team_b_name": "B", "team_a_key": "id:1", "team_b_key": "id:2",
         "p_team_a_win": .55, "p_market_a": .51, "market_spread": .04, "market_slug": "m1"},
        {"match_id": 42, "predicted_at": "2026-09-25T09:00Z", "scheduled_at": "2026-09-25T12:00Z",
         "team_a_name": "B", "team_b_name": "A", "team_a_key": "id:2", "team_b_key": "id:1",
         "p_team_a_win": .46, "p_market_a": .49, "market_spread": .04, "market_slug": "m1"},
        {"match_id": 42, "predicted_at": "2026-09-25T10:00Z", "scheduled_at": "2026-09-25T12:00Z",
         "team_a_name": "A", "team_b_name": "B", "team_a_key": "id:1", "team_b_key": "id:2",
         "p_team_a_win": .58, "p_market_a": .53, "market_spread": .06, "market_slug": "m1"},
        {"match_id": 42, "predicted_at": "2026-09-25T12:01Z", "scheduled_at": "2026-09-25T12:00Z",
         "team_a_name": "A", "team_b_name": "B", "team_a_key": "id:1", "team_b_key": "id:2",
         "p_team_a_win": .99, "p_market_a": .99, "market_spread": .02, "market_slug": "m1"},
    ])
    result = movement(log, 42)
    assert result["match_id"] == 42
    assert result["team_a"] == "A"
    assert result["team_b"] == "B"
    assert [x["elo"] for x in result["points"]] == [.55, .58]
    assert [x["market"] for x in result["points"]] == [.51, .53]
    assert [x["observed_at"] for x in result["points"]] == ["2026-09-25T08:00:00+00:00", "2026-09-25T10:00:00+00:00"]


def test_movement_unknown_match_is_none():
    assert movement(pd.DataFrame(), 99) is None


def test_movement_does_not_join_different_market_contracts():
    log = pd.DataFrame([
        {"match_id": 8, "predicted_at": "2026-09-25T08:00Z", "scheduled_at": "2026-09-25T12:00Z",
         "team_a_name": "A", "team_b_name": "B", "team_a_key": "a", "team_b_key": "b",
         "p_team_a_win": .55, "p_market_a": .51, "market_spread": .02, "market_slug": "old"},
        {"match_id": 8, "predicted_at": "2026-09-25T09:00Z", "scheduled_at": "2026-09-25T12:00Z",
         "team_a_name": "A", "team_b_name": "B", "team_a_key": "a", "team_b_key": "b",
         "p_team_a_win": .58, "p_market_a": .54, "market_spread": .02, "market_slug": "new"},
    ])
    assert [p["elo"] for p in movement(log, 8)["points"]] == [.55, .58]
    assert [p["market"] for p in movement(log, 8)["points"]] == [None, .54]
    assert [p["spread"] for p in movement(log, 8)["points"]] == [None, .02]
