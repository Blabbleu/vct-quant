"""Opt-in: forfeits with no scored map stay out of the Elo replay.

docs/forfeit-labels.md: a stored 0-0 with no winner is replayed as a draw, and
a forfeit whose placeholder side has no score was stored with the winner
flipped (`0 > NaN`). Neither carries performance information.
"""

import duckdb
import pytest

from vct_quant.features import build
from vct_quant.features.build import match_sequence, unscored_forfeit


def _db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE event (event_id INTEGER, tier INTEGER)")
    con.execute('CREATE TABLE match (match_id INTEGER, event_id INTEGER, date_raw VARCHAR, completed_at TIMESTAMP)')
    con.execute("""CREATE TABLE match_team (
        match_id INTEGER, team_number INTEGER, team_id INTEGER,
        team_name VARCHAR, is_winner BOOLEAN, series_score INTEGER)""")
    con.execute("CREATE TABLE match_map (match_map_id INTEGER, match_id INTEGER, map_number INTEGER)")
    con.execute("CREATE TABLE match_map_team_score (match_map_id INTEGER, team_number INTEGER, total_rounds INTEGER)")
    con.execute("INSERT INTO event VALUES (1, 1)")
    rows = {
        1: (("A", True, 2), ("B", False, 1)),     # played Bo3
        2: (("A", None, 0), ("B", None, 0)),      # 0-0 forfeit, no winner: replayed as a draw
        3: (("A", False, 0), ("TBD", True, None)),  # forfeit by TBD, winner flipped
        4: (("A", None, 1), ("B", None, 1)),      # genuine Bo2 draw
        5: (("A", True, 1), ("B", False, 0)),     # Bo1 1-0
    }
    for mid, sides in rows.items():
        con.execute("INSERT INTO match (match_id, event_id, date_raw) VALUES (?, 1, '2025')", [mid])
        for num, (name, win, score) in enumerate(sides, start=1):
            con.execute("INSERT INTO match_team VALUES (?, ?, NULL, ?, ?, ?)", [mid, num, name, win, score])
    return con


def test_unscored_forfeit_flags_only_rows_without_a_scored_map():
    con = _db()
    try:
        seq = match_sequence(con, skip_unscored=False)
    finally:
        con.close()
    assert seq.match_id.tolist() == [1, 2, 3, 4, 5]
    assert unscored_forfeit(seq).tolist() == [False, True, True, False, False]


def test_skip_unscored_drops_forfeits_and_keeps_played_draws():
    con = _db()
    try:
        kept = match_sequence(con, skip_unscored=True)
    finally:
        con.close()
    assert kept.match_id.tolist() == [1, 4, 5]
    assert kept.loc[kept.match_id.eq(4), "score_a"].item() == 0.5


def test_approved_default_skips_unscored_forfeits_and_flag_can_be_disabled(monkeypatch):
    assert build.SKIP_UNSCORED_FORFEITS is True
    con = _db()
    try:
        assert match_sequence(con).match_id.tolist() == [1, 4, 5]
        monkeypatch.setattr(build, "SKIP_UNSCORED_FORFEITS", False)
        assert match_sequence(con).match_id.tolist() == [1, 2, 3, 4, 5]
    finally:
        con.close()


@pytest.mark.parametrize("maps_a,maps_b,label,expected", [
    (None, None, 0.5, True),
    (2, None, 0.0, True),
    (0, 0, 0.5, True),
    (0, 0, 1.0, False),  # a stored winner on 0-0 is kept (not observed today; don't guess)
    (1, 1, 0.5, False),
    (1, 0, 1.0, False),
])
def test_unscored_forfeit_cases(maps_a, maps_b, label, expected):
    import pandas as pd
    df = pd.DataFrame({"maps_a": pd.array([maps_a], dtype="Int64"),
                       "maps_b": pd.array([maps_b], dtype="Int64"),
                       "score_a": [label]})
    assert unscored_forfeit(df).tolist() == [expected]
