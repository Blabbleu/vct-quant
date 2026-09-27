import duckdb

from scripts import fix_team_labels as ftl


def _db():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE match (match_id BIGINT, date_raw VARCHAR)")
    con.execute("CREATE TABLE match_team (match_id BIGINT, team_number SMALLINT, team_id BIGINT, team_name VARCHAR)")
    con.execute("CREATE TABLE match_map (match_map_id BIGINT, match_id BIGINT)")
    con.execute("CREATE TABLE match_map_team_score (match_map_id BIGINT, team_id BIGINT)")
    con.execute("INSERT INTO match VALUES (1, '2025'), (2, '2021'), (3, '2026')")
    con.execute("""INSERT INTO match_team VALUES
        (1, 1, 3788, 'Mega Minors'), (1, 2, 1120, 'EDward Gaming'),
        (2, 1, 3788, 'Mega Minors'), (2, 2, 9, 'Other'),
        (3, 1, 1034, 'NRG'), (3, 2, 3788, 'Mega Minors')""")
    con.execute("INSERT INTO match_map VALUES (10, 1), (20, 2), (30, 3)")
    con.execute("INSERT INTO match_map_team_score VALUES (10, 3788), (10, 1120), (20, 3788), (30, 3788)")
    return con


IDS = {"Mega Minors": 3788, "NRG": 1034}


def test_plan_targets_only_listed_years_and_flags_clashes():
    rows = ftl.plan(_db(), IDS)
    assert [(r["match_id"], r["clash"]) for r in rows] == [(1, False), (3, True)]


def test_apply_moves_rows_and_map_scores_and_is_idempotent():
    con = _db()
    rows = [r for r in ftl.plan(con, IDS) if not r["clash"]]
    assert ftl.apply(con, rows) == (1, 1)
    assert con.execute("SELECT team_id, team_name FROM match_team WHERE match_id=1 AND team_number=1").fetchone() == (1034, "NRG")
    assert con.execute("SELECT team_id FROM match_map_team_score WHERE match_map_id=10 ORDER BY team_id").fetchall() == [(1034,), (1120,)]
    # 2021's real Mega Minors is untouched.
    assert con.execute("SELECT team_id FROM match_team WHERE match_id=2 AND team_number=1").fetchone() == (3788,)
    assert [r["match_id"] for r in ftl.plan(con, IDS) if not r["clash"]] == []
