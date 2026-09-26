"""Exact-ID Tier-1 player history is descriptive and excludes future/other-pool rows."""
from datetime import datetime, timezone

import duckdb

from vct_quant.player_profile import player_profile


def test_player_profile_exact_identity_and_scored_prior_maps():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE player (player_id INTEGER, handle VARCHAR, country VARCHAR)")
    con.execute("CREATE TABLE event (event_id INTEGER, tier INTEGER)")
    con.execute("CREATE TABLE match (match_id INTEGER, event_id INTEGER, completed_at TIMESTAMP)")
    con.execute("CREATE TABLE match_team (match_id INTEGER, team_number INTEGER, team_id INTEGER, team_name VARCHAR)")
    con.execute("CREATE TABLE match_map (match_map_id INTEGER, match_id INTEGER, map_number INTEGER, map_name VARCHAR)")
    con.execute("CREATE TABLE match_map_team_score (match_map_id INTEGER, team_number INTEGER, total_rounds INTEGER)")
    con.execute("CREATE TABLE match_map_player_stat (match_map_id INTEGER, team_number INTEGER, player_id INTEGER, player_handle VARCHAR, agent_name VARCHAR, rating DOUBLE, acs DOUBLE, kills INTEGER, deaths INTEGER, assists INTEGER)")
    con.execute("INSERT INTO player VALUES (42, 'NewHandle', 'us'), (43, 'NewHandle', 'ca'), (44, 'Solo', NULL)")
    con.execute("INSERT INTO event VALUES (1,1), (3,3)")
    con.executemany("INSERT INTO match VALUES (?,?,?)", [(1,1,'2026-09-20'), (2,1,'2026-09-22'), (3,3,'2026-09-23'), (4,1,'2026-09-24'), (5,1,'2026-09-26'), (6,1,None), (7,1,'2026-09-21')])
    for match_id in range(1, 8):
        con.execute("INSERT INTO match_team VALUES (?,1,100,'Alpha'), (?,2,200,'Beta')", [match_id,match_id])
        con.execute("INSERT INTO match_map VALUES (?, ?, 1, 'Ascent')", [match_id,match_id])
        con.execute("INSERT INTO match_map_team_score VALUES (?,1,13), (?,2,9)", [match_id,match_id])
        con.execute("INSERT INTO match_map_player_stat VALUES (?,1,42,'OldHandle','Jett',1.1,220,18,12,6)", [match_id])
    # Another player's identical handle must not leak into this profile.
    con.execute("INSERT INTO match_map_player_stat VALUES (1,2,43,'OldHandle','Sova',2.0,300,30,4,8)")
    con.execute("UPDATE match_map_player_stat SET agent_name='jett' WHERE match_map_id=1 AND player_id=42")
    con.execute("UPDATE match_team SET team_name='Old Alpha' WHERE match_id=1 AND team_number=1")
    # Invalid result, anonymous opponent and no complete map score are excluded.
    con.execute("UPDATE match_map_team_score SET total_rounds=NULL WHERE match_map_id=4 AND team_number=2")
    con.execute("UPDATE match_team SET team_name='TBD' WHERE match_id=7 AND team_number=2")
    out = player_profile(42, con=con, as_of=datetime(2026,9,26,tzinfo=timezone.utc))
    assert out['player_id'] == 42 and out['handle'] == 'NewHandle'
    assert out['country'] == 'us'
    assert out['recorded_maps'] == 2
    assert [r['match_id'] for r in out['maps']] == [2,1]
    assert out['agents'] == [{'agent': 'Jett', 'maps': 2}]
    assert out['teams'] == [{'team_id': 100, 'name': 'Alpha', 'maps': 2}]
    assert out['maps'][0]['opponent_id'] == 200
    assert out['maps'][0]['result'] == 'W'
    assert out['maps'][0]['kills'] == 18
    assert player_profile(43, con=con, as_of=datetime(2026,9,26,tzinfo=timezone.utc)) is not None
    assert player_profile(999, con=con, as_of=datetime(2026,9,26,tzinfo=timezone.utc)) is None
    empty = player_profile(44, con=con, as_of=datetime(2026,9,26,tzinfo=timezone.utc))
    assert empty['recorded_maps'] == 0
    assert empty['maps'] == [] and empty['agents'] == [] and empty['teams'] == []
    con.close()
