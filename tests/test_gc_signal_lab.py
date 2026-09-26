import numpy as np
import pytest

from scripts import gc_signal_lab as lab
from vct_quant.features.ratings import compute_elo


def test_replay_matches_compute_elo_at_defaults():
    a = ["x", "y", "x", "z", "y"]
    b = ["y", "z", "z", "x", "x"]
    s = [1.0, 0.5, 2 / 3, 0.0, 1 / 3]
    ref = [r["p_a_win"] for r in compute_elo(zip(range(5), a, b, s), k=192.0)[0]]
    assert np.allclose(lab.replay(a, b, s, 192.0), ref)


def test_newcomer_seed_is_offset_from_pool_mean():
    # first two teams start at BASE; after game 1 a=1532, b=1468, mean 1500
    p = lab.replay(["a", "new"], ["b", "a"], [1.0, 0.5], 64.0, delta=-100.0)
    assert p[0] == pytest.approx(0.5)
    assert p[1] == pytest.approx(1 / (1 + 10 ** ((1532 - 1400) / 400)))


def test_newcomer_seed_tracks_mean_after_non_zero_sum_seeding():
    # game 2 seeds c at 1400 -> mean of {a 1532, b 1468, c 1400} drops
    p = lab.replay(["a", "c", "d"], ["b", "b", "b"], [1.0, 0.5, 0.5], 64.0, delta=-100.0)
    e2 = 1 / (1 + 10 ** ((1468 - 1400) / 400))
    c = 1400 + 64 * (0.5 - e2)
    b = 1468 - 64 * (0.5 - e2)
    mean = (1532 + b + c) / 3
    assert p[2] == pytest.approx(1 / (1 + 10 ** ((b - (mean - 100)) / 400)))


def test_two_newcomers_share_the_same_seed():
    p = lab.replay(["a", "c"], ["b", "d"], [1.0, 1.0], 64.0, delta=-200.0)
    assert p[1] == pytest.approx(0.5)


def test_provisional_multiplier_is_per_side():
    # a has 1 prior game (provisional, K*3), b has none; with provisional=1 only
    # b is provisional in game 2
    p = lab.replay(["a", "a"], ["c", "b"], [1.0, 1.0], 10.0, mult=3.0, provisional=1)
    # game 1 both provisional: a = 1500 + 30*0.5 = 1515
    e = 1 / (1 + 10 ** (-15 / 400))
    assert p[1] == pytest.approx(e)


def test_select_prefers_reference_on_ties():
    losses = {c: 1.0 for c in lab.configs()}
    assert lab.select(losses) == lab.REFERENCE
    other = ("B", 64.0, 0.0, 1.0)
    losses[other] = 0.9
    assert lab.select(losses) == other


def test_test_stage_refuses_reference():
    with pytest.raises(ValueError):
        lab.test(None, lab.REFERENCE)


def test_config_grid_is_as_frozen():
    cfgs = lab.configs()
    assert len(cfgs) == 11 + 11 + 6 * 5 + 3 * 5
    assert all(c[2] == 0.0 for c in cfgs if c[0] != "N")
    assert lab.REFERENCE in cfgs and lab.PRODUCTION in cfgs
    assert len(set(cfgs)) == len(cfgs)
