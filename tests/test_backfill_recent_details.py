from datetime import date, datetime, timezone

import duckdb

from scripts import backfill_recent_details as backfill
from vct_quant import recent_details


def make_db():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE event (event_id BIGINT, tier SMALLINT, name TEXT)")
    con.execute("CREATE TABLE match (match_id BIGINT, event_id BIGINT, status TEXT, completed_at TIMESTAMPTZ)")
    con.execute("CREATE TABLE match_team (match_id BIGINT, team_number SMALLINT, team_name TEXT, series_score SMALLINT)")
    con.execute("CREATE TABLE match_map (match_map_id BIGINT, match_id BIGINT, map_number SMALLINT, map_name TEXT)")
    return con


def add_match(con, match_id, *, tier=1, completed="2026-07-01", scores=(2, 0), status="completed"):
    con.execute("INSERT INTO event VALUES (?, ?, 'event')", [match_id + 10000, tier])
    completed_at = datetime.fromisoformat(completed).replace(tzinfo=timezone.utc) if completed else None
    con.execute("INSERT INTO match VALUES (?, ?, ?, ?)", [match_id, match_id + 10000, status, completed_at])
    con.executemany("INSERT INTO match_team VALUES (?, ?, ?, ?)", [
        (match_id, 1, "Alpha", scores[0]), (match_id, 2, "Bravo", scores[1])
    ])


def test_targets_filters_and_orders_completed_scored_unmapped_matches():
    con = make_db()
    add_match(con, 1)
    add_match(con, 2)
    con.execute("INSERT INTO match_map VALUES (1, 2, 1, 'Ascent')")
    add_match(con, 3, completed="2026-05-31")
    add_match(con, 4, tier=2)
    add_match(con, 5, scores=(0, 0))
    add_match(con, 6, scores=(None, 1))
    add_match(con, 7, completed=None)
    add_match(con, 8, completed="2026-08-01")
    assert backfill.targets(con, date(2026, 6, 1)) == [8, 1]
    assert backfill.targets(con, date(2026, 6, 1), (1, 2)) == [8, 4, 1]


def test_already_have_finds_timestamped_detail(monkeypatch, tmp_path):
    (tmp_path / "match_details_123_20261009T120000.json").touch()
    monkeypatch.setattr(recent_details, "RAW_VLRGG_DIR", tmp_path)
    assert backfill.already_have(123)
    assert not backfill.already_have(124)


def test_dry_run_does_not_fetch(monkeypatch, capsys):
    class Connection:
        def close(self): pass

    monkeypatch.setattr(backfill.db, "connect", lambda read_only=False: Connection())
    monkeypatch.setattr(backfill, "targets", lambda con, since, tiers: [91, 90, 89])
    monkeypatch.setattr(backfill, "already_have", lambda match_id: False)
    monkeypatch.setattr(backfill.vlrgg, "fetch_match_details", lambda _: (_ for _ in ()).throw(AssertionError("fetch called")))
    assert backfill.main(["--dry-run"]) == 0
    assert "3 match details" in capsys.readouterr().out
