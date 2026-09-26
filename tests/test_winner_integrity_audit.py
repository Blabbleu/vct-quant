"""Read-only winner-label integrity audit (docs/forfeit-labels.md)."""

import json
from types import SimpleNamespace

import duckdb
import pandas as pd

from scripts.winner_integrity_audit import (
    audit, classify_db, compare_feed, feed_winners, flag_vs_score, label,
)


def row(score_a, score_b, win_a, win_b, name_a="A", name_b="B"):
    return SimpleNamespace(score_a=score_a, score_b=score_b, win_a=win_a, win_b=win_b,
                           name_a=name_a, name_b=name_b)


def test_label_mirrors_elo_case_expression():
    assert label(True, False) == "a"
    assert label(False, True) == "b"
    assert label(None, None) == "none"
    assert label(False, False) == "both_false"
    assert label(True, True) == "both_true"


def test_classify_db_separates_played_draws_from_scoreless_forfeits():
    assert classify_db(row(2, 1, True, False)) == "consistent"
    assert classify_db(row(1, 2, True, False)) == "winner_contradicts_score"
    assert classify_db(row(1, 1, None, None)) == "legit_draw"
    assert classify_db(row(0, 0, None, None)) == "scoreless_no_winner"
    # The 97028 shape: forfeit by TBD, `0 > NaN` stored the placeholder as winner.
    assert classify_db(row(0, float("nan"), False, True)) == "winner_without_full_score"


def test_flag_vs_score():
    assert flag_vs_score("2", "1", 1) == "agrees"
    assert flag_vs_score("1", "2", 1) == "contradicts"
    assert flag_vs_score("0", "–", 1) == "no_decisive_score"


def _feed(name_1, name_2, winner_side, s1="0", s2="–"):
    return SimpleNamespace(feed_name_1=name_1, feed_name_2=name_2, feed_winner_side=winner_side,
                           feed_winner_name=name_1 if winner_side == 1 else name_2,
                           feed_flag_vs_score=flag_vs_score(s1, s2, winner_side))


def test_compare_feed_detects_flip_and_feed_self_contradiction():
    db_row = row(0, float("nan"), False, True, "IlluZion", "TBD")
    assert compare_feed(db_row, _feed("IlluZion", "TBD", 1)) == "flipped"
    # 78157 shape: feed scores 1-2 yet flags team 1 the winner; DB follows the score.
    played = row(1, 2, False, True, "Os Selvagens", "Arca do Plato")
    assert compare_feed(played, _feed("Os Selvagens", "Arca do Plato", 1, "1", "2")) == "feed_self_contradicts"
    assert compare_feed(played, _feed("Os Selvagens", "Arca do Plato", 2, "1", "2")) == "agree"
    renamed = row(0, 2, False, True, "Talon Esports", "Team Vitality")
    assert compare_feed(renamed, _feed("TALON", "Team Vitality", 2, "0", "2")) == "names_differ_agree_by_position"
    assert compare_feed(row(0, 0, None, None), _feed("A", "B", 1, "0", "0")) == "db_has_no_single_winner"


def test_feed_winners_keeps_latest_single_flag_snapshot(tmp_path):
    def seg(mid, f1, f2, status="Completed"):
        return {"match_id": str(mid), "status": status,
                "team1": {"name": "A", "score": "2", "is_winner": f1},
                "team2": {"name": "B", "score": "0", "is_winner": f2}}
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    old.write_text(json.dumps([seg(1, False, True), seg(2, True, False)]))
    new.write_text(json.dumps([seg(1, True, False), seg(2, True, True), seg(3, True, False, "Upcoming")]))
    feed = feed_winners([old, new], lambda p: json.loads(p.read_text()))
    by_id = feed.set_index("match_id")
    assert sorted(by_id.index) == [1, 2]
    assert by_id.loc[1, "feed_winner_side"] == 1  # the newer snapshot wins
    assert by_id.loc[2, "feed_winner_side"] == 1  # a both-true later row is not evidence


def test_audit_reads_db_without_writing():
    con = duckdb.connect()
    con.execute("CREATE TABLE event (event_id INTEGER, tier INTEGER)")
    con.execute('CREATE TABLE "match" (match_id INTEGER, event_id INTEGER, status TEXT, best_of INTEGER, vlr_url TEXT)')
    con.execute("""CREATE TABLE match_team (match_id INTEGER, team_number INTEGER, team_name TEXT,
                   series_score INTEGER, is_winner BOOLEAN)""")
    con.execute("CREATE TABLE match_map (match_id INTEGER)")
    con.execute("INSERT INTO event VALUES (1, 1)")
    con.execute("""INSERT INTO "match" VALUES (1, 1, 'completed', 3, ''), (2, 1, 'completed', 1, '')""")
    con.execute("""INSERT INTO match_team VALUES
        (1, 1, 'A', 2, TRUE), (1, 2, 'B', 0, FALSE),
        (2, 1, 'A', 0, FALSE), (2, 2, 'TBD', NULL, TRUE)""")
    feed = pd.DataFrame([{"match_id": 2, "feed_name_1": "A", "feed_name_2": "TBD",
                          "feed_score_1": "0", "feed_score_2": "–", "feed_winner_side": 1,
                          "feed_winner_name": "A", "feed_flag_vs_score": "no_decisive_score",
                          "feed_file": "x"}])
    res = audit(con, feed).set_index("match_id")
    assert res.loc[1, "db_class"] == "consistent" and res.loc[1, "feed_class"] == "no_feed_winner"
    assert res.loc[2, "db_class"] == "winner_without_full_score"
    assert res.loc[2, "feed_class"] == "flipped"
