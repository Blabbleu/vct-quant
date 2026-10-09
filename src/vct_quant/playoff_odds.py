"""Exact playoff pairing and title odds for the pinned Champions bracket."""
from __future__ import annotations

from math import isfinite
from typing import Callable

from .event_bracket import playoff_feeds, validate_bracket_spec

_STAGE_ORDER = (
    "Upper Quarterfinals", "Upper Semifinals", "Lower Round 1",
    "Lower Round 2", "Upper Final", "Lower Round 3", "Lower Final",
    "Grand Final",
)


def _winner(pair: tuple[int, int], scores: list[int]) -> tuple[int, int]:
    return (pair[0], pair[1]) if scores[0] > scores[1] else (pair[1], pair[0])


def project_playoffs(spec: dict, entrants: dict[int, tuple[int, int]],
                     results: dict[int, dict],
                     p_win: Callable[[int, int], float]) -> dict:
    """Enumerate every remaining playoff series outcome and return exact odds.

    ``p_win(a, b)`` is the series probability that ``a`` beats ``b``. Results
    are fixed positional team IDs and map scores, matching ``playoff_results``.
    """
    validate_bracket_spec(spec)
    feeds = playoff_feeds(spec)
    stage_order = {stage: index for index, stage in enumerate(_STAGE_ORDER)}
    slots = sorted(spec["playoffs"], key=lambda row: stage_order[row["stage"]])
    by_id = {row["match_id"]: row for row in slots}
    qf_ids = {row["match_id"] for row in slots if row["stage"] == "Upper Quarterfinals"}
    if set(entrants) != qf_ids:
        raise ValueError("entrants must cover exactly the Upper Quarterfinals")
    if set(results) - set(by_id):
        raise ValueError("result outside the playoff bracket")
    for mid, pair in entrants.items():
        if (not isinstance(pair, (tuple, list)) or len(pair) != 2
                or any(type(team) is not int or team <= 0 for team in pair)
                or pair[0] == pair[1]):
            raise ValueError(f"invalid entrants for {mid}")

    candidates: dict[int, dict[tuple[int, int], float]] = {mid: {} for mid in by_id}
    first_wins: dict[int, dict[tuple[int, int], float]] = {mid: {} for mid in by_id}
    team_fill: dict[int, dict[int, float]] = {mid: {} for mid in by_id}
    p_reach: dict[int, dict[str, float]] = {}
    p_title: dict[int, float] = {}
    total = 0.0

    def visit(index: int, outcomes: dict[int, tuple[int, int]], pairs: dict[int, tuple[int, int]],
              weight: float) -> None:
        nonlocal total
        if index == len(slots):
            total += weight
            for row in slots:
                mid, stage = row["match_id"], row["stage"]
                pair = pairs[mid]
                candidates[mid][pair] = candidates[mid].get(pair, 0.0) + weight
                if outcomes[mid][0] == pair[0]:
                    first_wins[mid][pair] = first_wins[mid].get(pair, 0.0) + weight
                for team in pair:
                    team_fill[mid][team] = team_fill[mid].get(team, 0.0) + weight
                    stages = p_reach.setdefault(team, {})
                    stages[stage] = stages.get(stage, 0.0) + weight
            champion = outcomes[slots[-1]["match_id"]][0]
            p_title[champion] = p_title.get(champion, 0.0) + weight
            return

        row = slots[index]
        mid, stage = row["match_id"], row["stage"]
        if stage == "Upper Quarterfinals":
            pair = tuple(entrants[mid])
        else:
            feed_a, feed_b = feeds[mid]
            pair = (outcomes[feed_a[0]][0 if feed_a[1] == "winner" else 1],
                    outcomes[feed_b[0]][0 if feed_b[1] == "winner" else 1])
        pairs[mid] = pair
        if mid in results:
            result = results[mid]
            if not isinstance(result, dict):
                raise ValueError(f"{mid} result does not match its routed playoff pair")
            scores = result.get("scores")
            result_teams = result.get("team_ids")
            if (not isinstance(result_teams, list) or len(result_teams) != 2
                    or any(type(team) is not int for team in result_teams)
                    or set(result_teams) != set(pair) or not isinstance(scores, list)
                    or len(scores) != 2 or any(type(score) is not int or score < 0 for score in scores)
                    or scores[0] == scores[1]):
                raise ValueError(f"{mid} result does not match its routed playoff pair")
            outcomes[mid] = _winner(tuple(result_teams), scores)
            visit(index + 1, outcomes, pairs, weight)
            del outcomes[mid]
        else:
            probability = p_win(*pair)
            if not isfinite(probability) or not 0.0 <= probability <= 1.0:
                raise ValueError(f"invalid pairwise probability for {mid}: {probability!r}")
            for winner_first, branch_probability in ((True, probability), (False, 1.0 - probability)):
                outcomes[mid] = pair if winner_first else (pair[1], pair[0])
                visit(index + 1, outcomes, pairs, weight * branch_probability)
            del outcomes[mid]
        del pairs[mid]

    visit(0, {}, {}, 1.0)
    if abs(total - 1.0) > 1e-9:
        raise ValueError("playoff paths do not sum to one")
    slot_output = {}
    for row in slots:
        mid = row["match_id"]
        pairing_total = sum(candidates[mid].values())
        if abs(pairing_total - 1.0) > 1e-9:
            raise ValueError(f"pairings for {mid} do not sum to one")
        slot_output[mid] = {
            "stage": row["stage"],
            "candidates": [],
            "team_fill": team_fill[mid],
        }
        rows = []
        for pair, probability in candidates[mid].items():
            rows.append({"team_ids": list(pair), "p_pairing": probability,
                         "p_a": first_wins[mid].get(pair, 0.0) / probability if probability else 0.0})
        slot_output[mid]["candidates"] = sorted(rows, key=lambda item: (-item["p_pairing"], item["team_ids"]))
    if abs(sum(p_title.values()) - 1.0) > 1e-9:
        raise ValueError("title probabilities do not sum to one")
    return {"slots": slot_output,
            "teams": {team: {"p_reach": p_reach.get(team, {}), "p_title": p_title.get(team, 0.0)}
                      for team in sorted(set(p_reach) | set(p_title))}}
