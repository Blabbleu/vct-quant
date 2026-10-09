"""Descriptive Champions group results from the canonical DB, never odds."""
from __future__ import annotations
from datetime import datetime

from .event_bracket import group_progress, validate_bracket_spec


def attach_playoff_projection(status: dict, spec: dict, results: dict, ratings: dict,
                              counts: dict, through: int | None) -> dict:
    """Attach exact frozen-Elo playoff pairing and title probabilities."""
    from .group_odds import MIN_RATED_MATCHES, elo_p_win
    from .playoff_odds import project_playoffs

    block = status.get("playoffs")
    if block is None:
        return status

    def withhold(reason: str) -> dict:
        block["projection"] = {"withheld": reason}
        block["routing"] = "unresolved"
        status["title_odds"] = None
        return status

    if getattr(results, "unverified", []):
        return withhold("unverified completed playoff result")
    entrants = {row["match_id"]: tuple(row["team_ids"])
                for row in spec["verified_opening_pairings"]}
    teams = sorted({team for pair in entrants.values() for team in pair})
    unrated = [team for team in teams if counts.get(str(team), 0) < MIN_RATED_MATCHES]
    if unrated:
        return withhold(f"insufficient rated history for team IDs {unrated}")
    verified = {mid: result for mid, result in results.items()
                if mid not in getattr(results, "unverified", [])}
    try:
        projection = project_playoffs(spec, entrants, verified, elo_p_win(ratings))
    except ValueError as exc:
        return withhold(f"playoff routing could not be verified: {exc}")

    advancement = spec.get("playoff_advancement", {})
    projection["slots"] = {
        str(mid): {"stage": slot["stage"], "candidates": [
            candidate for candidate in slot["candidates"] if candidate["p_pairing"] > 0
        ]} for mid, slot in projection["slots"].items()
    }
    projection["teams"] = [
        {"team_id": team, "p_reach": values["p_reach"], "p_title": values["p_title"]}
        for team, values in sorted(projection["teams"].items(), key=lambda item: (-item[1]["p_title"], item[0]))
    ]
    block["projection"] = {
        "model": "primary Elo, ratings frozen for the rest of the playoffs",
        "ratings_through_match_id": through,
        "routing_basis": {"slots": {str(mid): row["basis"]
                           for mid, row in advancement.get("slots", {}).items()},
                          "sources": list(advancement.get("sources", []))},
        **projection,
    }
    block["routing"] = "projected"
    status["title_odds"] = {str(row["team_id"]): row["p_title"] for row in projection["teams"]}
    return status


class _PlayoffResults(dict):
    """Exact public result mapping with DB names retained for completed slots."""
    team_names: dict[int, list[str]]
    unverified: list[int]
    last_seen_at: object
    match_meta: dict[int, dict]


def playoff_results(db, spec: dict) -> dict[int, dict]:
    """Read decisive, source-verified results for the spec's playoff slots."""
    slots = {slot["match_id"]: slot for slot in spec["playoffs"]}
    stages = {slot["match_id"]: slot["stage"] for slot in spec.get("verified_opening_pairings", [])}
    for match_id, stage in stages.items():
        slots.setdefault(match_id, {"match_id": match_id, "stage": stage})
    ids = list(slots)
    out = _PlayoffResults()
    out.team_names = {}
    out.unverified = []
    out.last_seen_at = None
    out.match_meta = {}
    if not ids:
        return out
    rows = db.execute("""
        SELECT m.match_id, m.event_id, m.event_series, m.status,
               mt.team_number, mt.team_id, mt.team_name, mt.series_score, mt.is_winner,
               m.last_seen_at, m.scheduled_at, m.completed_at, m.best_of, m.vlr_url
        FROM match m LEFT JOIN match_team mt ON m.match_id = mt.match_id
        WHERE m.match_id IN (SELECT unnest(?))
        ORDER BY m.match_id, mt.team_number
    """, [ids]).fetchall()
    by_id = {}
    for row in rows:
        by_id.setdefault(row[0], []).append(row)
    out.last_seen_at = max((row[9] for row in rows if row[9] is not None), default=None)
    for row in rows:
        out.match_meta.setdefault(row[0], {"scheduled_at": row[10], "completed_at": row[11],
                                           "best_of": row[12], "url": row[13]})
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


