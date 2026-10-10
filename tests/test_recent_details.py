from datetime import date, datetime, timedelta, timezone

import duckdb

from vct_quant import recent_details


def make_db():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE event (event_id BIGINT, tier SMALLINT, name TEXT)")
    con.execute("CREATE TABLE match (match_id BIGINT, event_id BIGINT, status TEXT, completed_at TIMESTAMPTZ)")
    con.execute("CREATE TABLE match_team (match_id BIGINT, team_number SMALLINT, team_name TEXT, series_score SMALLINT)")
    con.execute("CREATE TABLE match_map (match_map_id BIGINT, match_id BIGINT, map_number SMALLINT, map_name TEXT)")
    return con


def add_match(con, match_id, completed):
    con.execute("INSERT INTO event VALUES (?, 1, 'event')", [match_id + 1000])
    con.execute("INSERT INTO match VALUES (?, ?, 'completed', ?)", [match_id, match_id + 1000, completed])
    con.executemany("INSERT INTO match_team VALUES (?, ?, ?, ?)", [
        (match_id, 1, "Alpha", 2), (match_id, 2, "Bravo", 0),
    ])


def setup_refresh(monkeypatch, tmp_path, con):
    monkeypatch.setattr(recent_details.db, "connect", lambda read_only=False: con)
    monkeypatch.setattr(recent_details, "RAW_VLRGG_DIR", tmp_path)


def test_targets_use_recent_window_and_skip_harvested(monkeypatch, tmp_path):
    con = make_db()
    today = datetime.now(timezone.utc).date()
    add_match(con, 1, datetime.combine(today - timedelta(days=3), datetime.min.time(), timezone.utc))
    add_match(con, 2, datetime.combine(today - timedelta(days=15), datetime.min.time(), timezone.utc))
    (tmp_path / "match_details_1_20261010T000000.json").touch()
    setup_refresh(monkeypatch, tmp_path, con)
    fetched = []
    result = recent_details.refresh_recent_details(fetch=fetched.append, load=lambda: None)
    assert result == {"targets": 0, "fetched": 0, "failed": 0, "loaded": 0}
    assert fetched == []


def test_refresh_caps_newest_first_and_tolerates_fetch_and_load_failures(monkeypatch, tmp_path):
    con = make_db()
    today = datetime.now(timezone.utc).date()
    for match_id, age in [(10, 3), (11, 1), (12, 2), (13, 4)]:
        add_match(con, match_id, datetime.combine(today - timedelta(days=age), datetime.min.time(), timezone.utc))
    setup_refresh(monkeypatch, tmp_path, con)
    fetched = []
    loads = []

    def fetch(match_id):
        fetched.append(match_id)
        if match_id == 12:
            raise RuntimeError("offline")

    def load():
        loads.append(True)
        raise ValueError("load error")

    result = recent_details.refresh_recent_details(max_matches=3, fetch=fetch, load=load)
    assert fetched == [11, 12, 10]
    assert loads == [True]
    assert result == {"targets": 3, "fetched": 2, "failed": 2, "loaded": 0}


def test_load_runs_once_only_after_successful_fetch(monkeypatch, tmp_path):
    con = make_db()
    today = datetime.now(timezone.utc).date()
    add_match(con, 20, datetime.combine(today, datetime.min.time(), timezone.utc))
    setup_refresh(monkeypatch, tmp_path, con)
    loads = []
    result = recent_details.refresh_recent_details(
        fetch=lambda _: (_ for _ in ()).throw(OSError("fetch error")),
        load=lambda: loads.append(True),
    )
    assert result == {"targets": 1, "fetched": 0, "failed": 1, "loaded": 0}
    assert loads == []
