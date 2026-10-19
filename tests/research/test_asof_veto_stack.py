import numpy as np
import pandas as pd
import pytest

from research.asof_veto_stack import design, fit_frozen, forecast, verdict


def sample():
    rng = np.random.default_rng(1019)
    n = 80
    return pd.DataFrame({
        "year": np.repeat([2023, 2024, 2025, 2026], 20),
        "tier": np.ones(n, dtype=int),
        "y": rng.integers(0, 2, n),
        "p_elo": rng.uniform(.2, .8, n),
        "prior_draft_series_a": np.full(n, 3),
        "prior_draft_series_b": np.full(n, 3),
        "veto_edge": rng.normal(0, .2, n),
    })


def test_design_column_order():
    frame = pd.DataFrame({"p_elo": [.25, .75], "veto_edge": [.2, -.3]})
    np.testing.assert_allclose(design(frame),
                               [[np.log(1 / 3), .2], [np.log(3), -.3]])


def test_elo_fallback_for_short_history_and_nonfinite_edge():
    frame = sample().iloc[:5].copy().reset_index(drop=True)
    frame.loc[1, "prior_draft_series_a"] = 2
    frame.loc[2, "prior_draft_series_b"] = 2
    frame.loc[3, "veto_edge"] = np.nan
    frame.loc[4, "veto_edge"] = np.inf

    class FixedModel:
        def predict_proba(self, x):
            assert x.shape == (1, 2)
            return np.array([[.1, .9]])

    p, eligible_n = forecast(frame, FixedModel())
    assert eligible_n == 1
    assert p[0] == .9
    np.testing.assert_array_equal(p[1:], frame.p_elo.to_numpy()[1:])


def test_fit_uses_only_eligible_2023_and_2024_rows():
    frame = sample()
    original = fit_frozen(frame)
    changed = frame.copy()
    changed.loc[changed.year.ge(2025), "y"] = 1
    changed.loc[changed.year.ge(2025), "veto_edge"] = 1000.
    changed.loc[changed.year.ge(2025), "p_elo"] = .999
    revised = fit_frozen(changed)
    np.testing.assert_array_equal(original.intercept_, revised.intercept_)
    np.testing.assert_array_equal(original.coef_, revised.coef_)


@pytest.mark.parametrize("values, expected", [
    ([(2.1, .02, .02, .001), (2.2, .03, .03, .001)], "WIN"),
    ([(2.1, .04, .03, .001), (2.2, .03, .03, .001)], "NOT PROVEN"),
    ([(1.9, .02, .02, .001), (2.2, .03, .03, .001)], "NOT PROVEN"),
    ([(2.1, .02, .02, .001), (-.2, .03, .03, -.001)], "REJECTED"),
])
def test_verdict(values, expected):
    years = {year: {"stack": dict(zip(("t", "ece", "elo_ece", "gain_mean"), row))}
             for year, row in zip((2025, 2026), values)}
    assert verdict(years) == expected