def _later_sides(slot, date_row, fixture, result, results, unverified, logos=None, tags=None):
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
                      "logo": fixture[f"logo_{key}"] if matched else (logos or {}).get(str(team_ids[i])),
                      "tag": fixture[f"tag_{key}"] if matched else (tags or {}).get(str(team_ids[i])),
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


def attach_playoffs(status: dict, spec: dict, fixtures: list[dict], schedule: list[dict], results=None,
                    *, logos=None, tags=None) -> dict:
    """Add the verified opening playoff pairings joined to their model fixtures.

    Only ``verified_opening_pairings`` (pinned names/IDs) appear; the forecast,
    kick-off and market come from a fixture with the same match ID *and* the
    same two team names, otherwise they are withheld (never guessed). Later
    slots are listed as TBD with dates only where the schedule supplies them.
    Routing and title odds stay unresolved/null.
    """
    pairings = spec.get("verified_opening_pairings") or []
    playoff_as_of = getattr(results, "last_seen_at", None)
    if playoff_as_of is not None:
        current = status.get("as_of")
        try:
            current_dt = datetime.fromisoformat(current) if current else None
        except (TypeError, ValueError):
            current_dt = None
        status["as_of"] = max((value for value in (current_dt, playoff_as_of) if value is not None)).isoformat()
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
                    "logo": fixture[f"logo_{key}"] if fixture else (logos or {}).get(str(team_ids[index])),
                    "tag": fixture[f"tag_{key}"] if fixture else (tags or {}).get(str(team_ids[index])),
                    "matches": fixture[f"matches_{key}"] if fixture else None,
                    "p_win": None if p_a is None else (p_a if index == 0 else 1 - p_a)}

        result = (results or {}).get(pairing["match_id"])
        meta = getattr(results, "match_meta", {}).get(pairing["match_id"], {})
        if result and set(result["team_ids"]) != set(team_ids):
            result = None
        result_side_order = None if result is None else [result["team_ids"].index(team_id) for team_id in team_ids]
        entry = {
            "match_id": pairing["match_id"], "stage": pairing["stage"],
            "start": fixture["start"] if fixture else (meta.get("scheduled_at").isoformat() if meta.get("scheduled_at") else None),
            "best_of": fixture["best_of"] if fixture else spec.get("series_best_of", {}).get("playoffs", {}).get(pairing["stage"]),
            "url": fixture.get("url") if fixture else meta.get("url"),
            "played_on": meta.get("completed_at").date().isoformat() if result and meta.get("completed_at") else None,
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
              "best_of": dates.get(slot["match_id"], {}).get("best_of") or spec.get("series_best_of", {}).get("playoffs", {}).get(slot["stage"]),
              "played_on": (getattr(results, "match_meta", {}).get(slot["match_id"], {}).get("completed_at").date().isoformat()
                            if (results or {}).get(slot["match_id"]) and getattr(results, "match_meta", {}).get(slot["match_id"], {}).get("completed_at") else None)}
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
            row["sides"] = _later_sides(slot, dates.get(slot_id), by_id.get(slot_id), found, results, unverified, logos, tags)
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
    from .logos import load_logos, load_tags

    bracket = load_bracket_spec(2766)
    with connect(read_only=True) as connection:
        status = champions_status(connection, bracket)
        results = playoff_results(connection, bracket)
    ratings, counts, through = current_elo()
    status = attach_group_odds(status, ratings, counts, through)
    status = attach_playoffs(status, bracket, dashboard_fixtures(),
                             playoff_schedule([slot["match_id"] for slot in bracket["playoffs"]]), results,
                             logos=load_logos(), tags=load_tags())
    status = attach_playoff_projection(status, bracket, results, ratings, counts, through)
    print(json.dumps(status))
