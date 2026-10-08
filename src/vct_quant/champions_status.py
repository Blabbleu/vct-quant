"""Descriptive Champions group results from the canonical DB, never odds."""
from __future__ import annotations

from .event_bracket import group_progress, validate_bracket_spec


class _PlayoffResults(dict):
    """Exact public result mapping with DB names retained for completed slots."""
    team_names: dict[int, list[str]]
    unverified: list[int]


def playoff_results(db, spec: dict) -> dict[int, dict]:
    """Read decisive, source-verified results for the spec's playoff slots."""
    slots = {slot["match_id"]: slot for slot in spec["playoffs"]}
    stages = {slot["match_id"]: slot["stage"] for slot in spec.get("verified_opening_pairings", [])}
    for match_id, stage in stages.items():
        slots.setdefault(match_id, {"match_id": match_id, "stage": stage})
    ids = list(slots)
    if not ids:
        return {}
    rows = db.execute("""
        SELECT m.match_id, m.event_id, m.event_series, m.status,
               mt.team_number, mt.team_id, mt.team_name, mt.series_score, mt.is_winner
        FROM match m LEFT JOIN match_team mt ON m.match_id = mt.match_id
        WHERE m.match_id IN (SELECT unnest(?))
        ORDER BY m.match_id, mt.team_number
    """, [ids]).fetchall()
    by_id = {}
    for row in rows:
        by_id.setdefault(row[0], []).append(row)
    out = _PlayoffResults()
    out.team_names = {}
    out.unverified = []
    for match_id, slot in slots.items():
        sides = by_id.get(match_id, [])
        if not sides or sides[0][3] != "completed":
            continue
        ids_for_match = [side[5] for side in sides]
        scores = [side[7] for side in sides]
        best_of = spec.get("series_best_of", {}).get("playoffs", {}).get(slot["stage"])
        wins = (best_of // 2 + 1) if type(best_of) is int and best_of in (3, 5) else None
        decisive_scores = ([[0, wins], [1, wins]] if wins == 2 else
                           [[0, wins], [1, wins], [2, wins]] if wins == 3 else [])
        if (len(sides) != 2 or any(s[1] != spec["event_id"] or s[2] != slot["stage"] for s in sides)
                or [s[4] for s in sides] != [1, 2]
                or any(type(team_id) is not int or team_id <= 0 for team_id in ids_for_match)
                or len(set(ids_for_match)) != 2
                or any(type(score) is not int or score < 0 for score in scores)
                or sorted(scores) not in decisive_scores
                or [s[8] for s in sides] != [scores[0] > scores[1], scores[1] > scores[0]]):
            out.unverified.append(match_id)
            continue
        out[match_id] = {"team_ids": ids_for_match, "scores": scores}
        out.team_names[match_id] = [s[6] for s in sides]
    return out


def _later_sides(slot, date_row, fixture, result, results, unverified):
    if date_row and "teams" in date_row and "team_ids" in date_row:
        names, team_ids = date_row["teams"], date_row["team_ids"]
    elif result:
        team_ids = result["team_ids"]
        names = getattr(results, "team_names", {}).get(slot["match_id"], [None, None])
    else:
        return None
    if result:
        if date_row and "team_ids" in date_row and set(result["team_ids"]) != set(team_ids):
            unverified.add(slot["match_id"])
            return None
        names_by_id = dict(zip(result["team_ids"], getattr(results, "team_names", {}).get(slot["match_id"], [])))
        names = [names_by_id.get(team_id) or name for team_id, name in zip(team_ids, names)]
    flip = False
    schedule_names = date_row.get("teams", names) if date_row else names
    matched = fixture and [fixture["team_a"], fixture["team_b"]] in (schedule_names, schedule_names[::-1])
    if matched:
        flip = fixture["team_a"] != schedule_names[0]
    sides = []
    for i in range(2):
        src = (i + (1 if flip else 0)) % 2
        key = "ab"[src]
        sides.append({"team_id": team_ids[i], "name": names[i],
                      "logo": fixture[f"logo_{key}"] if matched else None,
                      "tag": fixture[f"tag_{key}"] if matched else None,
                      "matches": fixture[f"matches_{key}"] if matched else None,
                      "p_win": ((1 - fixture["p_a"]) if (i == 0 and flip) or (i == 1 and not flip)
                                else fixture["p_a"])
                      if matched else None})
    return sides


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


def attach_playoffs(status: dict, spec: dict, fixtures: list[dict], schedule: list[dict], results=None) -> dict:
    """Add the verified opening playoff pairings joined to their model fixtures.

    Only ``verified_opening_pairings`` (pinned names/IDs) appear; the forecast,
    kick-off and market come from a fixture with the same match ID *and* the
    same two team names, otherwise they are withheld (never guessed). Later
    slots are listed as TBD with dates only where the schedule supplies them.
    Routing and title odds stay unresolved/null.
    """
    pairings = spec.get("verified_opening_pairings") or []
    if not pairings:
        return status
    by_id = {f["match_id"]: f for f in fixtures}
    dates = {row["match_id"]: row for row in schedule}
    opening, unverified = [], set()
    for pairing in pairings:
        names, team_ids = pairing["teams"], pairing["team_ids"]
        fixture = by_id.get(pairing["match_id"])
        p_a, flip, extra = None, False, {}
        if fixture and [fixture["team_a"], fixture["team_b"]] in (names, names[::-1]):
            flip = fixture["team_a"] != names[0]
            p_a = fixture["p_a"] if not flip else 1 - fixture["p_a"]
            if fixture.get("market") is not None:
                market = fixture["market"] if not flip else 1 - fixture["market"]
                extra = {"p_a": market, "spread": fixture.get("spread"), "volume": fixture.get("volume")}
        else:
            fixture = None

        def side(index: int) -> dict:
            src = (index + (1 if flip else 0)) % 2
            key = "ab"[src]
            return {"team_id": team_ids[index], "name": names[index],
                    "logo": fixture[f"logo_{key}"] if fixture else None,
                    "tag": fixture[f"tag_{key}"] if fixture else None,
                    "matches": fixture[f"matches_{key}"] if fixture else None,
                    "p_win": None if p_a is None else (p_a if index == 0 else 1 - p_a)}

        result = (results or {}).get(pairing["match_id"])
        if result and set(result["team_ids"]) != set(team_ids):
            result = None
        result_side_order = None if result is None else [result["team_ids"].index(team_id) for team_id in team_ids]
        entry = {
            "match_id": pairing["match_id"], "stage": pairing["stage"],
            "start": fixture["start"] if fixture else None,
            "best_of": fixture["best_of"] if fixture else None,
            "url": fixture.get("url") if fixture else None,
            "sides": [side(0), side(1)],
            "market": extra or None,
        }
        if results is not None:
            entry["result"] = None if result is None else {
                "winner_team_id": result["team_ids"][0 if result["scores"][0] > result["scores"][1] else 1],
                "scores": [result["scores"][i] for i in result_side_order]}
            if result is None and pairing["match_id"] in results:
                unverified.add(pairing["match_id"])
        opening.append(entry)
    paired = {m["match_id"] for m in opening}
    later = [{"match_id": slot["match_id"], "stage": slot["stage"],
              "start": dates.get(slot["match_id"], {}).get("start"),
              "best_of": dates.get(slot["match_id"], {}).get("best_of")}
             for slot in spec["playoffs"] if slot["match_id"] not in paired]
    if results is not None:
        for row in later:
            slot_id = row["match_id"]
            found = results.get(slot_id)
            score_order = ([found["team_ids"].index(team_id) for team_id in dates[slot_id]["team_ids"]]
                           if found and dates.get(slot_id, {}).get("team_ids") and set(found["team_ids"]) == set(dates[slot_id]["team_ids"])
                           else None)
            row["result"] = (None if found is None or ("teams" in dates.get(slot_id, {}) and score_order is None) else {
                "winner_team_id": found["team_ids"][0 if found["scores"][0] > found["scores"][1] else 1],
                "scores": [found["scores"][i] for i in score_order] if score_order else list(found["scores"])})
            slot = next(s for s in spec["playoffs"] if s["match_id"] == slot_id)
            row["sides"] = _later_sides(slot, dates.get(slot_id), by_id.get(slot_id), found, results, unverified)
    later.sort(key=lambda row: (row["start"] is None, row["start"] or ""))
    for pairing in pairings:
        found = (results or {}).get(pairing["match_id"])
        if found and set(found["team_ids"]) != set(pairing["team_ids"]):
            unverified.add(pairing["match_id"])
    status["playoffs"] = {"routing": "unresolved", "observed_at": spec["playoff_draw_observed_at"],
                          "sources": list(spec["playoff_draw_sources"]), "opening": opening, "schedule": later}
    if results is not None:
        unverified.update(getattr(results, "unverified", []))
        status["playoffs"]["unverified_match_ids"] = sorted(unverified)
    return status


if __name__ == "__main__":
    import json
    from .db import connect
    from .event_bracket import load_bracket_spec
    from .group_odds import attach_group_odds, current_elo
    from .dashboard import fixtures as dashboard_fixtures, playoff_schedule

    bracket = load_bracket_spec(2766)
    with connect(read_only=True) as connection:
        status = champions_status(connection, bracket)
        results = playoff_results(connection, bracket)
    status = attach_group_odds(status, *current_elo())
    print(json.dumps(attach_playoffs(status, bracket, dashboard_fixtures(),
                                     playoff_schedule([slot["match_id"] for slot in bracket["playoffs"]]), results)))
