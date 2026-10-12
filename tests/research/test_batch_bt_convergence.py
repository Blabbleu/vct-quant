"""Regression tests for the numerical audit, independent of the live database."""
import numpy as np
import pandas as pd

from research import batch_bt
from research.batch_bt_convergence import (
    GRAD_TOL, POST_AUDIT_OPTIONS, fit_details, frozen_replay_sample,
    run_pass, select_buckets, summarize,
)


def fixture_frame(days, scores, tiers=None):
    n = len(days)
    return pd.DataFrame({
        "match_id": np.arange(1, n+1),
        "completed_at": pd.to_datetime(days, utc=True),
        "team_a": [f"a{i}" for i in range(n)],
        "team_b": [f"b{i}" for i in range(n)],
        "score_a": scores,
        "maps_a": [2 if s == 1 else 1 for s in scores],
        "maps_b": [1 if s == 1 else 2 for s in scores],
        "tier": np.ones(n, dtype=int) if tiers is None else tiers,
    })


def test_low_cap_detects_unconverged_fit_and_refit_improves():
    rng = np.random.default_rng(7)
    nteams = 16
    a = np.repeat(np.arange(nteams), nteams)
    b = np.tile(np.arange(nteams), nteams)
    keep = a != b
    a, b = a[keep], b[keep]
    trials = np.full(len(a), 3.0)
    success = rng.integers(0, 4, len(a)).astype(float)
    age = rng.integers(0, 365, len(a))
    start = np.zeros(nteams)
    _, capped = fit_details(a, b, success, trials, age, nteams, start,
                            {"maxiter": 1, "ftol": 1e-7, "gtol": 1e-4})
    _, converged = fit_details(a, b, success, trials, age, nteams, start,
                               POST_AUDIT_OPTIONS)
    assert capped["iterations"] == 1
    assert capped["max_gradient"] > GRAD_TOL
    assert converged["max_gradient"] <= GRAD_TOL
    assert converged["objective"] < capped["objective"]
    assert converged["max_gradient"] < capped["max_gradient"]


def test_date_only_first_median_last_survives_outcome_flip():
    days = [f"{year}-01-{day:02d}" for year in range(2023, 2027)
            for day in (1, 4, 7, 10, 13)]
    frame = fixture_frame(days, [0, 1] * 10)
    selected = select_buckets(frame)
    flipped = frame.copy()
    flipped["score_a"] = 1 - flipped.score_a
    assert select_buckets(flipped) == selected
    for year, buckets in selected.items():
        possible = np.unique(
            (pd.to_datetime(frame.loc[pd.to_datetime(frame.completed_at).dt.year == year,
                                       "completed_at"], utc=True).to_numpy(dtype="datetime64[D]")
             .astype(np.int64) // 3))
        assert buckets == (int(possible[0]), int(possible[2]), int(possible[-1]))


def test_same_bucket_result_excluded_and_forecast_unchanged():
    frame = fixture_frame(["2025-01-01", "2025-01-04", "2025-01-04"], [1, 1, 0])
    selected = {2025: (int(pd.Timestamp("2025-01-04").to_datetime64().astype("datetime64[D]").astype(int)//3),)}
    records, arrays = frozen_replay_sample(frame, selected)
    np.testing.assert_allclose(arrays[-2], batch_bt.replay(frame, batch_bt.FROZEN_CELL), atol=1e-12)
    record = records[0]
    assert record.eligible_indices.tolist() == [0]
    assert np.all(arrays[0][record.eligible_indices] < record.cutoff_day)
    flipped = frame.copy()
    flipped.loc[1, "score_a"] = 0
    flipped.loc[1, "maps_a"] = 1
    flipped.loc[1, "maps_b"] = 2
    changed, _ = frozen_replay_sample(flipped, selected)
    np.testing.assert_allclose(record.probabilities, changed[0].probabilities, atol=0)
    rows = run_pass(records, arrays, POST_AUDIT_OPTIONS)
    assert rows[0]["n_training"] == 1


def test_inconclusive_when_any_reference_gradient_fails():
    rows = [{"year": 2025, "original": {"iterations": 20, "success": False,
             "max_gradient": .1}, "reference": {"max_gradient": 2e-5},
             "absolute_changes": [.00001]}]
    summary, verdict = summarize(rows)
    assert summary["overall"]["reference_unconverged"] == 1
    assert verdict == "INCONCLUSIVE"
