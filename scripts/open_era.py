"""VCT 2027 readiness: how to rate teams entering an open, churning ecosystem.

    python scripts/open_era.py

2027 goes back to an open ecosystem (open qualifiers into every Kickoff and Cup,
promotion/relegation all season). The only precedent in our data is the
2021-22 open VCT era. Two questions, answered on 2022 (2021 is burn-in):

1. Newcomer prior: what should a team's first Tier-1 rating be? Production
   uses 1500 for everyone.
2. Roster inheritance: Riot's 2027 rule lets a team keep its points if it keeps
   3 of 5 players. When a team key appears for the first time and its lineup
   shares >= 3 players with one already-rated team's last lineup, start it at
   that team's rating (a rebrand or org change keeps its strength) instead of
   the prior.

Tuned on 2022 H1 (match_id order), scored on 2022 H2, then confirmed on
2023-26 newcomers. Paired t against production.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from model_lab import load  # noqa: E402

from vct_quant.features.build import BEST_K  # noqa: E402

BASE = 1500.0
NEW_WINDOW = 10


def run(d, c=BASE, inherit=0, shrink=1.0, en_bloc=False, from_year=0, until_year=9999):
    """inherit = min shared players to inherit a rating (0 = off).
    shrink = fraction of the inherited team's edge over 1500 that carries over.
    en_bloc = only inherit when the source team's latest lineup still contains
    those players, i.e. the source has not played since they left (a roster
    moving as a unit: rebrand or org change), not a continuing team losing
    players to transfers."""
    rating: dict = {}
    last_lineup: dict = {}       # team -> frozenset(players), latest known
    player_team: dict = {}       # player -> team of his latest lineup
    n: dict = {}
    out = np.full(len(d["y"]), np.nan)
    newcomer = np.zeros(len(d["y"]), bool)
    inherited = np.zeros(len(d["y"]), bool)
    for i in range(len(out)):
        if d["tier"][i] != 1:
            continue
        a, b = d["team_a"][i], d["team_b"][i]
        lineups = (frozenset(d["lineup_a"][i]), frozenset(d["lineup_b"][i]))
        for x, lu in zip((a, b), lineups):
            if x in rating:
                continue
            start = c
            if inherit and lu and from_year <= d["year"][i] <= until_year:
                counts: dict = {}
                for pl in lu:
                    t = player_team.get(pl)
                    if t is not None and t != x:
                        counts[t] = counts.get(t, 0) + 1
                if counts:
                    src, k = max(counts.items(), key=lambda kv: kv[1])
                    moved = k
                    if en_bloc:
                        moved = len(lu & last_lineup.get(src, frozenset()))
                    if k >= inherit and moved >= inherit and src in rating:
                        start = BASE + shrink * (rating[src] - BASE)
                        inherited[i] = True
            rating[x] = start
        ra, rb = rating[a], rating[b]
        p = 1 / (1 + 10 ** ((rb - ra) / 400))
        out[i] = p
        newcomer[i] = min(n.get(a, 0), n.get(b, 0)) < NEW_WINDOW
        delta = BEST_K * (d["signal"][i] - p)
        rating[a], rating[b] = ra + delta, rb - delta
        for x, lu in zip((a, b), lineups):
            n[x] = n.get(x, 0) + 1
            if lu:
                last_lineup[x] = lu
                for pl in lu:
                    player_team[pl] = x
    return out, newcomer, inherited


def loss(d, p, m):
    y = d["y"][m]
    q = np.clip(p[m], 1e-12, 1 - 1e-12)
    return -(y * np.log(q) + (1 - y) * np.log(1 - q))


def tstat(x):
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 and x.std() else 0.0


def main() -> int:
    d = load()
    scored = (d["tier"] == 1) & (d["y"] != 0.5)
    base, newcomer, _ = run(d)
    ids = d["match_id"]
    y22 = scored & (d["year"] == 2022)
    cut = np.median(ids[y22])
    periods = {
        "tune 2022 H1": y22 & (ids <= cut),
        "test 2022 H2": y22 & (ids > cut),
        "confirm 2023-26": scored & (d["year"] >= 2023),
    }
    for name, m in periods.items():
        print(f"{name:16} n={m.sum():5d}  newcomer matches {(m & newcomer).sum():5d}"
              f"  newcomer loss {loss(d, base, m & newcomer).mean():.4f}"
              f"  vs established {loss(d, base, m & ~newcomer).mean():.4f}")

    # c only matters relative to founding teams, and every team is a "newcomer"
    # in 2021, so a pool-wide prior just shifts all ratings: test inheritance
    # at the production 1500 prior.
    grid = [dict()]
    grid += [dict(inherit=k, shrink=s, en_bloc=e) for k in (3, 4)
             for s in (0.5, 0.75, 1.0) for e in (False, True)]
    tune = periods["tune 2022 H1"]
    scoredg = []
    for g in grid:
        p, _, inh = run(d, **g)
        scoredg.append((loss(d, p, tune).mean(), g, p, inh))
    scoredg.sort(key=lambda r: r[0])
    print("\nbest 6 on 2022 H1 (all Tier-1 matches):")
    for v, g, _, _ in scoredg[:6]:
        print(f"  {str(g):46} {v:.4f}")

    best_any = min((r for r in scoredg if r[1].get("inherit") and not r[1]["en_bloc"]), key=lambda r: r[0])
    best_bloc = min((r for r in scoredg if r[1].get("en_bloc")), key=lambda r: r[0])
    for label, (_, g, p, inh) in (("inherit on any 3-of-5 overlap", best_any),
                                  ("inherit only on en-bloc moves", best_bloc)):
        print(f"\n{label}: {g}")
        for name, m in periods.items():
            for sub, mm in (("all", m), ("newcomer", m & newcomer)):
                diff = loss(d, base, mm) - loss(d, p, mm)
                print(f"  {name:16} {sub:9} n={mm.sum():5d}  1500 {loss(d, base, mm).mean():.4f}"
                      f"  model {loss(d, p, mm).mean():.4f}  paired t={tstat(diff):+.2f}")
        print(f"  first appearances that inherited a rating: {int(inh.sum())}"
              f" (2023+: {int((inh & (d['year'] >= 2023)).sum())})")

    # Why does the rule lose on 2023-26? Split the effect: (a) inheritance only
    # from 2023 on, so 2021-22 ratings are identical to production and only the
    # 2023+ inheritances differ; (b) inheritance only up to 2022, so 2023+
    # differs only through ratings carried in from the open era.
    _, g, _, _ = best_bloc
    confirm = periods["confirm 2023-26"]
    print("\nwhere the 2023-26 loss comes from (en-bloc rule, all 2023-26 matches):")
    for label, window in (("inherit from 2023 on only", dict(from_year=2023)),
                          ("inherit in 2021-22 only", dict(until_year=2022))):
        p, _, inh = run(d, **g, **window)
        diff = loss(d, base, confirm) - loss(d, p, confirm)
        print(f"  {label:28} model {loss(d, p, confirm).mean():.4f} vs 1500 "
              f"{loss(d, base, confirm).mean():.4f}  paired t={tstat(diff):+.2f}"
              f"  inheritances {int(inh.sum())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
