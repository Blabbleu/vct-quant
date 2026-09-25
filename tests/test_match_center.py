"""The Match Center movement series uses only comparable pre-start observations."""
import pandas as pd

from vct_quant.match_center import movement


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
