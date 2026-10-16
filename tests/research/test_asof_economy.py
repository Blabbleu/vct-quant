"""Small, exact as-of economy replay cases independent of the live database."""
import pandas as pd
import pytest

from research.asof_economy import coverage, replay


def matches():
    return pd.DataFrame([
        dict(match_id=10, team_a="1", team_b="name:blue", team_a_name="Red", team_b_name=" Blue ", maps_a=2, maps_b=1, tier=1, year=2023, score_a=1.0),
        dict(match_id=20, team_a="1", team_b="name:blue", team_a_name="Red", team_b_name="Blue", maps_a=2, maps_b=0, tier=1, year=2024, score_a=1.0),
        dict(match_id=30, team_a="1", team_b="name:blue", team_a_name="Red", team_b_name="Blue", maps_a=1, maps_b=2, tier=1, year=2025, score_a=0.0),
        dict(match_id=40, team_a="1", team_b="name:blue", team_a_name="Red", team_b_name="Blue", maps_a=2, maps_b=1, tier=1, year=2026, score_a=1.0),
    ])


def economy():
    return pd.DataFrame([
        dict(match_id=10, team_id=1, team_name="Red", full_buy_win_pct=60, pistol_win_pct=50),
        dict(match_id=10, team_id=None, team_name=" blue ", full_buy_win_pct=40, pistol_win_pct=20),
        dict(match_id=20, team_id=1, team_name="Red", full_buy_win_pct=80, pistol_win_pct=None),
        dict(match_id=20, team_id=None, team_name="Blue", full_buy_win_pct=None, pistol_win_pct=40),
        dict(match_id=30, team_id=1, team_name="Red", full_buy_win_pct=100, pistol_win_pct=100),
        dict(match_id=40, team_id=1, team_name="Red", full_buy_win_pct=0, pistol_win_pct=0),
    ])


def test_asof_exact_nulls_counts_name_fallback_and_future():
    features, failures = replay(matches(), economy())
    assert failures.empty
    a, b, c, d = [r for r in features.itertuples(index=False)]
    assert a.prior_economy_rows_a == a.prior_economy_rows_b == 0
    assert pd.isna(a.full_buy_win_pct_a) and pd.isna(a.pistol_win_pct_b)
    assert (b.full_buy_win_pct_a, b.pistol_win_pct_a, b.full_buy_win_pct_b, b.pistol_win_pct_b) == (60, 50, 40, 20)
    assert (b.prior_economy_rows_a, b.prior_economy_rows_b) == (1, 1)
    assert (c.full_buy_win_pct_a, c.pistol_win_pct_a, c.full_buy_win_pct_b, c.pistol_win_pct_b) == (70, 50, 40, 30)
    assert (c.prior_economy_rows_a, c.prior_economy_rows_b) == (2, 2)
    assert (c.prior_full_buy_rows_a, c.prior_pistol_rows_a, c.prior_full_buy_rows_b, c.prior_pistol_rows_b) == (2, 1, 1, 2)
    assert (d.full_buy_win_pct_a, d.pistol_win_pct_a) == (80, 75)
    assert d.prior_economy_rows_a == 3
    # Adding a later result cannot alter any previously emitted feature.
    shorter, _ = replay(matches().iloc[:3], economy().loc[economy().match_id.lt(40)])
    pd.testing.assert_frame_equal(features.iloc[:3].reset_index(drop=True), shorter.reset_index(drop=True))


def test_duplicate_is_not_double_counted_and_conflict_is_excluded():
    e = economy()
    identical = pd.concat([e, e.iloc[[0]]], ignore_index=True)
    f, failures = replay(matches(), identical)
    assert f.loc[1, "prior_economy_rows_a"] == 1
    assert failures.loc[failures.reason.eq("duplicate_rows"), "rows"].sum() == 1
    conflicting = e.iloc[[0]].copy()
    conflicting.loc[:, "full_buy_win_pct"] = 99
    f, failures = replay(matches(), pd.concat([e, conflicting], ignore_index=True))
    assert f.loc[1, "prior_economy_rows_a"] == 0
    assert failures.loc[failures.reason.eq("conflicting_duplicates_excluded"), "rows"].sum() == 2


def test_mismatches_reported_and_incomplete_series_does_not_update():
    m = matches()
    m.loc[0, "maps_b"] = None
    e = pd.concat([economy(), pd.DataFrame([
        dict(match_id=10, team_id=99, team_name="Red", full_buy_win_pct=20, pistol_win_pct=20),
        dict(match_id=20, team_id=None, team_name="Unknown", full_buy_win_pct=20, pistol_win_pct=20),
    ])], ignore_index=True)
    f, failures = replay(m, e)
    assert f.loc[1, "prior_economy_rows_a"] == 0
    assert f.loc[1, "prior_economy_rows_b"] == 0
    assert dict(failures.groupby("reason").rows.sum()) == {"team_id_mismatch": 1, "team_name_mismatch": 1}
    c = coverage(m, f, failures)
    assert c.loc[c.year.eq(2023), "join_failures"].item() == 1
    assert c.loc[c.year.eq(2024), "join_failures"].item() == 1


def test_rejects_unsorted_match_ids():
    with pytest.raises(ValueError, match="increase strictly"):
        replay(matches().iloc[[1, 0]], economy())
