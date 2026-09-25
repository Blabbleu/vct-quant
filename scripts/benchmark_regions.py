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

import re

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

# Riot's September 2026 list has 16 qualifiers (not 14). Assign a territory
# from an official event title, never from a team's name or guessed nationality.
QUALIFIER_TERRITORIES = {
    "north america": "Americas", "latin america north": "Americas",
    "latin america south": "Americas", "brazil": "Americas",
    "europe": "EMEA", "turkiye": "EMEA", "türkiye": "EMEA", "mena": "EMEA",
    "south korea": "Pacific", "japan": "Pacific", "thailand": "Pacific",
    "indonesia": "Pacific", "vietnam": "Pacific", "southeast asia": "Pacific",
    "south asia": "Pacific", "oceania": "Pacific", "china": "China",
}
_QUALIFIER_NAME = "|".join(re.escape(name) for name in QUALIFIER_TERRITORIES)
_QUALIFIER = re.compile(rf"\b({_QUALIFIER_NAME})\s+open qualifiers?\b", re.I)


def territory_for_event(title: str) -> str | None:
    """Recognize a regional league or a named 2027 open qualifier."""
    if re.search(r"\bvct 2027\b", title, re.I) and re.search(
        r"\bopen qualifiers?\b", title, re.I
    ):
        found = _QUALIFIER.search(title)
        return QUALIFIER_TERRITORIES[found.group(1).lower()] if found else None
    if re.search(r"\bopen qualifiers?\b", title, re.I):
        return None
    found = re.search(LEAGUE, title)
    return found.group(1) if found else None


def assign_regions(df: pd.DataFrame) -> pd.DataFrame:
    """Carry the last regional event assignment in match-id order."""
    region: dict[str, str] = {}
    region_a, region_b = [], []
    for team_a, team_b, title in zip(df.team_a, df.team_b, df.event_name):
        league = None if re.search(INTERNATIONAL, title) else territory_for_event(title)
        if league:
            region[team_a] = region[team_b] = league
        region_a.append(region.get(team_a))
        region_b.append(region.get(team_b))
    return df.assign(region_a=region_a, region_b=region_b)


def region_history_mask(df: pd.DataFrame) -> pd.Series:
    """Retain 2027 fixtures with ISO dates and qualifier region lineage."""
    season_2027 = df.event_name.str.contains(
        r"\bvct 2027\b", case=False, regex=True, na=False
    )
    qualifier = df.event_name.str.contains(
        r"\bopen qualifiers?\b", case=False, regex=True, na=False
    )
    return (df.tier.eq(1) & (df.year.ge(FIRST_YEAR) | season_2027)) | (
        df.tier.eq(2) & season_2027 & qualifier
    )


def with_2027_season(df: pd.DataFrame) -> pd.DataFrame:
    """Label VCT 2027 by event season, including November 2026 qualifiers."""
    season_2027 = df.event_name.str.contains(
        r"\bvct 2027\b", case=False, regex=True, na=False
    )
    out = df.copy()
    out.loc[season_2027, "year"] = 2027
    return out


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
    # Tier-2 results do not move Elo (validated weight zero), but official
    # 2027 qualifier participation is a pre-match territory signal for a team's
    # later Tier-1 appearances. Keep those rows during region assignment only.
    df = df.loc[region_history_mask(df)].reset_index(drop=True)
    df = with_2027_season(assign_regions(df))
    df = df[df.tier.eq(1)].reset_index(drop=True)
    df["international"] = df.event_name.str.contains(INTERNATIONAL, regex=True)
    return df


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
