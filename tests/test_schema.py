from pathlib import Path

import duckdb

SCHEMA = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"


def test_schema_applies_cleanly():
    con = duckdb.connect()  # in-memory
    con.execute(SCHEMA.read_text(encoding="utf-8"))
    tables = {
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    for expected in ("team", "player", "event", "match", "match_map",
                     "match_map_player_stat", "harvest_run"):
        assert expected in tables
    assert len(tables) >= 25
