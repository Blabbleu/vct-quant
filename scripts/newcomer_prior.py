"""What rating should a team get on its first Tier-1 match?

    python scripts/newcomer_prior.py

VCT 2027 puts 4 open-qualifier teams into every 12-team Kickoff, and teams move
in and out of Cups all season, so first-time Tier-1 teams become far more
common. Production starts every newcomer at 1500. 2023-26 Ascension promotions
are the closest precedent. Tuned on 2023-24, scored on 2025-26, paired t against
production, on newcomer matches and on all matches.

  fixed      newcomer starts at a constant c
  tier2      a separate Tier-2 Elo pool runs alongside; the newcomer starts at
             c + beta * (tier2_rating - 1500), so a dominant Challengers/Ascension
             team enters higher than one that scraped through
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from model_lab import load  # noqa: E402

from vct_quant.features.build import BEST_K  # noqa: E402

BASE = 1500.0
NEW_WINDOW = 10  # a "newcomer match" = one of the team's first N Tier-1 matches


def run(d, c=1500.0, beta=0.0, k2=32.0):
    t1: dict = {}
    t2: dict = {}
    n1: dict = {}
    out = np.empty(len(d["y"]))
    newcomer = np.zeros(len(d["y"]), bool)
    for i in range(len(out)):
        a, b, tier = d["team_a"][i], d["team_b"][i], d["tier"][i]
        s = d["signal"][i]
        if tier == 1:
            for x in (a, b):
                if x not in t1:
                    # Founding teams (first seen before the 2023 restructure) keep
                    # the 1500 base; only later entrants get the tested prior.
                    # Applying c to everyone would just shift the whole pool.
                    late = d["year"][i] >= 2023
                    t1[x] = (c + beta * (t2.get(x, BASE) - BASE)) if late else BASE
            ra, rb = t1[a], t1[b]
            p = 1 / (1 + 10 ** ((rb - ra) / 400))
            out[i] = p
            newcomer[i] = min(n1.get(a, 0), n1.get(b, 0)) < NEW_WINDOW
            delta = BEST_K * (s - p)
            t1[a], t1[b] = ra + delta, rb - delta
            n1[a] = n1.get(a, 0) + 1
            n1[b] = n1.get(b, 0) + 1
        else:
            ra, rb = t2.get(a, BASE), t2.get(b, BASE)
            p = 1 / (1 + 10 ** ((rb - ra) / 400))
            out[i] = p
            delta = k2 * (s - p)
            t2[a], t2[b] = ra + delta, rb - delta
    return out, newcomer


def loss(d, p, mask):
    y = d["y"][mask]
    q = np.clip(p[mask], 1e-12, 1 - 1e-12)
    return -(y * np.log(q) + (1 - y) * np.log(1 - q))


def t(x):
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 and x.std() else 0.0


def main() -> int:
    d = load()
    scored = (d["tier"] == 1) & (d["y"] != 0.5)
    base, newcomer = run(d)
    years = {"tune 2023-24": (2023, 2024), "test 2025-26": (2025, 2026)}
    masks = {name: scored & np.isin(d["year"], ys) for name, ys in years.items()}
    for name, m in masks.items():
        print(f"{name}: {m.sum()} scored Tier-1 matches, {(m & newcomer).sum()} involve a newcomer "
              f"(first {NEW_WINDOW} T1 matches); newcomer log loss {loss(d, base, m & newcomer).mean():.4f}"
              f" vs {loss(d, base, m & ~newcomer).mean():.4f} otherwise")

    # Mean pre-match rating of established teams in each eval window, for scale.
    grid = [dict(c=c) for c in (1350, 1400, 1450, 1500, 1550, 1600, 1650)]
    grid += [dict(c=c, beta=bt, k2=k2) for c in (1400, 1450, 1500, 1550)
             for bt in (0.25, 0.5, 1.0) for k2 in (16.0, 32.0)]
    rows = []
    tune = masks["tune 2023-24"]
    for g in grid:
        p, _ = run(d, **g)
        rows.append((loss(d, p, tune & newcomer).mean(), loss(d, p, tune).mean(), g, p))
    rows.sort(key=lambda r: r[1])
    print("\nbest 6 by tune-period loss on ALL matches (newcomer-only loss alongside):")
    for nl, al, g, _ in rows[:6]:
        print(f"  {str(g):44} all {al:.4f}  newcomer {nl:.4f}")
    _, _, best, p = rows[0]
    print(f"\nselected: {best}")
    for name, m in masks.items():
        for label, mm in (("all", m), ("newcomer", m & newcomer)):
            diff = loss(d, base, mm) - loss(d, p, mm)
            print(f"  {name:13} {label:9} n={mm.sum():4d}  1500-prior {loss(d, base, mm).mean():.4f}"
                  f"  selected {loss(d, p, mm).mean():.4f}  paired t={t(diff):+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
