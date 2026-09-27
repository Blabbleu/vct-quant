import math

import numpy as np
import pandas as pd
import pytest

from scripts import gc_side_lab
from vct_quant.features import build
from vct_quant.models import shadow


def _gc_history():
    return pd.DataFrame({
        "match_id": [1, 2, 3, 4],
        "tier": [3, 3, 3, 3],
        "year": [2025] * 4,
        "team_a": ["x", "y", "x", "z"],
        "team_b": ["y", "z", "z", "x"],
        "score_a": [1.0, 0.0, 1.0, 0.0],
        "maps_a": [2, 1, 2, 0],
        "maps_b": [0, 2, 1, 2],
    })


def _fixtures():
    return pd.DataFrame({"team_a_key": ["x", "new"], "team_b_key": ["z", "y"],
                         "tier": [3, 3]})


def test_gc_side_ratings_match_lab_replay():
    h = _gc_history()
    ratings = shadow.side_advantage_ratings(h)
    # lab replay's pre-match p for a synthetic 5th match x vs z equals shadow's
    s = build.margin_signal(h).to_numpy()
    p = gc_side_lab.replay(list(h.team_a) + ["x"], list(h.team_b) + ["z"],
                           list(s) + [0.5], shadow.GC_SIDE_K, shadow.GC_SIDE_H)
    q = shadow.gc_side_probability(_fixtures().iloc[:1], h).iloc[0]
    assert q == pytest.approx(p[-1])
    assert set(ratings) == {"x", "y", "z"}


def test_gc_side_unrated_team_gets_base_plus_advantage():
    q = shadow.gc_side_probability(
        pd.DataFrame({"team_a_key": ["new"], "team_b_key": ["other"]}), _gc_history())
    assert q.iloc[0] == pytest.approx(1 / (1 + 10 ** (-shadow.GC_SIDE_H / 400)))


def test_gc_shadow_is_enabled_by_approval_and_adds_only_shadow_column():
    assert shadow.GC_SIDE_SHADOW is True
    f = _fixtures()
    out = shadow.gc_shadow_columns(f, _gc_history())
    assert "p_team_a_win_gc_side" in out
    assert list(out.columns) == list(f.columns) + ["p_team_a_win_gc_side"]
    assert out.p_team_a_win_gc_side.between(0, 1).all()
    pd.testing.assert_frame_equal(shadow.gc_shadow_columns(f, _gc_history(), enabled=False), f)


def test_gc_shadow_on_adds_column_only():
    f = _fixtures()
    out = shadow.gc_shadow_columns(f, _gc_history(), enabled=True)
    assert list(out.columns) == list(f.columns) + ["p_team_a_win_gc_side"]
    assert out.p_team_a_win_gc_side.between(0, 1).all()
    empty = shadow.gc_shadow_columns(f, _gc_history().iloc[:0], enabled=True)
    assert empty.p_team_a_win_gc_side.isna().all()


def _fixture_frame():
    return pd.DataFrame({
        "match_id": [9], "tier": [3], "team_a_key": ["x"], "team_b_key": ["z"],
        "event_name": ["Game Changers 2026"], "event_series": ["Upper Semifinal"],
        "best_of": [3],
    })


def test_predict_upcoming_gc_primary_unchanged_by_flag(monkeypatch):
    h = _gc_history()
    monkeypatch.setattr(shadow, "GC_SIDE_SHADOW", False)
    off = build.predict_upcoming(_fixture_frame(), h)
    monkeypatch.setattr(shadow, "GC_SIDE_SHADOW", True)
    on = build.predict_upcoming(_fixture_frame(), h)
    assert "p_team_a_win_gc_side" not in off
    assert "p_team_a_win_gc_side" in on
    for col in off.columns:
        a, b = off[col].iloc[0], on[col].iloc[0]
        if isinstance(a, float) and math.isnan(a):
            assert isinstance(b, float) and math.isnan(b)
        else:
            assert a == b, col
    assert not np.isclose(on.p_team_a_win_gc_side.iloc[0], on.p_team_a_win.iloc[0])


def test_official_pool_never_gets_gc_shadow(monkeypatch):
    monkeypatch.setattr(shadow, "GC_SIDE_SHADOW", True)
    h = _gc_history().assign(tier=1)
    f = _fixture_frame().assign(tier=1)
    out = build.predict_upcoming(f, h)
    assert "p_team_a_win_gc_side" not in out
