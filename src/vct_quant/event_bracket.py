"""Source-pinned tournament slots; no odds or inferred playoff pairing."""
from __future__ import annotations

import json
from pathlib import Path

from .config import PROJECT_ROOT

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


def load_bracket_spec(event_id: int) -> dict:
    if event_id != 2766:
        raise ValueError("unsupported event")
    spec = json.loads(_SPEC.read_text(encoding="utf-8"))
    validate_bracket_spec(spec)
    return spec
