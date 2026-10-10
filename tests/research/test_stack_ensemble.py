import numpy as np
import pandas as pd
import pytest

from research.stack_ensemble import align, fit, logits, predict, sigmoid


def test_fit_recovers_known_weights():
    rng = np.random.default_rng(51)
    x = rng.normal(size=(100000, 3))
    truth = np.array([.7, .4, -.25])
    y = rng.binomial(1, sigmoid(x @ truth))
    np.testing.assert_allclose(fit(x, y), truth, atol=.035)


def test_equal_inputs_recover_elo():
    p = np.array([.1, .35, .5, .73, .92])
    x = np.column_stack([logits(p)] * 3)
    y = np.array([0., 1., 0., 1., 1.])
    w = fit(x, y)
    np.testing.assert_allclose(predict(x, w), p)
    np.testing.assert_allclose(predict(x, np.array([1., 0., 0.])), p)


def test_no_intercept_side_swap_complements_probability():
    x = logits(np.array([[.2, .65, .8], [.7, .3, .9]]))
    w = np.array([.7, .2, -.1])
    np.testing.assert_allclose(predict(-x, w), 1-predict(x, w))


def test_misaligned_match_ids_raise():
    a = pd.DataFrame({"match_id":[1,2],"y":[0.,1.],"p_elo":[.2,.8]})
    b = pd.DataFrame({"match_id":[1,3],"y":[0.,1.],"p_rs":[.2,.8]})
    c = pd.DataFrame({"match_id":[1,2],"y":[0.,1.],"p_ls":[.2,.8]})
    with pytest.raises(ValueError, match="misaligned"):
        align(a,b,c)
