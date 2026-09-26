"""Live-log breakdown by pool: descriptive calibration of graded forecasts."""
import math

import numpy as np
import pandas as pd
import pytest

from vct_quant.live_calibration import BUCKETS, live_breakdown, wilson


def _frame(rows):
    return pd.DataFrame(rows, columns=["y", "p", "tier", "p_market_a", "market_spread"])


def test_pools_are_split_and_game_changers_never_mixed_into_tier_1():
    df = _frame([
        (1, 0.7, 1, None, None),
        (0, 0.4, 1, None, None),
        (1, 0.6, 3, None, None),
    ])
    out = live_breakdown(df)
    tiers = {t["tier"]: t for t in out["tiers"]}
    assert set(tiers) == {1, 3}
    assert tiers[1]["label"] == "Tier 1"
    assert tiers[3]["label"] == "Game Changers"
    assert tiers[1]["n"] == 2 and tiers[3]["n"] == 1
    expected = -(math.log(0.7) + math.log(0.6)) / 2
    assert tiers[1]["log_loss"] == pytest.approx(expected)
    assert tiers[1]["brier"] == pytest.approx((0.3 ** 2 + 0.4 ** 2) / 2)
    assert [t["tier"] for t in out["tiers"]] == [1, 3]


def test_buckets_fold_to_the_favourite_side():
    """Team a is an arbitrary orientation: 0.3 for a is 0.7 for b."""
    df = _frame([
        (0, 0.3, 1, None, None),   # b favoured at 0.7, b won
        (1, 0.72, 1, None, None),  # a favoured at 0.72, a won
        (1, 0.35, 1, None, None),  # b favoured at 0.65, a won (upset)
    ])
    t1 = live_breakdown(df)["tiers"][0]
    by_lo = {b["lo"]: b for b in t1["buckets"]}
    assert by_lo[0.7]["n"] == 2
    assert by_lo[0.7]["predicted"] == pytest.approx(0.71)
    assert by_lo[0.7]["actual"] == pytest.approx(1.0)
    assert by_lo[0.6]["n"] == 1 and by_lo[0.6]["actual"] == 0.0
    assert t1["favourite"] == {"calls": 3, "won": 2}
    # empty buckets are still listed so the chart keeps a fixed axis
    assert [b["lo"] for b in t1["buckets"]] == [lo for lo, _ in BUCKETS]
    assert by_lo[0.9]["n"] == 0 and by_lo[0.9]["actual"] is None


def test_coin_flips_are_not_favourite_calls():
    df = _frame([(1, 0.5, 1, None, None), (0, 0.8, 1, None, None)])
    t1 = live_breakdown(df)["tiers"][0]
    assert t1["coin_flips"] == 1
    assert t1["favourite"] == {"calls": 1, "won": 0}
    assert sum(b["n"] for b in t1["buckets"]) == 1
    assert t1["n"] == 2  # still scored in log loss


def test_top_bucket_includes_certainty_edge():
    df = _frame([(1, 1.0, 1, None, None), (1, 0.9, 1, None, None)])
    by_lo = {b["lo"]: b for b in live_breakdown(df)["tiers"][0]["buckets"]}
    assert by_lo[0.9]["n"] == 2


def test_market_block_needs_two_liquid_rows_in_that_pool():
    df = _frame([
        (1, 0.6, 1, 0.55, 0.05),
        (0, 0.6, 1, 0.45, 0.02),
        (1, 0.6, 1, 0.70, 0.30),   # too wide: not a price
        (1, 0.6, 3, 0.80, 0.01),   # GC has one liquid row only
    ])
    tiers = {t["tier"]: t for t in live_breakdown(df)["tiers"]}
    m = tiers[1]["market"]
    assert m["n"] == 2
    assert m["elo"] == pytest.approx(-(math.log(0.6) + math.log(0.4)) / 2)
    assert m["market"] == pytest.approx(-(math.log(0.55) + math.log(0.55)) / 2)
    assert tiers[3]["market"] is None


def test_missing_spread_is_not_liquid():
    df = _frame([(1, 0.6, 1, 0.55, None), (0, 0.6, 1, 0.45, None)])
    assert live_breakdown(df)["tiers"][0]["market"] is None


def test_unknown_or_missing_tier_goes_to_its_own_labelled_pool():
    df = _frame([(1, 0.6, None, None, None), (1, 0.6, 2, None, None)])
    labels = {t["tier"]: t["label"] for t in live_breakdown(df)["tiers"]}
    assert labels == {None: "Unknown tier", 2: "Tier 2"}


def test_empty_frame():
    assert live_breakdown(_frame([]))["tiers"] == []


def test_non_finite_probabilities_are_rejected():
    df = _frame([(1, float("nan"), 1, None, None)])
    with pytest.raises(ValueError):
        live_breakdown(df)


def test_wilson_interval():
    lo, hi = wilson(0, 0)
    assert lo is None and hi is None
    lo, hi = wilson(3, 4)
    assert 0 < lo < 0.75 < hi <= 1
    # textbook: 3/4 at 95% -> (0.301, 0.954)
    assert lo == pytest.approx(0.3006, abs=1e-3)
    assert hi == pytest.approx(0.9544, abs=1e-3)
    lo, hi = wilson(0, 5)
    assert lo == 0 and hi == pytest.approx(0.4345, abs=1e-3)
    assert np.isfinite(hi)


def test_bucket_interval_is_attached():
    df = _frame([(1, 0.72, 1, None, None), (0, 0.75, 1, None, None)])
    b = {b["lo"]: b for b in live_breakdown(df)["tiers"][0]["buckets"]}[0.7]
    assert b["ci"][0] < 0.5 < b["ci"][1]
