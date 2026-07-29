import duckdb
import pandas as pd

from vct_quant.etl.normalize import official_match_details, official_upcoming
from vct_quant.features.build import (
    add_map_predictions,
    current_rankings,
    predict_upcoming,
)


def test_official_upcoming_filters_and_resolves_ids():
    con = duckdb.connect()
    con.execute("CREATE TABLE team (team_id BIGINT, name TEXT)")
    con.execute("CREATE TABLE match_team (team_id BIGINT, team_name TEXT)")
    con.execute("CREATE TABLE event (event_id BIGINT, name TEXT, tier SMALLINT)")
    con.execute("INSERT INTO team VALUES (1, 'GIANTX'), (2, 'Team Liquid')")
    con.execute("INSERT INTO event VALUES (10, 'VCT 2026: EMEA Stage 2', 1)")
    payload = {"data": {"segments": [
        {
            "team1": "GIANTX", "team2": "Team Liquid",
            "match_event": "VCT 2026: EMEA Stage 2",
            "match_series": "Group Stage: Week 3",
            "unix_timestamp": "2026-07-29 15:00:00",
            "match_page": "712824/giantx-vs-team-liquid",
            "time_until_match": "20h",
        },
        {
            "team1": "SK Nebula", "team2": "G2 Gozen",
            "match_event": "Game Changers 2026: EMEA Stage 3",
            "match_series": "Group Stage",
            "unix_timestamp": "2026-07-29 15:00:00",
            "match_page": "716585/sk-nebula-vs-g2-gozen",
            "time_until_match": "20h",
        },
    ]}}

    out = official_upcoming(payload, con)

    assert out[[
        "match_id", "event_id", "best_of", "team_a_id", "team_a_key",
        "team_b_id", "team_b_key",
    ]].iloc[0].tolist() == [712824, 10, 3, 1, "1", 2, "2"]
    assert len(out) == 1


def test_official_match_details_normalizes_later_fixture():
    payload = {"data": {"segments": [{
        "match_id": "706376",
        "event": {
            "name": "VCT 2026: Americas Stage 2 Group Stage: Week 4",
            "series": "Group Stage: Week 4",
        },
        "date": "Saturday, August 8 5:00 PM EDT",
        "status": "10d 4h",
        "teams": [
            {"id": "2355", "name": "KRÜ Esports", "score": ""},
            {"id": "2", "name": "Sentinels", "score": ""},
        ],
        "maps": [{"map_name": "TBD"}] * 3,
    }]}}

    out = official_match_details(payload).iloc[0]

    assert out[["match_id", "event_name", "best_of"]].tolist() == [
        706376, "VCT 2026: Americas Stage 2", 3,
    ]
    assert out[["team_a_key", "team_b_key"]].tolist() == ["2355", "2"]


def test_predict_upcoming_replays_existing_elo():
    history = pd.DataFrame({
        "match_id": [1],
        "tier": [1],
        "team_a": ["1"],
        "team_b": ["2"],
        "maps_a": [2],
        "maps_b": [0],
        "score_a": [1.0],
    })
    fixtures = pd.DataFrame({
        "team_a_key": ["1", "2"],
        "team_b_key": ["2", "new"],
    })

    out = predict_upcoming(fixtures, history)

    assert out.loc[0, "p_team_a_win"] > 0.5
    assert out.loc[1, "p_team_a_win"] < 0.5
    assert (out.p_team_a_win + out.p_team_b_win).eq(1).all()
    assert out.ratings_through_match_id.tolist() == [1, 1]
    assert out.score_probabilities.map(lambda scores: abs(sum(scores.values()) - 1)).lt(1e-12).all()


def test_current_rankings_only_includes_latest_tier_one_season():
    history = pd.DataFrame({
        "match_id": [1, 2],
        "tier": [1, 1],
        "year": [2025, 2026],
        "team_a": ["old", "1"],
        "team_b": ["1", "2"],
        "team_a_name": ["Retired Team", "Alpha"],
        "team_b_name": ["Alpha", "Bravo"],
        "maps_a": [2, 2],
        "maps_b": [0, 0],
        "score_a": [1.0, 1.0],
    })

    out = current_rankings(history)

    assert out.team_name.tolist() == ["Alpha", "Bravo"]
    assert out["rank"].tolist() == [1, 2]
    assert out.season.tolist() == [2026, 2026]


def test_known_map_picks_condition_the_score_distribution():
    history = pd.DataFrame([
        {"map_name": name, "team_a": "1", "team_b": "2", "score_a": score}
        for name, score in [
            ("ascent", 1.0), ("ascent", 1.0), ("bind", 0.0),
            ("bind", 0.0), ("haven", 1.0),
        ]
    ])
    fixture = pd.DataFrame([{
        "team_a_key": "1",
        "team_b_key": "2",
        "event_series": "Group Stage",
        "best_of": 3,
        "p_team_a_win": 0.5,
        "p_team_b_win": 0.5,
    }])

    out = add_map_predictions(fixture, ["ascent", "bind", "haven"], history)
    maps = out.map_predictions.iloc[0]

    assert maps[0]["p_team_a_win"] > 0.5
    assert maps[1]["p_team_a_win"] < 0.5
    assert abs(sum(out.score_probabilities.iloc[0].values()) - 1.0) < 1e-12
