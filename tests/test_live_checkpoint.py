"""The descriptive checkpoint panel must mirror the pre-registered rule, not tune it."""

import numpy as np
import pandas as pd
import pytest

from vct_quant import live_checkpoint as lc


def test_elo_baseline_uses_raw_elo_and_falls_back_per_row():
    scored = pd.DataFrame({"p_team_a_win": [0.6, 0.4], "p_team_a_win_elo": [0.7, np.nan]})
    assert lc.elo_baseline(scored).tolist() == pytest.approx([0.7, 0.4])
    assert lc.elo_baseline(scored.drop(columns="p_team_a_win_elo")).tolist() == pytest.approx([0.6, 0.4])


def test_checkpoint_status_matches_equivalent_promoted_log():
    elo_log = _scored(8)
    elo_log.loc[7, "p_team_a_win_ensemble"] = np.nan
    promoted = elo_log.copy()
    promoted["p_team_a_win_elo"] = promoted.p_team_a_win
    promoted.loc[4:6, "p_team_a_win"] = promoted.loc[4:6, "p_team_a_win_ensemble"]
    unpromoted = elo_log.copy()
    left = lc.checkpoint_status(promoted, final_id=754737)
    right = lc.checkpoint_status(unpromoted, final_id=754737)
    assert left["checkpoint_1"]["diff"] == pytest.approx(right["checkpoint_1"]["diff"])
    assert left["checkpoint_1"]["t"] == pytest.approx(right["checkpoint_1"]["t"])


def _scored(n, ens_better=True, final_id=None, extra_after=0):
    rows = []
    base = pd.Timestamp("2026-09-26T00:00:00Z")
    for i in range(n + extra_after):
        y = i % 2
        conf = 0.58 + 0.01 * (i % 5)  # varied Elo so paired differences have spread
        p = conf if y else 1 - conf
        ens = 0.65 if ens_better else 0.55
        ens = ens if y else 1 - ens
        rows.append({"match_id": 1000 + i, "scheduled_at": base + pd.Timedelta(hours=i),
                     "y": y, "p_team_a_win": p, "p_team_a_win_ensemble": ens})
    df = pd.DataFrame(rows)
    if final_id is not None:
        df.loc[n - 1, "match_id"] = final_id
    return df


def test_grand_final_is_the_single_pinned_slot():
    assert lc.grand_final_id() == 754737


def test_awaiting_final_reports_running_pooled_score():
    out = lc.checkpoint_status(_scored(30), final_id=754737)
    c1 = out["checkpoint_1"]
    assert out["final_graded"] is False and c1["state"] == "awaiting_final"
    assert c1["n"] == 30 and c1["diff"] < 0 and c1["verdict"] == "no_worse"
    assert out["checkpoint_2"] == {"n": 30, "reached": False}


def test_too_few_matches_never_reads_as_a_pass():
    out = lc.checkpoint_status(_scored(24), final_id=754737)
    assert out["checkpoint_1"]["verdict"] == "too_few"


def test_worse_shadow_is_reported_as_worse():
    out = lc.checkpoint_status(_scored(30, ens_better=False), final_id=754737)
    assert out["checkpoint_1"]["diff"] > 0 and out["checkpoint_1"]["verdict"] == "worse"
    assert out["checkpoint_1"]["t"] < 0  # positive = shadow better


def test_checkpoint_1_freezes_at_the_graded_final():
    # 26 up to and including the final, then 10 later matches the shadow loses.
    df = _scored(26, final_id=754737)
    later = _scored(10, ens_better=False)
    later["match_id"] += 5000
    later["scheduled_at"] += pd.Timedelta(days=30)
    out = lc.checkpoint_status(pd.concat([df, later], ignore_index=True), final_id=754737)
    assert out["final_graded"] is True
    assert out["checkpoint_1"]["n"] == 26 and out["checkpoint_1"]["verdict"] == "no_worse"
    assert out["checkpoint_2"]["n"] == 36


def test_rows_without_the_shadow_are_excluded_same_row():
    df = _scored(30)
    df.loc[:4, "p_team_a_win_ensemble"] = np.nan
    out = lc.checkpoint_status(df, final_id=754737)
    assert out["n"] == 25 and out["checkpoint_1"]["n"] == 25


def test_tiny_positive_difference_is_boundary_not_pass():
    assert lc._verdict(30, 0.00001) == "boundary"
    assert lc._verdict(30, 0.0) == "no_worse"


def test_missing_column_is_empty_not_error():
    df = _scored(3).drop(columns="p_team_a_win_ensemble")
    out = lc.checkpoint_status(df, final_id=754737)
    assert out["n"] == 0 and out["checkpoint_1"]["verdict"] == "too_few"
    assert out["checkpoint_1"]["diff"] is None and out["checkpoint_1"]["t"] is None
