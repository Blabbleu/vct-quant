import numpy as np
import pandas as pd

from research import stack_ensemble as stack
from research import stack_temperature as temperature


def synthetic_frame() -> pd.DataFrame:
    rng = np.random.default_rng(102)
    years = np.repeat([2023, 2024, 2025, 2026], 80)
    x = rng.normal(size=(len(years), 3))
    p = stack.sigmoid(x)
    y = rng.binomial(1, stack.sigmoid(x @ np.array([.8, .1, .2])))
    return pd.DataFrame({"match_id": np.arange(len(years)), "tier": 1, "year": years,
                         "y": y, "p_elo": p[:, 0], "p_rs": p[:, 1], "p_ls": p[:, 2]})


def test_temperature_one_reproduces_original_stack_and_side_swap():
    p = np.array([[.2, .65, .8], [.7, .3, .9]])
    x = stack.logits(p)
    weights = np.array([.7, .2, -.1])
    np.testing.assert_allclose(temperature.tempered_predict(x, weights, 1.0), stack.predict(x, weights))
    np.testing.assert_allclose(temperature.tempered_predict(stack.logits(1-p), weights, .8),
                               1-temperature.tempered_predict(x, weights, .8))


def test_scoring_year_labels_cannot_change_temperature_or_frozen_weights():
    frame = synthetic_frame()
    original = temperature.evaluate(frame)
    changed = frame.copy()
    changed.loc[changed.year.isin((2025, 2026)), "y"] = 1 - changed.loc[
        changed.year.isin((2025, 2026)), "y"]
    rescored = temperature.evaluate(changed)
    assert original["temperature"] == rescored["temperature"]
    assert original["calibration_losses"] == rescored["calibration_losses"]
    np.testing.assert_array_equal(original["weights_2023"], rescored["weights_2023"])
    np.testing.assert_array_equal(original["weights"], rescored["weights"])


def test_exact_temperature_tie_selects_one(monkeypatch):
    monkeypatch.setattr(temperature, "log_loss", lambda y, p: .5)
    assert temperature.freeze(synthetic_frame())[0] == 1.0
