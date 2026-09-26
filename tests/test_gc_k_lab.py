"""Unit tests for scripts/gc_k_lab.py helpers (no DB)."""
import numpy as np
import pandas as pd
import pytest

from scripts import gc_k_lab as lab


def test_pick_k_flags_grid_edges():
    grid = [16.0, 32.0, 64.0]
    assert lab.pick_k({16.0: 0.6, 32.0: 0.5, 64.0: 0.55}, grid) == (32.0, False)
    assert lab.pick_k({16.0: 0.6, 32.0: 0.55, 64.0: 0.5}, grid) == (64.0, True)
    assert lab.pick_k({16.0: 0.4, 32.0: 0.55, 64.0: 0.5}, grid) == (16.0, True)


def test_extend_grid_steps_outward_from_edge():
    assert lab.extend_grid([16.0, 32.0], 32.0) == [16.0, 32.0, 48.0]
    assert lab.extend_grid([15.0, 32.0], 15.0) == [10.0, 15.0, 32.0]


def test_paired_t_sign_positive_when_new_better():
    base = np.array([0.7, 0.6, 0.8, 0.65])
    new = base - np.array([0.01, 0.02, 0.015, 0.01])
    assert lab.paired_t(base, new) > 0
    assert np.isnan(lab.paired_t(base, base))


def test_replay_matches_production_elo_and_is_pre_match():
    df = pd.DataFrame({
        "match_id": [1, 2, 3], "team_a": ["x", "x", "y"], "team_b": ["y", "z", "z"],
        "score_a": [1.0, 0.0, 1.0], "maps_a": [2, 0, 2], "maps_b": [0, 2, 1],
    })
    p = lab.replay(df, 48.0)
    assert p[0] == pytest.approx(0.5)
    # after x beat y 2-0 (signal 1.0) at K=48, x is +24: next p vs fresh z > 0.5
    assert p[1] == pytest.approx(1 / (1 + 10 ** (-24 / 400)))
    assert len(p) == 3
