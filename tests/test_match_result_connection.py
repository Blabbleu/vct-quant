"""Reusing one read-only connection must not change what the loaders return."""
import duckdb

from vct_quant import db as db_module
from vct_quant import match_result
from vct_quant.match_result import load_history_keys, load_result


def database():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE match (match_id BIGINT, status VARCHAR, completed_at TIMESTAMPTZ, scheduled_at TIMESTAMPTZ,"
                " best_of SMALLINT, vlr_url VARCHAR, last_seen_at TIMESTAMPTZ)")
    con.execute("CREATE TABLE match_team (match_id BIGINT, team_number SMALLINT, team_id BIGINT, team_name VARCHAR,"
                " series_score SMALLINT, is_winner BOOLEAN)")
    con.execute("CREATE SEQUENCE seq_mm")
    con.execute("CREATE TABLE match_map (match_map_id BIGINT DEFAULT nextval('seq_mm'), match_id BIGINT, map_number SMALLINT, map_name VARCHAR)")
    con.execute("CREATE TABLE match_map_team_score (match_map_id BIGINT, team_number SMALLINT, total_rounds SMALLINT)")
    con.execute("INSERT INTO match VALUES (7, 'completed', '2026-09-24 20:00:00+00', '2026-09-24 17:00:00+00', 3,"
                " 'https://www.vlr.gg/7/a-vs-b', '2026-09-24 21:00:00+00')")
    con.execute("INSERT INTO match_team VALUES (7, 1, 10, 'Alpha', 2, TRUE), (7, 2, 20, 'Bravo', 0, FALSE)")
    for number, name, one, two in ((1, "lotus", 13, 6), (2, "split", 13, 9)):
        con.execute("INSERT INTO match_map (match_id, map_number, map_name) VALUES (7, ?, ?)", [number, name])
        map_id = con.execute("SELECT max(match_map_id) FROM match_map").fetchone()[0]
        con.execute("INSERT INTO match_map_team_score VALUES (?, 1, ?), (?, 2, ?)", [map_id, one, map_id, two])
    return con


def test_shared_connection_gives_the_same_result_and_opens_nothing(monkeypatch):
    con = database()
    expected = load_result(7, "10", "20", 0.6, con=con)
    assert expected["status"] == "verified" and expected["winner"] == "a" and expected["maps_complete"] is True
    assert load_result(999, "10", "20", 0.6, con=con) is None
    assert load_history_keys(7, "name:alpha", "name:bravo", con) == ("10", "20")

    def refuse(*args, **kwargs):
        raise AssertionError("a passed-in connection must be used instead of opening the database")

    monkeypatch.setattr(db_module, "connect", refuse)
    assert load_result(7, "10", "20", 0.6, con=con) == expected
    assert load_history_keys(7, "20", "10", con) == ("20", "10")


def test_without_a_connection_each_call_opens_and_closes_its_own(monkeypatch):
    con = database()
    opened = []

    class Handle:
        def __enter__(self):
            opened.append("open")
            return con

        def __exit__(self, *exc):
            opened.append("close")
            return False

    monkeypatch.setattr(match_result.db, "connect", lambda read_only=False: Handle())
    assert load_result(7, "10", "20", 0.6)["status"] == "verified"
    assert load_history_keys(7, "10", "20") == ("10", "20")
    assert opened == ["open", "close", "open", "close"]
