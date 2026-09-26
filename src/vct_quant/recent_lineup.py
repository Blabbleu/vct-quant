"""Bounded exact-ID historical player links, not a current or expected lineup."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, time, timezone

from . import db

_SQL = """
WITH recent_maps AS (
    SELECT mm.match_map_id, m.completed_at, m.match_id, mt.team_number
    FROM match m
    JOIN event e ON e.event_id = m.event_id AND e.tier = 1
    JOIN match_team mt ON mt.match_id = m.match_id AND mt.team_id = ?
    JOIN match_team opp ON opp.match_id = m.match_id AND opp.team_number = 3 - mt.team_number
    JOIN match_map mm ON mm.match_id = m.match_id
    JOIN match_map_team_score own ON own.match_map_id = mm.match_map_id AND own.team_number = mt.team_number
    JOIN match_map_team_score other ON other.match_map_id = mm.match_map_id AND other.team_number = opp.team_number
    WHERE m.completed_at IS NOT NULL AND m.completed_at < ?
      AND opp.team_id IS NOT NULL AND lower(trim(mt.team_name)) <> 'tbd'
      AND lower(trim(opp.team_name)) <> 'tbd'
      AND own.total_rounds IS NOT NULL AND other.total_rounds IS NOT NULL
      AND own.total_rounds + other.total_rounds > 0
    ORDER BY m.completed_at DESC, m.match_id DESC, mm.map_number DESC
    LIMIT ?
)
SELECT rm.match_map_id, rm.completed_at, rm.match_id, s.player_id, p.handle
FROM recent_maps rm
LEFT JOIN match_map_player_stat s ON s.match_map_id = rm.match_map_id
    AND s.team_number = rm.team_number AND s.player_id > 0
LEFT JOIN player p ON p.player_id = s.player_id
ORDER BY rm.completed_at DESC, rm.match_id DESC, rm.match_map_id DESC
"""


def recent_lineup(team_id: int, *, con=None, as_of: datetime | None = None,
                  map_limit: int = 5, player_limit: int = 10) -> dict:
    """Link IDs observed in the last scored maps strictly before the UTC day."""
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    if team_id <= 0 or map_limit <= 0 or player_limit <= 0:
        raise ValueError("IDs and limits must be positive")
    cutoff = datetime.combine(now.astimezone(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    owned = con is None
    con = con or db.connect(read_only=True)
    try:
        rows = con.execute(_SQL, [team_id, cutoff, map_limit]).fetchall()
    finally:
        if owned:
            con.close()
    maps = {int(row[0]) for row in rows}
    counts: Counter[int] = Counter()
    names: dict[int, str] = {}
    seen: set[tuple[int, int]] = set()
    for map_id, _, _, player_id, handle in rows:
        if player_id is None or handle is None:
            continue
        key = (int(map_id), int(player_id))
        if key in seen:
            continue
        seen.add(key)
        counts[int(player_id)] += 1
        names[int(player_id)] = handle
    players = [{"player_id": pid, "handle": names[pid], "maps": count}
               for pid, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:player_limit]]
    return {"maps_sampled": len(maps), "latest_map_date": rows[0][1].date().isoformat() if rows else None,
            "latest_match_id": int(rows[0][2]) if rows else None, "players": players}
