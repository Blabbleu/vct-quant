import numpy as np
import pandas as pd
import pytest

from research.asof_economy_stack import align, design, fit_frozen, forecast, verdict


def sample():
    rng = np.random.default_rng(1016)
    n = 80
    return pd.DataFrame({
        "year": np.repeat([2023, 2024, 2025, 2026], 20),
        "tier": np.ones(n, dtype=int),
        "y": rng.integers(0, 2, n),
        "p_elo": rng.uniform(.2, .8, n),
        "prior_economy_rows_a": np.full(n, 3),
        "prior_economy_rows_b": np.full(n, 3),
        "full_buy_diff": rng.normal(0, .2, n),
        "pistol_diff": rng.normal(0, .2, n),
    })


def test_fallback_on_either_short_history_or_either_missing_difference():
    frame = sample().iloc[:6].copy().reset_index(drop=True)
    frame.loc[1, "prior_economy_rows_a"] = 2
    frame.loc[2, "prior_economy_rows_b"] = 2
    frame.loc[3, "full_buy_diff"] = np.nan
    frame.loc[4, "pistol_diff"] = np.nan

    class FixedModel:
        def predict_proba(self, x):
            assert len(x) == 2
            return np.tile([.1, .9], (len(x), 1))

    p, model_n = forecast(frame, FixedModel())
    assert model_n == 2
    np.testing.assert_array_equal(p[[1, 2, 3, 4]], frame.p_elo.to_numpy()[[1, 2, 3, 4]])
    np.testing.assert_array_equal(p[[0, 5]], [.9, .9])


@pytest.mark.parametrize("values, expected", [
    ([(2.1, .02, .02, .001), (2.2, .03, .03, .001)], "WIN"),
    ([(2.1, .04, .03, .001), (2.2, .03, .03, .001)], "NOT PROVEN"),
    ([(1.9, .02, .02, .001), (2.2, .03, .03, .001)], "NOT PROVEN"),
    ([(2.1, .02, .02, .001), (-.2, .03, .03, -.001)], "REJECTED"),
])
def test_verdict_uses_both_years_mean_gain_and_ece(values, expected):
    years = {year: {"stack": dict(zip(("t", "ece", "elo_ece", "gain_mean"), row))}
             for year, row in zip((2025, 2026), values)}
    assert verdict(years) == expected


def test_fit_uses_only_eligible_2023_and_2024_rows():
    frame = sample()
    original = fit_frozen(frame)
    changed = frame.copy()
    changed.loc[changed.year.ge(2025), "y"] = 1 - changed.loc[changed.year.ge(2025), "y"]
    changed.loc[changed.year.ge(2025), "full_buy_diff"] = 100.
    changed.loc[changed.year.ge(2025), "pistol_diff"] = -100.
    revised = fit_frozen(changed)
    np.testing.assert_array_equal(original.intercept_, revised.intercept_)
    np.testing.assert_array_equal(original.coef_, revised.coef_)


@pytest.mark.parametrize("column, value", [
    ("p_elo", np.nan), ("p_elo", np.inf),
    ("full_buy_diff", np.nan), ("full_buy_diff", -np.inf),
    ("pistol_diff", np.nan), ("pistol_diff", np.inf),
])
def test_design_rejects_nonfinite_inputs(column, value):
    frame = sample().iloc[:1].copy()
    frame.loc[frame.index[0], column] = value
    with pytest.raises(ValueError, match="nonfinite"):
        design(frame)


def test_alignment_requires_exact_unique_match_ids():
    elo = pd.DataFrame({"match_id": [1, 2], "p_elo": [.4, .6]})
    features = pd.DataFrame({"match_id": [2, 1], "full_buy_diff": [.1, -.1]})
    assert align(elo, features).match_id.tolist() == [1, 2]
    for bad in (features.assign(match_id=[1, 1]),
                features.assign(match_id=[1, 3]),
                features.assign(match_id=[1, np.nan])):
        with pytest.raises(ValueError):
            align(elo, bad)
