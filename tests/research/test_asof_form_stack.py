import numpy as np
import pandas as pd
import pytest

from research.asof_form_stack import align, design, fit_frozen, verdict
from research.stack_ensemble import fit as stack_fit


def sample():
    rng = np.random.default_rng(37)
    n = 80
    return pd.DataFrame({
        "year": np.repeat([2023, 2024, 2025, 2026], 20),
        "tier": np.ones(n, dtype=int),
        "y": rng.integers(0, 2, n),
        "p_elo": rng.uniform(.2, .8, n),
        "player_form_diff": rng.normal(0, .4, n),
        "rating_coverage_a": rng.choice([0., .4, .8, 1.], n),
        "rating_coverage_b": rng.choice([0., .6, 1.], n),
        "prior_lineup_a": rng.integers(0, 2, n).astype(bool),
        "prior_lineup_b": rng.integers(0, 2, n).astype(bool),
        "player_form_missing_a": rng.integers(0, 2, n).astype(bool),
        "player_form_missing_b": rng.integers(0, 2, n).astype(bool),
    })


def test_test_year_outcomes_and_features_do_not_enter_frozen_fit():
    frame = sample()
    original = fit_frozen(frame)
    altered = frame.copy()
    test = altered.year.ge(2025)
    altered.loc[test, "y"] = 1 - altered.loc[test, "y"]
    altered.loc[test, "p_elo"] = .97
    altered.loc[test, "player_form_diff"] = 1000.
    altered.loc[test, "rating_coverage_a"] = 0.
    altered.loc[test, "rating_coverage_b"] = 1.
    altered.loc[test, "prior_lineup_a"] = True
    altered.loc[test, "prior_lineup_b"] = False
    altered.loc[test, "player_form_missing_a"] = True
    altered.loc[test, "player_form_missing_b"] = False
    revised = fit_frozen(altered)
    for key in original:
        np.testing.assert_array_equal(original[key], revised[key])


def test_scaling_uses_fit_population_sd_without_centering_and_missing_form_is_zero():
    frame = sample()
    frame.loc[0, "player_form_diff"] = np.nan
    frame.loc[frame.year.le(2024), "player_form_diff"] += 2.
    x = design(frame)
    assert x[0, 1] == 0.
    fit = frame.year.le(2024)
    frozen = fit_frozen(frame)
    expected = x[fit.to_numpy(), 1:].std(axis=0, ddof=0)
    np.testing.assert_allclose(frozen["scales"], expected)
    scaled = x.copy()
    scaled[:, 1:] /= frozen["scales"]
    expected_weights = stack_fit(scaled[fit.to_numpy()], frame.loc[fit, "y"].to_numpy(float),
                                 anchor=np.array([1., 0., 0., 0., 0.]))
    np.testing.assert_allclose(frozen["weights"], expected_weights)
    nonzero = np.flatnonzero(x[:, 1])[-1]
    assert scaled[nonzero, 1] == pytest.approx(x[nonzero, 1] / expected[0])
    assert scaled[fit.to_numpy(), 1].mean() != pytest.approx(0.)


def test_zero_fit_sd_is_left_unscaled():
    frame = sample()
    frame.loc[frame.year.le(2024), "prior_lineup_a"] = True
    frame.loc[frame.year.le(2024), "prior_lineup_b"] = False
    assert fit_frozen(frame)["scales"][2] == 1.


@pytest.mark.parametrize("stats,expected", [
    ([(2.01, .02, .02), (2.1, .03, .04)], "WIN"),
    ([(2.0, .02, .02), (2.1, .03, .04)], "NOT PROVEN"),
    ([(2.1, .03, .04), (.1, .02, .02)], "NOT PROVEN"),
    ([(2.1, .02, .02), (0., .02, .02)], "REJECTED"),
    ([(2.1, .02, .02), (-.1, .02, .02)], "REJECTED"),
])
def test_verdict_uses_both_years_and_calibration(stats, expected):
    years = {year: {"stack": {"t": t, "ece": ece, "elo_ece": elo_ece}}
             for year, (t, ece, elo_ece) in zip((2025, 2026), stats)}
    assert verdict(years) == expected


def test_alignment_refuses_mismatched_duplicate_null_and_reversed_ids():
    elo = pd.DataFrame({"match_id": [1, 2], "team_a": ["A", "C"], "team_b": ["B", "D"], "p_elo": [.6, .4]})
    form = elo[["match_id", "team_a", "team_b"]].copy()
    assert align(elo, form).match_id.tolist() == [1, 2]
    bad = [form.assign(match_id=[1, 3]), form.assign(match_id=[1, 1]),
           form.assign(match_id=[1, np.nan]), form.assign(team_a=["B", "C"])]
    for changed in bad:
        with pytest.raises(ValueError):
            align(elo, changed)
    with pytest.raises(ValueError):
        align(pd.concat([elo, elo.iloc[[0]]], ignore_index=True), form)
