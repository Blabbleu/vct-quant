"""Market-implied win probabilities, matched onto model fixtures.

A Polymarket price is already a probability: $0.58 on Paper Rex means the
market prices them at 58%. There is no bookmaker margin to strip, but there is
a bid/ask spread, so the midpoint is used. Wide spreads and low volume mean a
stale or thin market -- both are kept so the grader can filter on them.
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from .entity_resolution import normalize_name

MARKET_COLUMNS = ["p_market_a", "market_spread", "market_volume", "market_slug"]


def moneylines(events: list[dict]) -> pd.DataFrame:
    """One row per open series-winner market: both names and P(first name wins)."""
    rows = []
    for event in events:
        for market in event.get("markets") or []:
            if market.get("sportsMarketType") != "moneyline" or market.get("closed"):
                continue
            names = json.loads(market.get("outcomes") or "[]")
            if len(names) != 2:
                continue
            bid, ask = market.get("bestBid"), market.get("bestAsk")
            if bid is not None and ask is not None and 0 < bid <= ask < 1:
                p, spread = (bid + ask) / 2, ask - bid
            else:
                p, spread = float(json.loads(market["outcomePrices"])[0]), np.nan
            rows.append({
                "market_slug": event.get("slug"),
                "game_start": market.get("gameStartTime"),
                "name_1": names[0], "name_2": names[1],
                "p_1": p, "spread": spread, "volume": market.get("volumeNum"),
            })
    out = pd.DataFrame(rows, columns=[
        "market_slug", "game_start", "name_1", "name_2", "p_1", "spread", "volume",
    ])
    out["game_start"] = pd.to_datetime(out.game_start, utc=True, errors="coerce")
    return out


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(str(a)), normalize_name(str(b))).ratio()


def attach_market_prices(
    fixtures: pd.DataFrame,
    markets: pd.DataFrame,
    window: pd.Timedelta = pd.Timedelta(hours=2),
    min_similarity: float = 0.6,
) -> pd.DataFrame:
    """Add p_market_a (market P(team A wins)) to each fixture that has a market.

    Names differ between vlr.gg and Polymarket ("Xi Lai Gaming" vs "XLG Gaming",
    "FENNEL GC" vs "FENNEL Female"), so a market matches a fixture only when it
    starts within `window` AND both team names are similar. Polymarket's
    outcome order is independent of team A/B, so both orientations are tried.
    ponytail: fuzzy name match; move to vlr.gg IDs if Polymarket ever exposes them.
    """
    out = fixtures.copy()
    out["p_market_a"] = np.nan
    out["market_spread"] = np.nan
    out["market_volume"] = np.nan
    out["market_slug"] = pd.Series(pd.NA, index=out.index, dtype="string")
    if markets.empty or out.empty:
        return out

    scheduled = pd.to_datetime(out.scheduled_at, utc=True, errors="coerce")
    for i, when, a, b in zip(out.index, scheduled, out.team_a_name, out.team_b_name):
        if pd.isna(when):
            continue
        best = None
        for m in markets[(markets.game_start - when).abs() <= window].itertuples():
            for flipped, (sa, sb) in (
                (False, (_similarity(a, m.name_1), _similarity(b, m.name_2))),
                (True, (_similarity(a, m.name_2), _similarity(b, m.name_1))),
            ):
                if min(sa, sb) >= min_similarity and (best is None or sa + sb > best[0]):
                    best = (sa + sb, m, flipped)
        if best:
            _, m, flipped = best
            out.loc[i, "p_market_a"] = 1 - m.p_1 if flipped else m.p_1
            out.loc[i, "market_spread"] = m.spread
            out.loc[i, "market_volume"] = m.volume
            out.loc[i, "market_slug"] = m.market_slug
    return out
