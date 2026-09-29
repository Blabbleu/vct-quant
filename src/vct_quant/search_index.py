"""Build a compact, read-only client-side search index for official entities."""
from __future__ import annotations

import json
import re

from . import db
from .config import PROCESSED_DIR
from .logos import load_logos, load_tags
from .player_photos import local_photo


def _local_asset(value: object, kind: str) -> str | None:
    if not isinstance(value, str):
        return None
    extensions = r"png|jpg|webp|svg" if kind == "logos" else r"png|jpg|webp"
    pattern = rf"/{kind}/[1-9][0-9]{{0,9}}\.(?:{extensions})"
    return value if re.fullmatch(pattern, value) else None


def build_search_index(*, teams: list[dict], players: list[dict], events: list[dict],
                       logos: dict[str, str] | None = None) -> dict:
    """Shape source rows, excluding unresolved IDs and non-Tier-1/2 entities."""
    logos = logos or {}
    valid_tiers = {1, 2}
    return {
        "teams": [
            {"id": int(row["team_id"]), "name": row["name"], "tag": row.get("tag"),
             "tier": int(row["tier"]), "logo": _local_asset(logos.get(str(row["team_id"])), "logos")}
            for row in teams if row.get("team_id") is not None and row.get("name")
            and row.get("tier") in valid_tiers
        ],
        "players": [
            {"id": int(row["player_id"]), "handle": row["handle"],
             "real_name": row.get("real_name"),
             "team_id": int(row["team_id"]) if row.get("team_id") is not None else None,
             "team_name": row.get("team_name"), "photo": _local_asset(row.get("photo"), "players")}
            for row in players if row.get("player_id") is not None and row.get("handle")
        ],
        "events": [
            {"id": int(row["event_id"]), "name": row["name"], "tier": int(row["tier"])}
            for row in events if row.get("event_id") is not None and row.get("name")
            and row.get("tier") in valid_tiers
        ],
    }


def search_index(con=None) -> dict:
    """Return official teams, players and events observed in match history."""
    owned = con is None
    con = con or db.connect(read_only=True)
    try:
        team_rows = con.execute("""
            WITH seen AS (
              SELECT mt.team_id, min(e.tier) AS tier
              FROM match_team mt JOIN match m USING (match_id)
              JOIN event e ON e.event_id = m.event_id
              WHERE mt.team_id IS NOT NULL AND e.tier IN (1, 2)
              GROUP BY mt.team_id
            )
            SELECT s.team_id, t.name, t.tag, s.tier
            FROM seen s JOIN team t USING (team_id)
            ORDER BY lower(t.name), s.team_id
        """).fetchall()
        player_rows = con.execute("""
            WITH appearances AS (
              SELECT s.player_id, mt.team_id, mt.team_name,
                     row_number() OVER (PARTITION BY s.player_id
                       ORDER BY m.completed_at DESC NULLS LAST, m.match_id DESC,
                                mm.map_number DESC) AS rn
              FROM match_map_player_stat s
              JOIN match_map mm USING (match_map_id)
              JOIN match m USING (match_id)
              JOIN event e ON e.event_id = m.event_id AND e.tier IN (1, 2)
              JOIN match_team mt ON mt.match_id = m.match_id
                                  AND mt.team_number = s.team_number
              WHERE s.player_id IS NOT NULL
            )
            SELECT p.player_id, p.handle, p.real_name, a.team_id, a.team_name
            FROM appearances a JOIN player p USING (player_id)
            WHERE a.rn = 1
            ORDER BY lower(p.handle), p.player_id
        """).fetchall()
        event_rows = con.execute("""
            SELECT DISTINCT e.event_id, e.name, e.tier
            FROM event e JOIN match m ON m.event_id = e.event_id
            WHERE e.tier IN (1, 2)
            ORDER BY lower(e.name), e.event_id
        """).fetchall()
    finally:
        if owned:
            con.close()
    tags = load_tags()
    teams = [{"team_id": tid, "name": name, "tag": tag or tags.get(str(tid)), "tier": tier}
             for tid, name, tag, tier in team_rows]
    players = [{"player_id": pid, "handle": handle, "real_name": real_name,
                "team_id": tid, "team_name": team_name, "photo": local_photo(pid)}
               for pid, handle, real_name, tid, team_name in player_rows]
    events = [{"event_id": eid, "name": name, "tier": tier}
              for eid, name, tier in event_rows]
    return build_search_index(teams=teams, players=players, events=events,
                              logos=load_logos())


def write_search_index() -> dict:
    """Refresh the derived processed cache; raw data and the database are read-only."""
    index = search_index()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / "search_index.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    tmp.replace(path)
    return {"path": str(path), "teams": len(index["teams"]),
            "players": len(index["players"]), "events": len(index["events"])}


def main() -> None:
    print(json.dumps(write_search_index(), allow_nan=False))


if __name__ == "__main__":
    main()
