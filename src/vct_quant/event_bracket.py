"""Source-pinned tournament slots; no odds or inferred playoff pairing."""
from __future__ import annotations

import json
from pathlib import Path

from .config import PROJECT_ROOT
from .ingest.vlrgg import detail_segments

_SPEC = PROJECT_ROOT / "config" / "brackets" / "champions_2026.json"
_GROUP_KEYS = {"opening_1", "opening_2", "winners", "elimination", "decider"}
_PLAYOFF_STAGES = {
    "Upper Quarterfinals": 4, "Upper Semifinals": 2, "Upper Final": 1,
    "Lower Round 1": 2, "Lower Round 2": 2, "Lower Round 3": 1,
    "Lower Final": 1, "Grand Final": 1,
}


def validate_bracket_spec(spec: dict) -> None:
    """Reject partial/ambiguous slots instead of inventing tournament odds."""
    if spec.get("event_id") != 2766 or set(spec.get("groups", {})) != set("ABCD"):
        raise ValueError("unsupported event or incomplete groups")
    if spec.get("playoff_seeding") != "unresolved" or spec.get("playoff_advancement") != "unresolved":
        raise ValueError("playoff routing has not been source verified")
    formats = spec.get("series_best_of")
    if (not isinstance(formats, dict) or type(formats.get("groups")) is not int
            or formats["groups"] != 3 or formats.get("playoffs") != {
                stage: (5 if stage in ("Lower Final", "Grand Final") else 3)
                for stage in _PLAYOFF_STAGES
            } or set(formats) != {"groups", "playoffs"}):
        raise ValueError("series format does not match official Champions overview")
    ids: set[int] = set()
    entrants: list[str] = []
    entrant_ids: list[int] = []

    def check_slot(slot: dict, stage: str) -> None:
        if slot.get("stage") != stage:
            raise ValueError(f"wrong stage: expected {stage}")
        match_id = slot.get("match_id")
        if type(match_id) is not int or match_id <= 0:
            raise ValueError("invalid match ID")
        if match_id in ids:
            raise ValueError("duplicate match ID")
        ids.add(match_id)

    for letter, group in spec["groups"].items():
        if set(group) != _GROUP_KEYS:
            raise ValueError(f"incomplete group {letter}")
        for key, stage in (("opening_1", "Opening"), ("opening_2", "Opening"),
                           ("winners", "Winner's"), ("elimination", "Elimination"),
                           ("decider", "Decider")):
            slot = group[key]
            check_slot(slot, f"{stage} ({letter})")
            if key.startswith("opening"):
                teams = slot.get("teams")
                if not isinstance(teams, list) or len(teams) != 2 or any(not isinstance(t, str) or not t.strip() or t == "TBD" for t in teams):
                    raise ValueError("incomplete opening entrants")
                entrants.extend(teams)
                if "team_ids" not in slot:
                    raise ValueError("missing opening team IDs")
                team_ids = slot["team_ids"]
                if (not isinstance(team_ids, list) or len(team_ids) != 2
                        or any(type(team_id) is not int or team_id <= 0 for team_id in team_ids)):
                    raise ValueError("invalid opening team IDs")
                entrant_ids.extend(team_ids)
            elif "teams" in slot or "team_ids" in slot:
                raise ValueError("future participants are not fixed")
    if len(set(entrants)) != 16:
        raise ValueError("duplicate opening entrant")
    if len(set(entrant_ids)) != 16:
        raise ValueError("duplicate opening team ID")
    if len(spec.get("playoffs", [])) != 14:
        raise ValueError("incomplete playoff slots")
    stages: dict[str, int] = {}
    for slot in spec["playoffs"]:
        stage = slot.get("stage")
        if stage not in _PLAYOFF_STAGES or "teams" in slot or "team_ids" in slot:
            raise ValueError("unknown playoff stage or premature participant")
        check_slot(slot, stage)
        stages[stage] = stages.get(stage, 0) + 1
    if stages != _PLAYOFF_STAGES:
        raise ValueError("incomplete playoff stage counts")


def detail_result(payload: dict, match_id: int) -> dict:
    """Convert a final, ID-verified detail payload to a group result."""
    detail = detail_segments(payload, match_id)[0]
    teams = detail["teams"]
    if detail.get("status") != "final" or len(teams) != 2:
        raise ValueError("detail is not a final two-team result")
    ids, scores = [], []
    for team in teams:
        raw_id, raw_score = str(team.get("id", "")), str(team.get("score", ""))
        if not raw_id.isascii() or not raw_id.isdecimal() or int(raw_id) <= 0 or not raw_score.isascii() or not raw_score.isdecimal():
            raise ValueError("detail lacks exact IDs or scores")
        ids.append(int(raw_id))
        scores.append(int(raw_score))
    if (ids[0] == ids[1] or scores[0] == scores[1]
            or [team.get("is_winner") for team in teams] != [scores[0] > scores[1], scores[1] > scores[0]]):
        raise ValueError("detail winner is inconsistent")
    return {"team_ids": ids, "scores": scores}


def group_progress(spec: dict, letter: str, results: dict[int, dict]) -> dict:
    """Route ID-checked, scored series within one group; never infer playoffs.

    ``results`` is keyed by the pinned match ID and uses positional exact team
    IDs and integer map scores. Callers must verify its source identity first.
    An absent result means unknown, not a guessed winner.
    """
    validate_bracket_spec(spec)
    if letter not in spec["groups"]:
        raise ValueError("unknown group")
    group = spec["groups"][letter]
    allowed = {slot["match_id"] for slot in group.values()}
    if set(results) - allowed:
        raise ValueError("result outside this group")
    expected: dict[str, list[int]] = {}

    def outcome(key: str, participants: list[int] | None) -> tuple[int, int] | None:
        match_id = group[key]["match_id"]
        if match_id not in results:
            return None
        if participants is None:
            raise ValueError(f"{key} completed before predecessor")
        row = results[match_id]
        scores = row.get("scores")
        if (row.get("team_ids") != participants or not isinstance(scores, list)
                or len(scores) != 2 or any(type(s) is not int or s < 0 for s in scores)
                or scores[0] == scores[1]):
            raise ValueError(f"unverified or incomplete {key} result")
        return (participants[0], participants[1]) if scores[0] > scores[1] else (participants[1], participants[0])

    first = outcome("opening_1", group["opening_1"]["team_ids"])
    second = outcome("opening_2", group["opening_2"]["team_ids"])
    if first and second:
        expected["winners"] = [first[0], second[0]]
        expected["elimination"] = [first[1], second[1]]
    winners = outcome("winners", expected.get("winners"))
    elimination = outcome("elimination", expected.get("elimination"))
    if winners and elimination:
        expected["decider"] = [winners[1], elimination[0]]
    decider = outcome("decider", expected.get("decider"))
    return {"expected": expected, "qualifiers": [winners[0], decider[0]] if winners and decider else []}


def load_bracket_spec(event_id: int) -> dict:
    if event_id != 2766:
        raise ValueError("unsupported event")
    spec = json.loads(_SPEC.read_text(encoding="utf-8"))
    validate_bracket_spec(spec)
    return spec
