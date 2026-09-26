"""End-to-end point-in-time invariance of the canonical feature builder."""

import duckdb
import pandas as pd

from vct_quant.features.build import build_features


FEATURE_COLUMNS = [
    "elo_diff", "elo_p_a_win", "churn_a", "churn_b", "player_form_a",
    "player_form_b", "player_form_diff", "player_form_coverage_a",
    "player_form_coverage_b", "player_form_t2_share_a",
    "player_form_t2_share_b", "n_prior_a", "n_prior_b",
]


def test_build_features_does_not_see_its_own_result_or_player_rating():
    """Changing match 2's result/stats may affect match 3, never match 1 or 2."""
    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE TABLE event (event_id INTEGER, tier INTEGER)")
        con.execute('CREATE TABLE match (match_id INTEGER, event_id INTEGER, date_raw VARCHAR, completed_at TIMESTAMP)')
        con.execute("""CREATE TABLE match_team (
            match_id INTEGER, team_number INTEGER, team_id INTEGER,
            team_name VARCHAR, is_winner BOOLEAN, series_score INTEGER)""")
        con.execute("CREATE TABLE match_map (match_map_id INTEGER, match_id INTEGER, map_number INTEGER)")
        con.execute("CREATE TABLE match_map_team_score (match_map_id INTEGER, team_number INTEGER, total_rounds INTEGER)")
        con.execute("""CREATE TABLE match_map_player_stat (
            match_map_id INTEGER, team_number INTEGER, player_id INTEGER,
            player_handle VARCHAR, player_slot INTEGER, rating DOUBLE)""")
        con.execute("INSERT INTO event VALUES (1, 1), (2, 2)")
        con.execute("INSERT INTO match (match_id, event_id, date_raw) VALUES (1, 2, '2025'), (2, 1, '2025'), (3, 1, '2025')")
        # Shared players and teams establish prior Elo and player form on both sides.
        for match_id, a, b in [(1, 'A', 'B'), (2, 'A', 'B'), (3, 'A', 'B')]:
            con.executemany("INSERT INTO match_team VALUES (?, ?, NULL, ?, ?, ?)", [
                (match_id, 1, a, True, 2), (match_id, 2, b, False, 1),
            ])
            con.execute("INSERT INTO match_map VALUES (?, ?, 1)", [match_id, match_id])
            con.executemany("INSERT INTO match_map_player_stat VALUES (?, ?, NULL, ?, 1, ?)", [
                (match_id, 1, 'alpha', 1.1 + match_id / 10),
                (match_id, 2, 'bravo', 0.9 - match_id / 10),
            ])
        before = build_features(con).set_index('match_id')
        con.execute("UPDATE match_team SET is_winner = NOT is_winner WHERE match_id = 2")
        con.execute("UPDATE match_team SET series_score = CASE team_number WHEN 1 THEN 0 ELSE 2 END WHERE match_id = 2")
        con.execute("UPDATE match_map_player_stat SET rating = 0.1 WHERE match_map_id = 2 AND team_number = 1")
        after = build_features(con).set_index('match_id')
        pd.testing.assert_frame_equal(before.loc[[1, 2], FEATURE_COLUMNS], after.loc[[1, 2], FEATURE_COLUMNS])
        assert before.loc[2, 'label'] != after.loc[2, 'label']
        assert before.loc[3, 'elo_p_a_win'] != after.loc[3, 'elo_p_a_win']
        assert before.loc[3, 'player_form_a'] != after.loc[3, 'player_form_a']
    finally:
        con.close()
