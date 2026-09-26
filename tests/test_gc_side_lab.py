import numpy as np
import pytest

from scripts import gc_side_lab as lab
from vct_quant.features.ratings import compute_elo


def test_h_zero_matches_compute_elo():
    a = ["x", "y", "x", "z"]
    b = ["y", "z", "z", "x"]
    s = [1.0, 0.5, 2 / 3, 0.0]
    ref = [r["p_a_win"] for r in compute_elo(zip(range(4), a, b, s), k=192.0)[0]]
    assert np.allclose(lab.replay(a, b, s, 192.0, 0.0), ref)


def test_side_advantage_enters_prediction_and_update():
    p = lab.replay(["a", "a"], ["b", "b"], [1.0, 1.0], 100.0, h=50.0)
    e1 = 1 / (1 + 10 ** (-50 / 400))
    assert p[0] == pytest.approx(e1)
    d = 100 * (1 - e1)
    assert p[1] == pytest.approx(1 / (1 + 10 ** ((-2 * d - 50) / 400)))


def test_select_prefers_smaller_h_on_ties():
    losses = {(192.0, 0.0): 0.5, (192.0, 10.0): 0.5, (128.0, 20.0): 0.4}
    assert lab.select(losses) == (128.0, 20.0)
    losses[(128.0, 20.0)] = 0.5
    assert lab.select(losses) == (192.0, 0.0)


def test_decide_needs_t_and_every_year():
    assert lab.decide(2.5, {2025: 0.01, 2026: 0.001})
    assert not lab.decide(2.5, {2025: 0.01, 2026: -0.001})
    assert not lab.decide(1.9, {2025: 0.01, 2026: 0.01})
    assert not lab.decide(3.0, {})


def test_test_stage_refuses_h_zero():
    with pytest.raises(ValueError):
        lab.test(None, (192.0, 0.0))
