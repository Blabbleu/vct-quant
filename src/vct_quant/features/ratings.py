"""Elo ratings over match history.

Point-in-time safe by construction: the rating attached to a match is the
rating *before* that match was played, so features built from these never
leak the match's own outcome.
"""
from __future__ import annotations

from itertools import repeat
from math import comb
from typing import Hashable, Iterable

DEFAULT_K = 32.0
DEFAULT_BASE = 1500.0


def expected_score(rating_a: float, rating_b: float) -> float:
    """P(A beats B) under the Elo logistic model."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def update(
    rating_a: float, rating_b: float, score_a: float, k: float = DEFAULT_K
) -> tuple[float, float]:
    """score_a: 1.0 = A won, 0.0 = A lost, 0.5 = draw."""
    delta = k * (score_a - expected_score(rating_a, rating_b))
    return rating_a + delta, rating_b - delta


def series_score_probabilities(
    p_series_a: float, best_of: int = 3
) -> dict[str, float]:
    """Exact score probabilities consistent with a series-win probability."""
    if not 0.0 <= p_series_a <= 1.0:
        raise ValueError("p_series_a must be between 0 and 1")
    if best_of <= 0 or best_of % 2 == 0:
        raise ValueError("best_of must be a positive odd number")

    wins = best_of // 2 + 1

    def p_series(p_map: float) -> float:
        return sum(
            comb(wins + losses - 1, losses)
            * p_map**wins
            * (1 - p_map) ** losses
            for losses in range(wins)
        )

    low, high = 0.0, 1.0
    for _ in range(60):
        mid = (low + high) / 2
        if p_series(mid) < p_series_a:
            low = mid
        else:
            high = mid
    p_map = (low + high) / 2
    out = {
        f"{wins}-{losses}": comb(wins + losses - 1, losses)
        * p_map**wins
        * (1 - p_map) ** losses
        for losses in range(wins)
    }
    out.update({
        f"{losses}-{wins}": comb(wins + losses - 1, losses)
        * (1 - p_map) ** wins
        * p_map**losses
        for losses in range(wins)
    })
    return out


def compute_elo(
    matches: Iterable[tuple[Hashable, Hashable, Hashable, float]],
    k: float | Iterable[float] = DEFAULT_K,
    base: float = DEFAULT_BASE,
    initial: dict | None = None,
) -> tuple[list[dict], dict]:
    """Run Elo over (match_id, team_a, team_b, score_a) tuples that MUST be in
    chronological order.

    `k` is either one value for every match, or a sequence of per-match values
    aligned with `matches` — the latter lets a match's own weight vary, e.g.
    updating harder on a dominant win than a narrow one.

    `initial` seeds the ratings instead of starting everyone at `base`. Use it to
    run a season at a time, regressing the previous season's ratings toward the
    mean in between — rosters turn over, so a year-old rating describes a team
    that no longer exists. It is copied, not mutated.

    Returns (rows, final_ratings) where each row carries the pre-match ratings
    and the model's win probability for team A.
    """
    ks = repeat(float(k)) if isinstance(k, (int, float)) else iter(k)
    ratings: dict = dict(initial or {})
    rows: list[dict] = []
    for (match_id, team_a, team_b, score_a), k in zip(matches, ks):
        ra = ratings.get(team_a, base)
        rb = ratings.get(team_b, base)
        rows.append(
            {
                "match_id": match_id,
                "team_a": team_a,
                "team_b": team_b,
                "elo_a_pre": ra,
                "elo_b_pre": rb,
                "p_a_win": expected_score(ra, rb),
            }
        )
        ratings[team_a], ratings[team_b] = update(ra, rb, score_a, k)
    return rows, ratings
