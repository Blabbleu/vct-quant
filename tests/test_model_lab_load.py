import duckdb
import pandas as pd
import pytest

from scripts import model_lab


@pytest.mark.parametrize("include_completed_at", [True, False])
def test_load_merges_only_missing_match_columns(monkeypatch, include_completed_at):
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE match (match_id INTEGER, best_of INTEGER, completed_at TIMESTAMPTZ)")
    con.execute("INSERT INTO match VALUES (10, 3, '2024-01-02 00:00:00+00')")
    con.execute("CREATE TABLE match_map (match_map_id INTEGER, match_id INTEGER)")
    con.execute("""CREATE TABLE match_map_player_stat (
        match_map_id INTEGER, team_number INTEGER, player_id INTEGER, player_handle VARCHAR
    )""")
    monkeypatch.setattr(model_lab.db, "connect", lambda **kwargs: con)

    sequence = {
        "match_id": [10], "tier": [1], "year": [2024], "team_a": [1], "team_b": [2],
        "maps_a": [2.0], "maps_b": [1.0], "score_a": [1.0],
    }
    if include_completed_at:
        sequence["completed_at"] = pd.to_datetime(["2024-01-02"], utc=True)
    monkeypatch.setattr(model_lab, "match_sequence", lambda _con: pd.DataFrame(sequence))

    loaded = model_lab.load()
    df = loaded["df"]
    assert list(df.columns).count("completed_at") == 1
    assert "completed_at_x" not in df and "completed_at_y" not in df
    assert df.loc[0, "completed_at"] == pd.Timestamp("2024-01-02", tz="UTC")
    assert loaded["match_id"].tolist() == [10]
