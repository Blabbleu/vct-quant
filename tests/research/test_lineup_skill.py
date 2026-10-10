"""Offline checks for the ADF replay."""
import copy
import numpy as np
import pytest
from research.lineup_skill import Config, adf_update, advance_idle, model_lab, predict_map, replay


CFG = Config(beta=8, sigma0=8, tau=.5, per_map=False)
A = [f"a{i}" for i in range(5)]
B = [f"b{i}" for i in range(5)]


def state():
    return {p: (0.0, 64.0, 0.0) for p in A + B}


def test_adf_direction_and_variance():
    s = state()
    adf_update(s, A, B, True, CFG)
    assert all(s[p][0] > 0 and s[p][1] < 64 for p in A)
    assert all(s[p][0] < 0 and s[p][1] < 64 for p in B)


def test_idle_inflates_variance():
    s = state()
    advance_idle(s, A, 10.0, CFG)
    assert all(s[p][1] == 64 + 10 * CFG.tau**2 for p in A)


def test_probability_symmetry():
    s = state()
    adf_update(s, A, B, True, CFG)
    pa, pb = predict_map(A, B, s, CFG), predict_map(B, A, s, CFG)
    assert np.isclose(pa + pb, 1)
    assert np.isclose(model_lab.p_series(pa, 3) + model_lab.p_series(pb, 3), 1)


@pytest.mark.parametrize("per_map", [False, True])
def test_no_lookahead(per_map):
    d = {"y": np.array([1., 1.]), "year": np.array([2023, 2023]),
         "tier": np.array([1, 1]), "lineup_a": [A, A], "lineup_b": [B, B],
         "days": np.array([1., 2.]), "best_of": np.array([3, 3]),
         "maps_a": np.array([2., 2.]), "maps_b": np.array([0., 0.])}
    base = np.array([.5, .5])
    cfg = Config(beta=8, sigma0=8, tau=.5, per_map=per_map)
    first = replay(d, cfg, base)
    changed = copy.deepcopy(d)
    changed["y"][0] = 0.
    changed["maps_a"][0], changed["maps_b"][0] = 0., 2.
    second = replay(changed, cfg, base)
    assert first[0] == second[0]
    assert first[1] != second[1]
