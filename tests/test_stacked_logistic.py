import numpy as np
import pandas as pd
import pytest

from scripts.benchmark_stacked_logistic import loss, metrics, predict_year, prepare


def test_prepare_excludes_draws_other_tiers_and_uses_pre_match_features():
    f = pd.DataFrame({
        "match_id": [1, 2, 3, 4], "tier": [1, 1, 2, 1],
        "year": [2022, 2023, 2023, 2023], "label": [1., 0., 0., 0.5],
        "elo_p_a_win": [.7, .3, .5, .5],
        "player_form_diff": [np.nan, .2, .1, .1],
        "churn_a": [np.nan, .4, 0., 0.], "churn_b": [np.nan, .1, 0., 0.],
        "n_prior_a": [0, 3, 1, 1], "n_prior_b": [0, 1, 1, 1],
    })
    out = prepare(f)
    assert out.match_id.tolist() == [1, 2]
    assert out.form_missing.tolist() == [1., 0.]
    assert out.form_diff.tolist() == [0., .2]
    assert out.churn_diff.tolist() == [0., pytest.approx(.3)]
    assert np.isclose(out.exp_diff.iloc[1], np.log(2))


def test_year_fit_never_reads_same_year_labels():
    rows = 30
    f = pd.DataFrame({
        "match_id": np.arange(rows),
        "year": [2022] * 20 + [2023] * 10,
        "z_elo": np.linspace(-2, 2, rows),
        "label": [0, 1] * 15,
    })
    before = predict_year(f, 2023, ["z_elo"], .3, 1.)
    f.loc[f.year.eq(2023), "label"] = 1 - f.loc[f.year.eq(2023), "label"]
    np.testing.assert_array_equal(before, predict_year(f, 2023, ["z_elo"], .3, 1.))
    f.loc[f.year.eq(2022), "label"] = 0
    f.loc[0, "label"] = 1
    assert not np.array_equal(before, predict_year(f, 2023, ["z_elo"], .3, 1.))


def test_chronology_guard_rejects_earlier_ids_in_later_year():
    f = pd.DataFrame({"match_id": [8, 7], "year": [2022, 2023],
                      "label": [0., 1.], "z_elo": [0., 1.]})
    with pytest.raises(AssertionError, match="chronology"):
        predict_year(f, 2023, ["z_elo"], .3, 0.)


def test_metrics_are_paired_on_same_matches():
    f = pd.DataFrame({"label": [1., 0., 1.], "elo_p_a_win": [.6, .6, .6]})
    p = np.array([.7, .5, .7])
    result = metrics(f, p)
    assert result["n"] == 3
    assert result["paired_t"] > 0
    assert result["elo_loss"] - result["candidate_loss"] == pytest.approx(
        np.mean(loss(f.label.to_numpy(), f.elo_p_a_win.to_numpy()) - loss(f.label.to_numpy(), p))
    )
