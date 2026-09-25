"""The live grading report must preserve the pooled checkpoint score."""

import numpy as np
import pandas as pd

from scripts import grade_predictions as grader


def test_shadow_report_keeps_pooled_score_and_splits_by_fixture_year(capsys):
    scored = pd.DataFrame({
        "scheduled_at": pd.to_datetime([
            "2026-12-31T23:59:00Z", "2026-09-25T12:00:00Z",
            "2027-01-01T00:00:00Z", "2027-01-02T00:00:00Z",
        ]),
        "y": [1, 0, 1, 0],
        "p_team_a_win": [0.6, 0.4, 0.6, 0.4],
        "p_team_a_win_ensemble": [0.7, 0.3, 0.5, np.nan],
    })
    grader._print_shadow_scores(scored, "p_team_a_win_ensemble", "fast/slow ensemble")
    report = capsys.readouterr().out
    assert "fast/slow ensemble, n = 3" in report  # checkpoint uses this pooled n
    assert "elo    0.5108" in report  # same-row comparison, not all four Elo rows
    assert "shadow 0.4688" in report  # preregistered pooled score stays authoritative
    assert "2026: n = 2, elo 0.5108, shadow 0.3567" in report
    assert "2027: n = 1 (paired t unavailable)" in report


def test_shadow_report_exposes_empty_year_without_inventing_a_score(capsys):
    scored = pd.DataFrame({
        "scheduled_at": pd.to_datetime(["2026-09-25T00:00:00Z"]),
        "y": [1], "p_team_a_win": [0.6],
        "p_team_a_win_ensemble": [0.7],
    })
    grader._print_shadow_scores(scored, "p_team_a_win_ensemble", "fast/slow ensemble")
    report = capsys.readouterr().out
    assert "fast/slow ensemble: 1 graded so far" in report
    assert "2026: n = 1" in report
    assert "2027: n = 0" in report
    assert "2027: n = 0 (paired t unavailable)" in report
