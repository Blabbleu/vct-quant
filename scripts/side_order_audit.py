"""Descriptive first-listed-side residual by year, never a model selector.

    python -m scripts.side_order_audit

Read-only. Uses the official replay for Tier 1 and the already-frozen A73/A74
GC replay for comparison. All years are already consulted: no new holdout.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd


def by_year(df: pd.DataFrame, p, tier: int) -> list[dict]:
    """Observed - expected side-1 wins on decisive, dated rows of one pool.

    z uses the sum of Bernoulli variances under independent, fixed pre-match
    probabilities. It is a descriptive scale, not a formal significance test:
    seasons, team identities and forecast calibration are dependent.
    """
    p = np.asarray(p, dtype=float)
    if len(df) != len(p):
        raise ValueError("probabilities must be aligned with match rows")
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("probabilities must be finite and within [0, 1]")
    mask = df.tier.eq(tier) & df.score_a.isin([0.0, 1.0]) & df.year.notna()
    rows = df.loc[mask].copy()
    rows["p"] = p[mask.to_numpy()]
    result = []
    for year, group in rows.groupby("year", sort=True):
        n = len(group)
        actual = float(group.score_a.mean())
        predicted = float(group.p.mean())
        variance = float((group.p * (1 - group.p)).sum())
        result.append({"year": int(year), "n": n, "actual": actual,
                       "predicted": predicted, "residual": actual - predicted,
                       "z": ((actual - predicted) * n / np.sqrt(variance))
                       if variance > 0 else None})
    return result


def orientation_counts(df: pd.DataFrame, feed: pd.DataFrame, tier: int) -> dict[int, dict]:
    """Cross-check canonical order against archived event-feed order by ID.

    Exact case-insensitive names only; aliases are deliberately unmatched.
    An archived completed feed is post-match evidence, not proof of pre-start
    orientation. `feed` must have one latest valid row per match ID.
    """
    if feed.match_id.duplicated().any():
        raise ValueError("feed match IDs must be unique")
    joined = df[df.tier.eq(tier) & df.year.notna()].merge(
        feed[["match_id", "name_a", "name_b"]], on="match_id", how="left", validate="many_to_one")
    result: dict[int, dict] = {}
    for year, group in joined.groupby("year", sort=True):
        counts = dict.fromkeys(("absent", "same", "flipped", "unmatched"), 0)
        for row in group.itertuples(index=False):
            if not isinstance(row.name_a, str) or not isinstance(row.name_b, str):
                label = "absent"
            else:
                stored = (str(row.team_a_name).strip().casefold(),
                          str(row.team_b_name).strip().casefold())
                observed = (row.name_a.strip().casefold(), row.name_b.strip().casefold())
                label = ("same" if stored == observed else
                         "flipped" if stored == observed[::-1] else "unmatched")
            counts[label] += 1
        result[int(year)] = counts
    return result


def main() -> None:
    from vct_quant.features.build import BEST_K, TIER_2_WEIGHT, margin_signal, match_sequence
    from vct_quant.features.ratings import compute_elo
    from scripts.gc_side_lab import predict
    from vct_quant.etl.normalize import _vlrgg_event_matches

    official = match_sequence(tiers=(1, 2))
    signal = margin_signal(official)
    k = np.where(official.tier.eq(1), BEST_K, BEST_K * TIER_2_WEIGHT)
    rows, _ = compute_elo(zip(official.match_id, official.team_a, official.team_b,
                              signal), k=k)
    p = np.array([row["p_a_win"] for row in rows])
    gc = match_sequence(tiers=(3,))
    feed = _vlrgg_event_matches()
    result = {"tier_1_K48": by_year(official, p, 1),
              "gc_K192_h0": by_year(gc, predict(gc, (192.0, 0.0)), 3),
              "gc_K192_h30": by_year(gc, predict(gc, (192.0, 30.0)), 3),
              "archived_feed_orientation": {
                  "tier_1": orientation_counts(official, feed, 1),
                  "gc": orientation_counts(gc, feed, 3),
              }}
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
