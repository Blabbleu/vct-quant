import numpy as np
import pandas as pd
import pytest

from vct_quant import dashboard, live_checkpoint


def test_graded_shadow_uses_elo_for_promoted_rows(monkeypatch, tmp_path):
    (tmp_path / "prediction_log.parquet").touch()
    monkeypatch.setattr(dashboard, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(pd, "read_parquet", lambda path: pd.DataFrame())
    monkeypatch.setattr(dashboard, "load_logos", lambda: {})
    monkeypatch.setattr(dashboard, "load_tags", lambda: {})
    monkeypatch.setattr(live_checkpoint, "grand_final_id", lambda: 754737)
    promoted = pd.DataFrame({
        "match_id": [1, 2, 3, 4],
        "scheduled_at": pd.date_range("2026-01-01", periods=4, tz="UTC"),
        "tier": [1, 1, 1, 1], "y": [1, 0, 1, 0],
        "p_team_a_win_ensemble": [0.7, 0.3, 0.7, np.nan],
        "p_team_a_win": [0.6, 0.4, 0.7, 0.2],
        "p_team_a_win_elo": [np.nan, np.nan, 0.6, 0.2],
        "p_market_a": [np.nan] * 4, "market_spread": [np.nan] * 4,
        "team_a_name": ["A"] * 4, "team_b_name": ["B"] * 4,
        "team_a_key": ["a"] * 4, "team_b_key": ["b"] * 4,
    })
    unpromoted = promoted.drop(columns="p_team_a_win_elo").copy()
    unpromoted.loc[2, "p_team_a_win"] = 0.6
    current = {"value": promoted}

    def forecasts(_log):
        result = current["value"].copy()
        result.attrs["logged"] = 4
        return result

    monkeypatch.setattr(dashboard, "graded_forecasts", forecasts)
    first = dashboard.graded_log()["shadows"]["ensemble"]
    current["value"] = unpromoted
    second = dashboard.graded_log()["shadows"]["ensemble"]
    assert first["n"] == second["n"] == 3
    for key in ("elo", "shadow", "t"):
        assert first[key] == pytest.approx(second[key])
