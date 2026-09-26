"""A team profile uses exact IDs and separates recorded history from fixtures."""
import pandas as pd

from vct_quant.team_profile import profile_from_rows
from vct_quant import team_profile as team_module


def test_team_profile_filters_to_exact_identity_and_played_tier1():
    history = pd.DataFrame([
        (1, 1, "2026-09-20", "42", "9", "Falcons", "Nine", 1., 2, 0),
        (2, 1, "2026-09-21", "8", "42", "Eight", "Falcons", 1., 2, 1),
        (3, 3, "2026-09-22", "42", "7", "Falcons", "Seven", 1., 2, 0),
        (4, 1, "2026-09-23", "name:falcons", "7", "Falcons", "Seven", 1., 2, 0),
        (5, 1, "2026-09-23", "42", "6", "Falcons", "TBD", 1., 2, 0),
        (6, 1, "2026-09-24", "42", "5", "Falcons", "Five", .5, 1, 1),
        (7, 1, "2026-09-27", "42", "4", "Falcons", "Four", 1., 2, 0),
        (8, 1, None, "42", "3", "Falcons", "Three", 1., 2, 0),
    ], columns=["match_id", "tier", "completed_at", "team_a", "team_b", "team_a_name", "team_b_name", "score_a", "maps_a", "maps_b"])
    fixtures = pd.DataFrame([
        {"match_id": 10, "scheduled_at": "2026-09-26T12:00Z", "team_a_key": "42", "team_b_key": "8", "team_a_name": "Falcons", "team_b_name": "Eight", "p_team_a_win": .6},
        {"match_id": 11, "scheduled_at": "2026-09-26T13:00Z", "team_a_key": "name:falcons", "team_b_key": "8", "team_a_name": "Falcons", "team_b_name": "Eight", "p_team_a_win": .7},
        {"match_id": 12, "scheduled_at": "2026-09-26T14:00Z", "team_a_key": "8", "team_b_key": "42", "team_a_name": "Eight", "team_b_name": "Falcons", "p_team_a_win": .3, "tier": 1},
        {"match_id": 13, "scheduled_at": "2026-09-26T15:00Z", "team_a_key": "42", "team_b_key": "8", "team_a_name": "Falcons", "team_b_name": "Eight", "p_team_a_win": .8, "tier": 3},
    ])
    out = profile_from_rows(history, fixtures, 42, "2026-09-26T03:00Z")
    assert out["team_id"] == 42
    assert out["name"] == "Falcons"
    assert [(r["match_id"], r["result"]) for r in out["results"]] == [(2, "L"), (1, "W")]
    assert [(r["match_id"], r["p_win"]) for r in out["fixtures"]] == [(10, .6), (12, .7)]
    assert out["record"] == {"wins": 1, "losses": 1}


def test_team_profile_unknown_or_fixture_only():
    empty = pd.DataFrame()
    assert profile_from_rows(empty, empty, 42, "2026-09-26T03:00Z") is None
    fixtures = pd.DataFrame([{"match_id": 10, "scheduled_at": "2026-09-26T12:00Z", "team_a_key": "42", "team_b_key": "8", "team_a_name": "Falcons", "team_b_name": "Eight", "p_team_a_win": .6}])
    out = profile_from_rows(empty, fixtures, 42, "2026-09-26T03:00Z")
    assert out["results"] == [] and out["record"] == {"wins": 0, "losses": 0}
    assert out["fixtures"][0]["match_id"] == 10


def test_team_api_profile_includes_bounded_historical_player_links(monkeypatch, tmp_path):
    monkeypatch.setattr(team_module, "PROCESSED_DIR", tmp_path)
    history = pd.DataFrame([{
        "match_id": 1, "tier": 1, "completed_at": "2026-09-20", "team_a": "42", "team_b": "9",
        "team_a_name": "Falcons", "team_b_name": "Nine", "score_a": 1., "maps_a": 2, "maps_b": 0,
    }])
    monkeypatch.setattr(team_module, "match_sequence", lambda tiers: history)
    monkeypatch.setattr(team_module, "load_logos", lambda: {})
    monkeypatch.setattr(team_module, "load_tags", lambda: {})
    calls = []
    def lineup(team_id, *, as_of):
        calls.append((team_id, as_of))
        return {"maps_sampled": 1, "latest_map_date": "2026-09-20",
                "players": [{"player_id": 7, "handle": "Renamed", "maps": 1}]}
    monkeypatch.setattr(team_module, "recent_lineup", lineup, raising=False)
    result = team_module.team_profile(42)
    assert result["recent_lineup"]["players"][0]["player_id"] == 7
    assert calls[0][0] == 42 and calls[0][1].tzinfo is not None
