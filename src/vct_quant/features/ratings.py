"""Elo ratings over match history.

Point-in-time safe by construction: the rating attached to a match is the
rating *before* that match was played, so features built from these never
leak the match's own outcome.
"""
from __future__ import annotations

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


def compute_elo(
    matches: Iterable[tuple[Hashable, Hashable, Hashable, float]],
    k: float = DEFAULT_K,
    base: float = DEFAULT_BASE,
) -> tuple[list[dict], dict]:
    """Run Elo over (match_id, team_a, team_b, score_a) tuples that MUST be in
    chronological order.

    Returns (rows, final_ratings) where each row carries the pre-match ratings
    and the model's win probability for team A.
    """
    ratings: dict = {}
    rows: list[dict] = []
    for match_id, team_a, team_b, score_a in matches:
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
