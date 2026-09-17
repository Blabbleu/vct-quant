"""Does Elo misjudge whole regions against each other at international events?

    python scripts/benchmark_regions.py

Regions only meet at Masters / Champions, so each league's ratings drift on
their own. A per-region OFFSET (in Elo points) is learned online from past
international results only, and added to both teams' ratings in international
matches. Regional matches are untouched: both teams share a region, so the
offset would cancel.

Since the 2023 partner leagues there are four regions: Americas, EMEA, Pacific,
China. Earlier seasons used different regions, so offsets start in 2023.

Protocol: choose REGION_K on 2023-2024 international matches, score 2025-2026
international matches with a paired t-test against raw Elo. Warning: there are
only ~120 scored matches in 2025-2026 -- expect a noisy answer.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vct_quant import db
from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo, expected_score

LEAGUE = r"(Americas|EMEA|Pacific|China)"
INTERNATIONAL = r"Masters|LOCK//IN|Valorant Champions \d{4}$"
FIRST_YEAR = 2023
TUNE_YEARS, TEST_YEARS = (2023, 2024), (2025, 2026)
K_GRID = [0, 2, 4, 8, 16, 32]


def per_match_loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def load() -> pd.DataFrame:
    """Tier-1 matches since 2023 with pre-match Elo and each team's region."""
    con = db.connect(read_only=True)
    try:
        seq = match_sequence(con)
        events = con.execute("SELECT match_id, event_name FROM match").df()
    finally:
        con.close()
    elo = pd.DataFrame(compute_elo(
        zip(seq.match_id, seq.team_a, seq.team_b, margin_signal(seq).to_numpy()),
        k=elo_k(seq.tier),
    )[0])
    df = seq.assign(
        elo_a=elo.elo_a_pre, elo_b=elo.elo_b_pre, p_elo=elo.p_a_win,
        signal=margin_signal(seq),
    ).merge(events, on="match_id")
    df = df[df.tier.eq(1) & df.year.ge(FIRST_YEAR)].reset_index(drop=True)

    df["international"] = df.event_name.str.contains(INTERNATIONAL, regex=True)
    league = df.event_name.str.extract(LEAGUE, expand=False).where(~df.international)

    # A team's region = league of its most recent regional match. Known before
    # any international match it plays, so this is not leakage.
    region: dict = {}
    region_a, region_b = [], []
    for team_a, team_b, lg in zip(df.team_a, df.team_b, league):
        if isinstance(lg, str):
            region[team_a] = region[team_b] = lg
        region_a.append(region.get(team_a))
        region_b.append(region.get(team_b))
    return df.assign(region_a=region_a, region_b=region_b)


def offset_probabilities(df: pd.DataFrame, k: float) -> np.ndarray:
    """P(team A wins) with region offsets; raw Elo outside international play.

    offsets[region] starts at 0 for every region. For each international match,
    IN ORDER, where both regions are known and differ:

      1. predict FIRST, using offsets from earlier matches only:
             p = expected_score(elo_a + offsets[region_a], elo_b + offsets[region_b])
      2. then learn from the result, exactly like an Elo update but for regions:
             delta = k * (signal - p)
             offsets[region_a] += delta
             offsets[region_b] -= delta

    Swap steps 1 and 2 and you have leakage: the prediction would already
    contain this match's own result.
    """
    offsets = {"Americas": 0.0, "EMEA": 0.0, "Pacific": 0.0, "China": 0.0}
    p = df.p_elo.to_numpy().copy()
    for i, row in enumerate(df.itertuples(index=False)):
        known = isinstance(row.region_a, str) and isinstance(row.region_b, str)
        if not row.international or not known:
            continue
        if row.region_a == row.region_b:
            continue
        p[i] = expected_score(
            row.elo_a + offsets[row.region_a], row.elo_b + offsets[row.region_b]
        )
        delta = k * (row.signal - p[i])
        offsets[row.region_a] += delta
        offsets[row.region_b] -= delta
    return p


def main() -> None:
    df = load()
    y = df.score_a.to_numpy()
    usable = df.international & df.score_a.ne(0.5)
    tune = (usable & df.year.isin(TUNE_YEARS)).to_numpy()
    test = (usable & df.year.isin(TEST_YEARS)).to_numpy()

    print(f"international matches: tune n={tune.sum()}, test n={test.sum()}")
    results = []
    for k in K_GRID:
        loss = per_match_loss(y[tune], offset_probabilities(df, k)[tune]).mean()
        results.append((loss, k))
        print(f"  k={k:<3} tune loss={loss:.4f}")
    best_k = min(results)[1]
    if best_k == 0:
        print("\nk=0 won on tuning: learned offsets never beat raw Elo. Nothing to test.")
        return

    p = offset_probabilities(df, best_k)
    raw, adj = per_match_loss(y[test], df.p_elo.to_numpy()[test]), per_match_loss(y[test], p[test])
    diff = raw - adj
    t = diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))
    print(f"\ntest {TEST_YEARS}  k={best_k}  elo={raw.mean():.4f}  "
          f"offsets={adj.mean():.4f}  t={t:+.2f}")


if __name__ == "__main__":
    main()
