import duckdb
import pandas as pd

from vct_quant.etl.normalize import official_upcoming
from vct_quant.features.build import predict_upcoming


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
        "match_id", "event_id", "team_a_id", "team_a_key",
        "team_b_id", "team_b_key",
    ]].iloc[0].tolist() == [712824, 10, 1, "1", 2, "2"]
    assert len(out) == 1


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
