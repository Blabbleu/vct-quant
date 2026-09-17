import json

import numpy as np
import pandas as pd
import pytest

from vct_quant.etl.markets import attach_market_prices, moneylines


def market(names, prices, bid=None, ask=None, kind="moneyline", start="2026-09-24 09:00:00+00"):
    return {
        "sportsMarketType": kind, "closed": False, "gameStartTime": start,
        "outcomes": json.dumps(names), "outcomePrices": json.dumps(prices),
        "bestBid": bid, "bestAsk": ask, "volumeNum": 100.0,
    }


def test_moneylines_use_midpoint_and_skip_other_market_types():
    events = [{"slug": "val-tl1-pr1", "markets": [
        market(["Team Liquid", "Paper Rex"], ["0.42", "0.58"], bid=0.41, ask=0.45),
        market(["Team Liquid", "Paper Rex"], ["0.4", "0.6"], kind="child_moneyline"),
    ]}, {"slug": "val-no-book", "markets": [
        market(["A", "B"], ["0.3", "0.7"]),  # no order book: fall back to displayed price
    ]}]

    out = moneylines(events)

    assert out.market_slug.tolist() == ["val-tl1-pr1", "val-no-book"]
    assert out.p_1.tolist() == pytest.approx([0.43, 0.3])
    assert out.spread.iloc[0] == pytest.approx(0.04)
    assert np.isnan(out.spread.iloc[1])


def test_attach_matches_by_time_and_fuzzy_names_in_either_orientation():
    markets = moneylines([
        {"slug": "val-kc3-xlg", "markets": [market(["Karmine Corp", "XLG Gaming"], ["0.6", "0.4"])]},
        {"slug": "later", "markets": [market(["Karmine Corp", "XLG Gaming"], ["0.9", "0.1"],
                                             start="2026-09-26 09:00:00+00")]},
    ])
    fixtures = pd.DataFrame({
        "scheduled_at": pd.to_datetime(["2026-09-24 09:00", "2026-09-24 09:00", "2026-09-24 09:00"], utc=True),
        "team_a_name": ["Xi Lai Gaming", "Karmine Corp", "TBD"],
        "team_b_name": ["Karmine Corp", "Paper Rex", "TBD"],
    })

    out = attach_market_prices(fixtures, markets)

    assert out.p_market_a.iloc[0] == pytest.approx(0.4)  # flipped: team A is XLG
    assert out.market_slug.iloc[0] == "val-kc3-xlg"  # not the same pairing two days later
    assert out.p_market_a.iloc[1:].isna().all()  # one name wrong, or TBD: no match
