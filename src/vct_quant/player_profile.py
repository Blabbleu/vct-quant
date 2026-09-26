"""Read-only exact-ID player page data from scored Tier-1 maps.

This describes recorded history, not a pre-match rating or forecast input. No
handle matching: a renamed player retains their ID; same-name players do not mix.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, time, timezone

from . import db

_SQL = """
SELECT m.match_id, m.completed_at, mm.map_number, mm.map_name,
       s.agent_name, CAST(s.rating AS DOUBLE), CAST(s.acs AS DOUBLE),
       s.kills, s.deaths, s.assists,
       mt.team_id, mt.team_name, opp.team_id, opp.team_name,
       own.total_rounds, other.total_rounds
FROM match_map_player_stat s
JOIN match_map mm ON mm.match_map_id = s.match_map_id
JOIN match m ON m.match_id = mm.match_id
JOIN event e ON e.event_id = m.event_id AND e.tier = 1
JOIN match_team mt ON mt.match_id = m.match_id AND mt.team_number = s.team_number
JOIN match_team opp ON opp.match_id = m.match_id AND opp.team_number = 3 - s.team_number
JOIN match_map_team_score own ON own.match_map_id = mm.match_map_id AND own.team_number = s.team_number
JOIN match_map_team_score other ON other.match_map_id = mm.match_map_id AND other.team_number = 3 - s.team_number
WHERE s.player_id = ? AND m.completed_at IS NOT NULL AND m.completed_at < ?
  AND mt.team_id IS NOT NULL AND opp.team_id IS NOT NULL
  AND lower(trim(mt.team_name)) <> 'tbd' AND lower(trim(opp.team_name)) <> 'tbd'
  AND own.total_rounds IS NOT NULL AND other.total_rounds IS NOT NULL
  AND own.total_rounds + other.total_rounds > 0
ORDER BY m.completed_at DESC, m.match_id DESC, mm.map_number DESC
"""


def player_profile(player_id: int, *, con=None, as_of: datetime | None = None,
                   limit: int = 20) -> dict | None:
    """Recorded map stats as of the prior UTC day (source dates are day-only)."""
    if player_id <= 0:
        return None
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    cutoff = datetime.combine(now.astimezone(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    owned = con is None
    con = con or db.connect(read_only=True)
    try:
        player = con.execute("SELECT handle, country FROM player WHERE player_id = ?", [player_id]).fetchone()
        if player is None:
            return None
        rows = con.execute(_SQL, [player_id, cutoff]).fetchall()
    finally:
        if owned:
            con.close()
    agents: Counter[str] = Counter()
    teams: Counter[int] = Counter()
    team_names: dict[int, str] = {}
    maps = []
    def optional(value):
        return float(value) if value is not None else None
    for (mid, completed, number, map_name, agent, rating, acs, kills, deaths, assists,
         tid, team_name, oid, opponent, own, other) in rows:
        normalized_agent = agent.strip().title() if agent and agent.strip() else "Unknown"
        agents[normalized_agent] += 1
        teams[int(tid)] += 1
        team_names.setdefault(int(tid), team_name)
        if len(maps) < limit:
            maps.append({
                "match_id": int(mid), "completed_at": completed.isoformat(),
                "map_number": int(number), "map": map_name,
                "team_id": int(tid), "team": team_name,
                "opponent_id": int(oid), "opponent": opponent,
                "agent": normalized_agent if normalized_agent != "Unknown" else None,
                "result": "W" if own > other else "L" if own < other else "D",
                "rounds_for": int(own), "rounds_against": int(other),
                "rating": optional(rating), "acs": optional(acs),
                "kills": kills, "deaths": deaths, "assists": assists,
            })
    return {
        "player_id": player_id, "handle": player[0], "country": player[1],
        "recorded_maps": len(rows), "maps": maps,
        "agents": [{"agent": a, "maps": n} for a, n in agents.most_common()],
        "teams": [{"team_id": tid, "name": team_names[tid], "maps": n}
                  for tid, n in teams.most_common()],
        "note": "Recorded, dated Tier-1 maps before today (UTC). Stats and teams may be incomplete; this is not a player rating or forecast.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("player_id", type=int)
    args = parser.parse_args()
    print(json.dumps(player_profile(args.player_id), allow_nan=False))


if __name__ == "__main__":
    main()
