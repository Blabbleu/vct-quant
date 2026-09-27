"""Group-stage qualification odds derived from the primary Elo forecast.

Descriptive derivation only (docs/champions-group-odds.md): every remaining
series in a five-match double-elimination group is resolved with the same
probability the primary forecast would emit for that pairing today, and the
tree is enumerated exactly (at most 2**5 paths). No new model, no tuning, no
title odds: playoff routing is still unverified, so this stops at the group.
"""
from __future__ import annotations

from itertools import product
from math import isfinite
from typing import Callable

from .features.ratings import DEFAULT_BASE, expected_score

_ORDER = ("opening_1", "opening_2", "winners", "elimination", "decider")
# A group is withheld unless every entrant has at least this many rated
# official matches: a 1500 default would be "unknown", not "average".
MIN_RATED_MATCHES = 1


def _winner(pair: list[int], scores: list[int]) -> tuple[int, int]:
    return (pair[0], pair[1]) if scores[0] > scores[1] else (pair[1], pair[0])


def qualification_odds(group: dict, p_win: Callable[[int, int], float]) -> dict:
    """Exact P(qualify) and P(group winner) for one group-status dict.

    ``group`` is one entry of ``champions_status(...)["groups"]``: pinned
    opening team IDs in ``slots`` and verified ``results`` by slot key. Played
    results are fixed; every other series is an independent draw from
    ``p_win(a, b)`` = P(a beats b). "Group winner" is the winners'-match victor
    (first qualifier); the second qualifier is the decider winner.
    """
    slots, results = group["slots"], group["results"]
    open_keys = [key for key in _ORDER if key not in results]
    p_qualify: dict[int, float] = {}
    p_first: dict[int, float] = {}
    for team in slots["opening_1"]["team_ids"] + slots["opening_2"]["team_ids"]:
        p_qualify[team] = p_first[team] = 0.0
    total = 0.0
    for branch in product((0, 1), repeat=len(open_keys)):
        picks = dict(zip(open_keys, branch))
        weight = 1.0
        outcome: dict[str, tuple[int, int]] = {}
        pairs = {"opening_1": slots["opening_1"]["team_ids"],
                 "opening_2": slots["opening_2"]["team_ids"]}
        for key in _ORDER:
            if key == "winners":
                pairs[key] = [outcome["opening_1"][0], outcome["opening_2"][0]]
            elif key == "elimination":
                pairs[key] = [outcome["opening_1"][1], outcome["opening_2"][1]]
            elif key == "decider":
                pairs[key] = [outcome["winners"][1], outcome["elimination"][0]]
            pair = pairs[key]
            if key in results:
                if results[key]["team_ids"] != pair:
                    raise ValueError(f"{key} result does not match its bracket slot")
                outcome[key] = _winner(pair, results[key]["scores"])
                continue
            a_wins = picks[key] == 0
            p = p_win(pair[0], pair[1])
            if not isfinite(p) or not 0.0 <= p <= 1.0:
                raise ValueError(f"invalid pairwise probability for {key}: {p!r}")
            weight *= p if a_wins else 1.0 - p
            outcome[key] = (pair[0], pair[1]) if a_wins else (pair[1], pair[0])
        total += weight
        first, second = outcome["winners"][0], outcome["decider"][0]
        p_first[first] += weight
        p_qualify[first] += weight
        p_qualify[second] += weight
    if abs(total - 1.0) > 1e-9:
        raise ValueError("group paths do not sum to one")
    return {"p_qualify": p_qualify, "p_first": p_first}


def elo_p_win(ratings: dict) -> Callable[[int, int], float]:
    """P(a beats b) exactly as `predict_upcoming` emits it (string team keys)."""
    return lambda a, b: expected_score(ratings.get(str(a), DEFAULT_BASE),
                                       ratings.get(str(b), DEFAULT_BASE))


def current_elo() -> tuple[dict, dict, int | None]:
    """Primary-pool ratings, rated-match counts and the last replayed match ID.

    Mirrors the official branch of `features.build.predict_upcoming`.
    """
    import pandas as pd

    from .features.build import elo_k, margin_signal, match_sequence
    from .features.ratings import compute_elo

    history = match_sequence(tiers=(1, 2))
    _, ratings = compute_elo(
        zip(history.match_id, history.team_a, history.team_b, margin_signal(history)),
        k=elo_k(history.tier),
    )
    counts = pd.concat([history.team_a, history.team_b]).value_counts().to_dict()
    through = int(history.match_id.max()) if not history.empty else None
    return ratings, counts, through


def attach_group_odds(status: dict, ratings: dict, counts: dict,
                      through: int | None) -> dict:
    """Add a ``qualification`` block per group; withhold it rather than guess."""
    p_win = elo_p_win(ratings)
    for group in status["groups"].values():
        teams = [int(team) for team in group["entrants"]]
        unrated = [team for team in teams if counts.get(str(team), 0) < MIN_RATED_MATCHES]
        if group["unverified_match_ids"]:
            group["qualification"] = {"withheld": "unverified completed result in this group"}
            continue
        if unrated:
            group["qualification"] = {"withheld": f"no rated official history for team IDs {unrated}"}
            continue
        odds = qualification_odds(group, p_win)
        group["qualification"] = {
            "model": "primary Elo, ratings frozen for the rest of the group",
            "ratings_through_match_id": through,
            "teams": [
                {"team_id": team, "elo": ratings[str(team)],
                 "rated_matches": int(counts[str(team)]),
                 "p_qualify": odds["p_qualify"][team],
                 "p_first": odds["p_first"][team],
                 "qualified": team in group["qualifiers"]}
                for team in sorted(teams, key=lambda t: (-odds["p_qualify"][t], t))
            ],
        }
    return status
