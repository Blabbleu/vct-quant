"""BT stack alignment and frozen split, without the live database."""
import numpy as np
import pandas as pd
import pytest

from research.stack_bt import align_bt, fit_frozen
from research.stack_ensemble import logits, predict


def components():
    stack = pd.DataFrame({"match_id": [1, 2], "y": [1., 0.], "tier": [1, 1],
                          "year": [2023, 2025], "p_elo": [.6, .4],
                          "p_rs": [.6, .45], "p_ls": [.6, .35]})
    bt = pd.DataFrame({"match_id": [2, 1], "team_a": ["C", "A"],
                       "team_b": ["D", "B"], "score_a": [0., 1.],
                       "p_elo": [.4, .6]})
    sides = bt[["match_id", "team_a", "team_b"]].copy()
    sides["y"] = bt.score_a
    return stack, bt, {1: .55, 2: .42}, sides


def test_join_uses_ids_and_preserves_team_a_probability():
    out = align_bt(*components())
    assert out.match_id.tolist() == [1, 2]
    np.testing.assert_allclose(out.p_bt, [.55, .42])


@pytest.mark.parametrize("change, message", [
    (lambda s, b, p, d: p.pop(2), "missing or extra"),
    (lambda s, b, p, d: b.__setitem__("match_id", [1, 1]), "duplicate"),
    (lambda s, b, p, d: d.__setitem__("team_a", ["wrong", "A"]), "orientation"),
    (lambda s, b, p, d: b.__setitem__("score_a", [1., 1.]), "labels"),
    (lambda s, b, p, d: b.__setitem__("p_elo", [.4, .7]), "Elo"),
    (lambda s, b, p, d: p.__setitem__(2, np.nan), "finite"),
])
def test_invalid_bt_join_raises(change, message):
    parts = components()
    change(*parts)
    with pytest.raises(ValueError, match=message):
        align_bt(*parts)


def test_fallback_to_elo_when_all_component_inputs_equal():
    frame = pd.DataFrame({"tier": [1, 1, 1], "year": [2023, 2024, 2025],
                          "y": [1., 0., 1.], "p_elo": [.3, .6, .7]})
    for name in ("p_rs", "p_ls", "p_bt"):
        frame[name] = frame.p_elo
    prior, four = fit_frozen(frame)
    np.testing.assert_allclose(predict(logits(frame[["p_elo", "p_rs", "p_ls"]].to_numpy()), prior), frame.p_elo)
    np.testing.assert_allclose(predict(logits(frame[["p_elo", "p_rs", "p_ls", "p_bt"]].to_numpy()), four), frame.p_elo)


def test_held_out_labels_cannot_enter_weight_fitting():
    rng = np.random.default_rng(19)
    n = 80
    frame = pd.DataFrame({"tier": np.ones(n, int),
                          "year": np.repeat([2023, 2024, 2025, 2026], n // 4),
                          "y": rng.integers(0, 2, n).astype(float)})
    for name in ("p_elo", "p_rs", "p_ls", "p_bt"):
        frame[name] = rng.uniform(.15, .85, n)
    original = fit_frozen(frame)
    changed = frame.copy()
    changed.loc[changed.year >= 2025, "y"] = 1 - changed.loc[changed.year >= 2025, "y"]
    for a, b in zip(original, fit_frozen(changed), strict=True):
        np.testing.assert_array_equal(a, b)
