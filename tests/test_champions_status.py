"""Read-only Champions group state from exact, scored canonical rows."""
import duckdb
import pytest

from vct_quant.champions_status import champions_status
from vct_quant.event_bracket import load_bracket_spec


def database(rows):
    db = duckdb.connect(":memory:")
    db.execute("CREATE TABLE match (match_id BIGINT, event_id BIGINT, event_series VARCHAR, status VARCHAR, last_seen_at TIMESTAMP)")
    db.execute("CREATE TABLE match_team (match_id BIGINT, team_number INT, team_id BIGINT, team_name VARCHAR, series_score INT, is_winner BOOLEAN)")
    for match_id, stage, status, sides in rows:
        db.execute("INSERT INTO match VALUES (?, 2766, ?, ?, '2026-09-26 03:00:00')", [match_id, stage, status])
        for number, (team_id, score, winner) in enumerate(sides, 1):
            db.execute("INSERT INTO match_team VALUES (?, ?, ?, ?, ?, ?)", [match_id, number, team_id, str(team_id), score, winner])
    return db


def test_champions_status_routes_only_db_verified_results():
    spec = load_bracket_spec(2766)
    db = database([
        (753454, "Opening (C)", "completed", [(731, 0, False), (11058, 2, True)]),
        (753455, "Opening (C)", "completed", [(474, 1, False), (624, 2, True)]),
        (753459, "Opening (D)", "completed", [(8877, 2, True), (13581, 0, False)]),
        (753460, "Opening (D)", "completed", [(11060, 0, False), (1034, 2, True)]),
    ])
    output = champions_status(db, spec)
    assert output["event_id"] == 2766
    assert output["as_of"] == "2026-09-26T03:00:00"
    assert output["groups"]["C"]["expected"] == {"winners": [11058, 624], "elimination": [731, 474]}
    assert output["groups"]["D"]["expected"] == {"winners": [8877, 1034], "elimination": [13581, 11060]}
    assert output["groups"]["C"]["results"]["opening_1"]["scores"] == [0, 2]
    assert output["groups"]["A"]["expected"] == {}
    assert output["groups"]["C"]["qualifiers"] == []
    assert output["groups"]["C"]["entrants"]["11058"] == "G2 Esports"
    assert output["groups"]["C"]["slots"]["opening_1"] == {"match_id": 753454, "stage": "Opening (C)", "team_ids": [731, 11058]}
    assert output["groups"]["C"]["slots"]["decider"] == {"match_id": 753458, "stage": "Decider (C)"}
    assert output["playoff_routing"] == "unresolved"
    assert output["title_odds"] is None
    db.close()


@pytest.mark.parametrize("sql", [
    "UPDATE match SET event_id=99 WHERE match_id=753455",
    "UPDATE match SET event_series='Decider (C)' WHERE match_id=753455",
    "UPDATE match_team SET team_id=999 WHERE match_id=753455 AND team_number=2",
    "UPDATE match_team SET series_score=1 WHERE match_id=753455 AND team_number=2",
    "UPDATE match_team SET is_winner=false WHERE match_id=753455 AND team_number=2",
    "DELETE FROM match_team WHERE match_id=753455 AND team_number=2",
])
def test_champions_status_does_not_route_unverified_completed_match(sql):
    db = database([
        (753454, "Opening (C)", "completed", [(731, 0, False), (11058, 2, True)]),
        (753455, "Opening (C)", "completed", [(474, 1, False), (624, 2, True)]),
    ])
    db.execute(sql)
    group = champions_status(db, load_bracket_spec(2766))["groups"]["C"]
    assert group["results"] == {"opening_1": {"team_ids": [731, 11058], "scores": [0, 2]}}
    assert group["expected"] == {}
    assert group["qualifiers"] == []
    assert group["unverified_match_ids"] == [753455]
    db.close()


def test_champions_status_never_advances_premature_winners_result():
    db = database([
        (753454, "Opening (C)", "completed", [(731, 0, False), (11058, 2, True)]),
        (753456, "Winner's (C)", "completed", [(11058, 2, True), (624, 0, False)]),
    ])
    group = champions_status(db, load_bracket_spec(2766))["groups"]["C"]
    assert group["expected"] == {}
    assert group["qualifiers"] == []
    assert 753456 in group["unverified_match_ids"]
    db.close()
