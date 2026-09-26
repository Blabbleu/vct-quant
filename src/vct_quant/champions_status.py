"""Descriptive Champions group results from the canonical DB, never odds."""
from __future__ import annotations

from .event_bracket import group_progress, validate_bracket_spec


def champions_status(db, spec: dict) -> dict:
    """Return source-pinned group progress; unverified rows cannot advance teams.

    Canonical rows may lag the live event page. Use the DB source timestamp,
    and do not infer playoff routing from group position.
    """
    validate_bracket_spec(spec)
    ids = [slot["match_id"] for group in spec["groups"].values() for slot in group.values()]
    rows = db.execute("""
        SELECT m.match_id, m.event_id, m.event_series, m.status, m.last_seen_at,
               mt.team_number, mt.team_id, mt.series_score, mt.is_winner
        FROM match m LEFT JOIN match_team mt ON m.match_id = mt.match_id
        WHERE m.match_id IN (SELECT unnest(?))
        ORDER BY m.match_id, mt.team_number
    """, [ids]).fetchall()
    by_id: dict[int, list] = {}
    for row in rows:
        by_id.setdefault(row[0], []).append(row)
    as_of = max((row[4] for row in rows if row[4] is not None), default=None)
    output = {"event_id": spec["event_id"], "as_of": as_of.isoformat() if as_of else None,
              "playoff_routing": "unresolved", "title_odds": None, "groups": {}}
    for letter, group in spec["groups"].items():
        results = {}
        issues = []
        for key, slot in group.items():
            match_id = slot["match_id"]
            sides = by_id.get(match_id, [])
            if not sides:
                continue
            if sides[0][3] != "completed":
                continue
            scores = [side[7] for side in sides]
            team_ids = [side[6] for side in sides]
            flags = [side[8] for side in sides]
            if (len(sides) != 2 or any(side[1] != spec["event_id"] or side[2] != slot["stage"] for side in sides)
                    or [side[5] for side in sides] != [1, 2]
                    or any(type(team_id) is not int or team_id <= 0 for team_id in team_ids)
                    or len(set(team_ids)) != 2
                    or any(type(score) is not int or score < 0 for score in scores)
                    or sorted(scores) not in ([0, 2], [1, 2])
                    or flags != [scores[0] > scores[1], scores[1] > scores[0]]
                    or ("team_ids" in slot and team_ids != slot["team_ids"])):
                issues.append(match_id)
                continue
            results[match_id] = {"team_ids": team_ids, "scores": scores}
        try:
            progress = group_progress(spec, letter, results)
        except ValueError:
            # A source result with an impossible predecessor/order must not route.
            progress = {"expected": {}, "qualifiers": []}
            issues.extend(results)
            results = {}
        output["groups"][letter] = {
            **progress,
            "entrants": {str(team_id): name for slot in group.values() if "teams" in slot
                         for team_id, name in zip(slot["team_ids"], slot["teams"])},
            "slots": {key: {"match_id": slot["match_id"], "stage": slot["stage"],
                            **({"team_ids": slot["team_ids"]} if "team_ids" in slot else {})}
                      for key, slot in group.items()},
            "results": {key: results[slot["match_id"]] for key, slot in group.items() if slot["match_id"] in results},
            "unverified_match_ids": sorted(set(issues)),
        }
    return output


if __name__ == "__main__":
    import json
    from .db import connect
    from .event_bracket import load_bracket_spec

    with connect(read_only=True) as connection:
        print(json.dumps(champions_status(connection, load_bracket_spec(2766))))
