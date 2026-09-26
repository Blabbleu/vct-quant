"""Only verified, paired, pre-start finished series enter the live holdout."""
import duckdb
import pandas as pd

from scripts import grade_predictions
from vct_quant import dashboard, db
from vct_quant.live_grading import graded_forecasts
from vct_quant.match_result import result_detail


def _log():
    return pd.DataFrame({
        "match_id": [11, 11, 12, 13],
        "predicted_at": pd.to_datetime([
            "2026-09-18T10:00Z", "2026-09-18T11:00Z",
            "2026-09-18T11:00Z", "2026-09-18T11:00Z",
        ]),
        "scheduled_at": pd.to_datetime(["2026-09-19T12:00Z"] * 4),
        "team_a_key": ["1", "1", "1", "1"],
        "team_b_key": ["2", "2", "2", "2"],
        "team_a_id": [1, 1, 1, 1], "team_b_id": [2, 2, 2, 2],
        "team_a_name": ["Alpha"] * 4, "team_b_name": ["Beta"] * 4,
        "p_market_a": [0.5] * 4, "market_spread": [0.05] * 4,
        "p_team_a_win": [0.4, 0.6, 0.7, 0.8],
        "p_team_a_win_ensemble": [0.5, 0.65, 0.75, 0.85],
    })


def _result(a, b, *, completed="2026-09-19T15:00Z"):
    meta = {"status": "completed", "completed_at": completed, "scheduled_at": "2026-09-19T12:00Z", "best_of": 3}
    teams = pd.DataFrame({"team_number": [1, 2], "team_id": [1, 2],
                          "team_name": ["Alpha", "Beta"], "series_score": [2, 0],
                          "is_winner": [True, False]})
    return result_detail(meta, teams, pd.DataFrame(), a, b)


def test_grades_latest_verified_pair_and_preserves_shadow_column():
    def load(mid, a, b, p):
        return _result(a, b) if mid == 11 else None

    scored = graded_forecasts(_log(), load)
    assert scored.match_id.tolist() == [11]
    assert scored.y.tolist() == [1]
    assert scored.p_team_a_win.tolist() == [0.6]
    assert scored.p_team_a_win_ensemble.tolist() == [0.65]
    assert scored.attrs["logged"] == 3


def test_conflicting_latest_timestamp_is_not_scored():
    log = _log().iloc[:2].copy()
    log.loc[0, "predicted_at"] = log.loc[1, "predicted_at"]
    log.loc[0, "team_b_key"] = "99"
    scored = graded_forecasts(log, lambda mid, a, b, p: _result(a, b))
    assert scored.attrs["logged"] == 1
    assert scored.empty


def test_logged_schedule_outlives_completed_result_even_if_db_was_rescheduled():
    log = _log().iloc[:2].copy()
    logged = log.scheduled_at.iloc[0]
    log["scheduled_at"] = pd.Timestamp("2026-09-21T12:00Z")
    def load(mid, a, b, p):
        # The canonical match now has an earlier scheduled time, so its own
        # validation passes; the log's original schedule must still veto it.
        return {"status": "verified", "winner": "a", "completed_on": logged.date().isoformat()}
    scored = graded_forecasts(log, load)
    assert scored.attrs["logged"] == 1
    assert scored.empty


def test_both_live_reports_withhold_a_one_sided_result(tmp_path, monkeypatch, capsys):
    path = tmp_path / "fixture.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE match (match_id INTEGER, status VARCHAR, completed_at TIMESTAMP, scheduled_at TIMESTAMP, best_of INTEGER, vlr_url VARCHAR, last_seen_at TIMESTAMP)")
        con.execute("CREATE TABLE match_team (match_id INTEGER, team_number INTEGER, team_id INTEGER, team_name VARCHAR, series_score INTEGER, is_winner BOOLEAN)")
        con.execute("CREATE TABLE match_map (match_id INTEGER, match_map_id INTEGER, map_number INTEGER, map_name VARCHAR)")
        con.execute("CREATE TABLE match_map_team_score (match_map_id INTEGER, team_number INTEGER, total_rounds INTEGER)")
        con.execute("INSERT INTO match VALUES (11, 'completed', '2026-09-19 15:00', '2026-09-19 12:00', 3, NULL, NULL)")
        con.execute("INSERT INTO match_team VALUES (11, 1, 1, 'Alpha', 2, TRUE), (11, 2, 99, 'Other', 0, FALSE)")
    monkeypatch.setattr(db, "connect", lambda read_only=False: duckdb.connect(str(path), read_only=True))
    monkeypatch.setattr(dashboard, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(grade_predictions, "PROCESSED_DIR", tmp_path)
    _log().iloc[:2].to_parquet(tmp_path / "prediction_log.parquet")

    live = dashboard.graded_log()
    assert live["logged"] == 1
    assert live["graded"] == 0
    assert grade_predictions.main() == 0
    assert "none played yet" in capsys.readouterr().out
