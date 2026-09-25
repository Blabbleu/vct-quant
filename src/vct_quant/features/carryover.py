"""Roster-based rating carry-over: Riot's 2027 "keep 3 of 5, keep your points".

Production Elo starts every new team key at 1500. In an open ecosystem a new
key is often an existing roster under a new banner (rebrand, org swap, a core
picked up after its org folds). This replay starts such a key at the rating of
the team its players came from instead.

Rule (fixed on 2022 H1; docs/roster-carryover-2026-09-24.md): when a team key
plays its first Tier-1 match and at least MIN_SHARED of that lineup were last
seen together on one already-rated team, and that team's latest lineup still
contains them (an en-bloc move, not a continuing team losing players to
transfers), the new key starts at that team's full rating.

Lineups are the players who took the server for the match. Rows without
player stats never trigger inheritance, so with no rosters at all this is
exactly production Elo: margin signal, K = BEST_K on Tier 1, Tier-2 results
at weight zero. Reproduces scripts/open_era.py's en-bloc run exactly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable, Mapping

import numpy as np
import pandas as pd

from .ratings import DEFAULT_BASE, expected_score

MIN_SHARED = 3
SHRINK = 1.0      # fraction of the source's edge over the base that carries over
EN_BLOC = True

Rosters = Mapping[tuple[int, int], frozenset]


@dataclass
class CarryoverState:
    min_shared: int = MIN_SHARED
    shrink: float = SHRINK
    en_bloc: bool = EN_BLOC
    base: float = DEFAULT_BASE
    rating: dict = field(default_factory=dict)
    last_lineup: dict = field(default_factory=dict)   # team -> latest Tier-1 lineup
    player_team: dict = field(default_factory=dict)   # player -> team of that lineup

    def source(self, team: Hashable, lineup: frozenset) -> Hashable | None:
        """The rated team this lineup moved from as a unit, or None."""
        counts: dict = {}
        for player in lineup:
            src = self.player_team.get(player)
            if src is not None and src != team:
                counts[src] = counts.get(src, 0) + 1
        if not counts:
            return None
        # max() keeps the first-seen team on ties, as scripts/open_era.py does.
        src, shared = max(counts.items(), key=lambda kv: kv[1])
        if self.en_bloc:
            shared = min(shared, len(lineup & self.last_lineup.get(src, frozenset())))
        if shared < self.min_shared or src not in self.rating:
            return None
        return src

    def start_rating(self, team: Hashable, lineup: frozenset) -> tuple[float, Hashable | None]:
        """(rating, source team or None) for `team` if it played with `lineup` now."""
        if team in self.rating:
            return self.rating[team], None
        src = self.source(team, lineup) if lineup else None
        if src is None:
            return self.base, None
        return self.base + self.shrink * (self.rating[src] - self.base), src

    def remember(self, team: Hashable, lineup: frozenset) -> None:
        if lineup:
            self.last_lineup[team] = lineup
            for player in lineup:
                self.player_team[player] = team


def carryover_elo(
    history: pd.DataFrame,
    rosters: Rosters,
    k: float | None = None,
    **rule,
) -> tuple[np.ndarray, CarryoverState, list[tuple[int, Hashable, Hashable]]]:
    """Replay Tier-1 Elo over `history` (chronological) with roster carry-over.

    Returns (pre-match P(team A wins) per row, NaN off Tier 1; the final state;
    [(match_id, new team, source team)] for every inheritance). `rule`
    overrides MIN_SHARED / SHRINK / EN_BLOC (min_shared=, shrink=, en_bloc=).
    """
    from .build import BEST_K, TIER_2_WEIGHT, margin_signal

    # Tier-2 rows are skipped outright, which equals production only while
    # their Elo weight is zero. Fail loudly if that validated setting changes.
    assert TIER_2_WEIGHT == 0.0, "carry-over replay assumes Tier-2 weight 0"
    k = BEST_K if k is None else k
    state = CarryoverState(**rule)
    signal = margin_signal(history).to_numpy(float)
    p_out = np.full(len(history), np.nan)
    inherited: list = []
    rows = zip(history.match_id, history.tier, history.team_a, history.team_b)
    for i, (match_id, tier, a, b) in enumerate(rows):
        if tier != 1:
            continue
        lineups = (rosters.get((int(match_id), 1), frozenset()),
                   rosters.get((int(match_id), 2), frozenset()))
        for team, lineup in zip((a, b), lineups):
            if team not in state.rating:
                state.rating[team], src = state.start_rating(team, lineup)
                if src is not None:
                    inherited.append((int(match_id), team, src))
        ra, rb = state.rating[a], state.rating[b]
        p = expected_score(ra, rb)
        p_out[i] = p
        delta = k * (signal[i] - p)
        state.rating[a], state.rating[b] = ra + delta, rb - delta
        for team, lineup in zip((a, b), lineups):
            state.remember(team, lineup)
    return p_out, state, inherited


def latest_lineups(history: pd.DataFrame, rosters: Rosters) -> dict:
    """team key -> its most recent known lineup in `history`, any tier.

    An upcoming fixture has no lineup yet, so a team's first Tier-1 forecast
    uses the lineup it last fielded (typically in an open qualifier).
    """
    out: dict = {}
    for match_id, a, b in zip(history.match_id, history.team_a, history.team_b):
        for team, side in ((a, 1), (b, 2)):
            lineup = rosters.get((int(match_id), side))
            if lineup:
                out[team] = lineup
    return out


def carryover_probability(
    fixtures: pd.DataFrame, history: pd.DataFrame, rosters: Rosters
) -> pd.DataFrame:
    """P(team A wins) under carry-over, plus the team each side inherited from."""
    _, state, _ = carryover_elo(history, rosters)
    known = latest_lineups(history, rosters) if rosters else {}
    p, src_a, src_b = [], [], []
    for a, b in zip(fixtures.team_a_key, fixtures.team_b_key):
        ra, sa = state.start_rating(a, known.get(a, frozenset()))
        rb, sb = state.start_rating(b, known.get(b, frozenset()))
        p.append(expected_score(ra, rb))
        src_a.append(None if sa is None else str(sa))
        src_b.append(None if sb is None else str(sb))
    return pd.DataFrame(
        {"p_team_a_win_carryover": p, "carryover_from_a": src_a, "carryover_from_b": src_b},
        index=fixtures.index,
    )
