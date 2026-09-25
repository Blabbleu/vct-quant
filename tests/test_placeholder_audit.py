"""Archived completed/TBD rows must be accounted for before a clean rebuild."""

import duckdb

from scripts.placeholder_audit import placeholder_rows


def test_placeholder_audit_counts_each_completed_match_once_and_excludes_valid_forfeits():
    con = duckdb.connect()
    con.execute("CREATE TABLE event (event_id INTEGER, tier INTEGER)")
    con.execute('CREATE TABLE "match" (match_id INTEGER, event_id INTEGER, status TEXT)')
    con.execute("CREATE TABLE match_team (match_id INTEGER, team_number INTEGER, team_name TEXT, series_score INTEGER)")
    con.execute("INSERT INTO event VALUES (1, 1), (2, 2), (3, 3)")
    con.execute("""INSERT INTO "match" VALUES
        (10, 1, 'completed'), (11, 2, 'completed'), (12, 3, 'completed'),
        (13, 1, 'completed'), (14, 1, 'scheduled')""")
    con.execute("""INSERT INTO match_team VALUES
        (10, 1, 'TBD', 0), (10, 2, 'Alpha', 1),
        (11, 1, 'Beta', 0), (11, 2, ' tBd ', NULL),
        (12, 1, 'TBD', 2), (12, 2, 'TBD', NULL),
        (13, 1, 'Alpha', NULL), (13, 2, 'Beta', NULL),
        (14, 1, 'TBD', NULL), (14, 2, 'Beta', NULL)""")
    rows = placeholder_rows(con)
    assert rows.match_id.tolist() == [10, 11, 12]
    assert rows.tier.tolist() == [1, 2, 3]
    assert rows.missing_score.tolist() == [False, True, True]
    assert rows.team_a.tolist() == ['TBD', 'Beta', 'TBD']
