"""Recent linked players come only from exact-ID scored Tier-1 team maps."""
from datetime import datetime, timezone

import duckdb

from vct_quant.recent_lineup import recent_lineup


def test_recent_lineup_uses_five_prior_maps_and_exact_team_player_ids():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE event (event_id INTEGER, tier INTEGER)")
    con.execute("CREATE TABLE match (match_id INTEGER, event_id INTEGER, completed_at TIMESTAMP)")
    con.execute("CREATE TABLE match_team (match_id INTEGER, team_number INTEGER, team_id INTEGER, team_name VARCHAR)")
    con.execute("CREATE TABLE match_map (match_map_id INTEGER, match_id INTEGER, map_number INTEGER)")
    con.execute("CREATE TABLE match_map_team_score (match_map_id INTEGER, team_number INTEGER, total_rounds INTEGER)")
    con.execute("CREATE TABLE match_map_player_stat (match_map_id INTEGER, team_number INTEGER, player_id INTEGER, player_handle VARCHAR)")
    con.execute("CREATE TABLE player (player_id INTEGER, handle VARCHAR)")
    con.execute("INSERT INTO event VALUES (1,1), (2,3)")
    con.execute("INSERT INTO player VALUES (7,'Renamed'), (8,'Twin'), (9,'Twin')")
    for mid, event, date, opponent in [(1,1,'2026-09-20','Beta'), (2,1,'2026-09-21','Beta'),
                                       (3,1,'2026-09-22','Beta'), (4,1,'2026-09-23','Beta'),
                                       (5,1,'2026-09-24','Beta'), (6,1,'2026-09-25','Beta'),
                                       (7,2,'2026-09-25','Beta'), (8,1,'2026-09-26','Beta'),
                                       (9,1,'2026-09-25','TBD'), (10,1,None,'Beta')]:
        con.execute("INSERT INTO match VALUES (?,?,?)", [mid,event,date])
        con.execute("INSERT INTO match_team VALUES (?,1,100,'Alpha'), (?,2,200,?)", [mid,mid,opponent])
        con.execute("INSERT INTO match_map VALUES (?,?,1)", [mid,mid])
        con.execute("INSERT INTO match_map_team_score VALUES (?,1,13), (?,2,9)", [mid,mid])
        con.execute("INSERT INTO match_map_player_stat VALUES (?,1,7,'Old'), (?,2,9,'Twin')", [mid,mid])
    con.execute("INSERT INTO match_map_player_stat VALUES (6,1,8,'Twin')")
    con.execute("UPDATE match_map_team_score SET total_rounds=NULL WHERE match_map_id=5 AND team_number=2")
    out = recent_lineup(100, con=con, as_of=datetime(2026,9,26,tzinfo=timezone.utc), map_limit=3)
    assert out['maps_sampled'] == 3
    assert [p['player_id'] for p in out['players']] == [7, 8]
    assert out['players'][0] == {'player_id': 7, 'handle': 'Renamed', 'maps': 3}
    assert out['players'][1]['maps'] == 1
    assert out['latest_map_date'] == '2026-09-25'
    assert out['latest_match_id'] == 6
    assert recent_lineup(999, con=con, as_of=datetime(2026,9,26,tzinfo=timezone.utc))['players'] == []
    assert recent_lineup(100, con=con, as_of=datetime(2026,9,20,tzinfo=timezone.utc)) == {
        'maps_sampled': 0, 'latest_map_date': None, 'latest_match_id': None, 'players': []}
    con.close()
