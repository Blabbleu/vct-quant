"""Live forecasts graded per rating pool, with a folded reliability table.

Descriptive only. The live prediction log is the project's one clean holdout,
so nothing here is fitted to it: no recalibration, no threshold chosen from
it. It answers "when the model called a favourite at 70-80%, how often did
that favourite win, and how sure can we be at this n?".

Two choices worth knowing:

* **Pools are never pooled.** Game Changers is a separate Elo pool
  (CLAUDE.md), so its graded forecasts are scored on their own, not mixed
  into the Tier-1 headline.
* **Buckets fold to the favourite.** Which team is "a" is arbitrary, so a
  0.30 forecast for a is a 0.70 call on b. Folding halves the buckets and
  doubles the n per bucket, which matters while the log is tiny. An exact
  0.5 has no favourite and is left out of the buckets (still scored).

Each bucket carries a 95% Wilson interval on the favourite's win rate, so a
3/4 bucket reads as "somewhere between 30% and 95%", not as "75%".
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Liquidity rule shared with the grader and the desk (spread <= 0.10).
MAX_SPREAD = 0.10
BUCKETS: tuple[tuple[float, float], ...] = (
    (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0),
)
LABELS = {1: "Tier 1", 2: "Tier 2", 3: "Game Changers"}
Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float | None, float | None]:
    """95% Wilson score interval for k successes in n trials."""
    if n <= 0:
        return None, None
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def _bucket_index(q: float) -> int:
    """Index into BUCKETS for a folded favourite probability q in (0.5, 1]."""
    return min(int(math.floor(q * 10 + 1e-9)) - 5, len(BUCKETS) - 1)


def _tier_key(value) -> int | None:
    return None if value is None or pd.isna(value) else int(value)


def _pool(frame: pd.DataFrame, tier: int | None) -> dict:
    y = frame.y.astype(float).to_numpy()
    p = frame.p.astype(float).to_numpy()
    q = np.maximum(p, 1 - p)
    fav_won = np.where(p > 0.5, y, 1 - y)
    called = p != 0.5

    rows = [{"lo": lo, "hi": hi, "n": 0, "won": 0, "predicted": None, "actual": None,
             "ci": [None, None]} for lo, hi in BUCKETS]
    idx = np.array([_bucket_index(v) if c else -1 for v, c in zip(q, called)], dtype=int)
    for i, row in enumerate(rows):
        m = idx == i
        n = int(m.sum())
        if not n:
            continue
        won = int(fav_won[m].sum())
        row.update(n=n, won=won, predicted=float(q[m].mean()), actual=won / n,
                   ci=list(wilson(won, n)))

    market = None
    if "p_market_a" in frame:
        pm = pd.to_numeric(frame.p_market_a, errors="coerce").to_numpy(dtype=float)
        spread = pd.to_numeric(frame.market_spread, errors="coerce").to_numpy(dtype=float)
        liquid = np.isfinite(pm) & np.isfinite(spread) & (spread <= MAX_SPREAD)
        if liquid.sum() >= 2:
            market = {"n": int(liquid.sum()),
                      "elo": _log_loss(y[liquid], p[liquid]),
                      "market": _log_loss(y[liquid], pm[liquid])}

    return {
        "tier": tier,
        "label": LABELS.get(tier, "Unknown tier") if tier is not None else "Unknown tier",
        "n": int(len(y)),
        "log_loss": _log_loss(y, p),
        "brier": float(((p - y) ** 2).mean()),
        "favourite": {"calls": int(called.sum()), "won": int(fav_won[called].sum())},
        "coin_flips": int((~called).sum()),
        "buckets": rows,
        "market": market,
    }


def live_breakdown(frame: pd.DataFrame) -> dict:
    """Per-pool scores for graded rows with columns y, p, tier (+ market cols).

    `y` is 1 if team a won; `p` the logged pre-start probability for team a.
    Rows with a non-finite probability raise instead of being silently dropped.
    """
    out = {"buckets": [[lo, hi] for lo, hi in BUCKETS], "tiers": []}
    if frame.empty:
        return out
    p = pd.to_numeric(frame.p, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(p).all() or (p < 0).any() or (p > 1).any():
        raise ValueError("graded probabilities must be finite and in [0, 1]")
    # Plain Python keys: a pandas map would turn None back into NaN (NaN != NaN).
    keys = [_tier_key(v) for v in frame.tier.tolist()]
    order = sorted(set(keys), key=lambda k: (k is None, k if k is not None else 0))
    for key in order:
        mask = np.array([k == key for k in keys], dtype=bool)
        out["tiers"].append(_pool(frame[mask], key))
    return out
