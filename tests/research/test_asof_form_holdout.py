import json

import numpy as np
import pandas as pd
import pytest

from research import asof_form_holdout as holdout


def row(match_id, completed_at, y=1, form=0.2, elo=0.6, tier=1, event=7):
    return dict(match_id=match_id, completed_at=completed_at, y=y,
                player_form_diff=form, p_elo=elo, tier=tier, event_id=event)


FROZEN = json.loads(holdout.FROZEN_PATH.read_text())


def test_strict_cutoff_frozen_weights_and_missing_form(monkeypatch):
    monkeypatch.setattr(holdout.form_stack, "fit_frozen", lambda *_: pytest.fail("scorer refit"))
    frame = pd.DataFrame([
        row(1, "2026-10-15T06:59:59Z", y=0),
        row(2, holdout.FREEZE_TIME, y=0),
        row(3, "2026-10-15T07:00:01Z", form=np.nan),
        row(4, "2026-10-15T07:00:02Z", form=0.2),
    ])
    result = holdout.evaluate(frame, FROZEN)
    assert result["eligible_rows"] == 2
    assert result["verdict"] == "PENDING"
    p0 = holdout.stack.predict(np.array([[holdout.stack.logits(np.array([0.6]))[0], 0]]),
                               np.array(FROZEN["weights"]))[0]
    p1 = holdout.stack.predict(np.array([[holdout.stack.logits(np.array([0.6]))[0],
                                          0.2 / FROZEN["form_difference_scale"]]]),
                               np.array(FROZEN["weights"]))[0]
    expected_loss = -np.log([p0, p1]).mean()
    assert result["primary"]["loss"] == pytest.approx(expected_loss)
    changed = frame.copy()
    changed.loc[changed.match_id == 4, "y"] = 0
    changed_result = holdout.evaluate(changed, FROZEN)
    assert changed_result["primary"]["loss"] == pytest.approx((-np.log(p0)-np.log1p(-p1))/2)


def test_first_150_and_verdict_boundaries():
    start = pd.Timestamp("2026-10-15T07:00:01Z")
    rows = [row(i, start + pd.Timedelta(seconds=i), y=i % 2, event=i // 10)
            for i in range(151)]
    # Reverse input order: completed_at, not frame position, determines the window.
    full = holdout.evaluate(pd.DataFrame(rows[::-1]), FROZEN)
    first = holdout.evaluate(pd.DataFrame(rows[:150]), FROZEN)
    assert full["primary"]["n"] == 150
    assert full["primary"]["loss"] == pytest.approx(first["primary"]["loss"])
    assert full["primary"]["distinct_events"] == 15
    assert full["later_rows"]["n"] == 1
    assert first["later_rows"] is None
    assert holdout.evaluate(pd.DataFrame(rows[:149]), FROZEN)["verdict"] == "PENDING"
    assert holdout.verdict({"t": 2.01, "ece": 0.04, "elo_ece": 0.04}, 150) == "WIN"
    assert holdout.verdict({"t": 2.01, "ece": 0.05, "elo_ece": 0.04}, 150) == "NOT PROVEN"
    assert holdout.verdict({"t": 2.0, "ece": 0.03, "elo_ece": 0.04}, 150) == "NOT PROVEN"
    assert holdout.verdict({"t": 0.01, "ece": 0.03, "elo_ece": 0.04}, 150) == "NOT PROVEN"
    assert holdout.verdict({"t": 0, "ece": 0.03, "elo_ece": 0.04}, 150) == "REJECTED"
    assert holdout.verdict({"t": -0.01, "ece": 0.03, "elo_ece": 0.04}, 150) == "REJECTED"


@pytest.mark.parametrize("weights,scale", [([0.872970, 0.07737623], 0.09254274),
                                           ([0.87296870, 0.07737623], 0.092544)])
def test_freeze_refuses_documented_drift(monkeypatch, tmp_path, weights, scale):
    monkeypatch.setattr(holdout.form_stack, "fit_frozen", lambda _: {
        "diagnostic_weights": np.array(weights), "scales": np.array([scale])})
    with pytest.raises(ValueError, match="drifted"):
        holdout.freeze(pd.DataFrame([dict(tier=1, y=1, year=2023)]), tmp_path / "frozen.json")
    assert not (tmp_path / "frozen.json").exists()


def test_committed_freeze_provenance():
    frozen = json.loads(holdout.FROZEN_PATH.read_text())
    assert frozen["weights"] == pytest.approx([0.87296870, 0.07737623], abs=1e-6)
    assert frozen["form_difference_scale"] == pytest.approx(0.09254274, abs=1e-6)
    assert frozen["freeze_time"] == "2026-10-15T07:00:00Z"
    assert frozen["fit_years"] == [2023, 2024]
    assert frozen["fit_row_count"] == 769
    assert frozen["git_commit"] == "2d5fbea"
