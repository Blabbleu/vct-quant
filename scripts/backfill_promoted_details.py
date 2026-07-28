"""Fetch player/map details for promoted teams' final Tier-2 matches.

    python scripts/backfill_promoted_details.py --dry-run
    python scripts/backfill_promoted_details.py --max-matches 1  # payload probe
    python scripts/backfill_promoted_details.py

Targets are derived from DuckDB: a promoted team played Ascension and then
appeared in Tier 1. Existing raw payloads are skipped.
"""
from __future__ import annotations

import argparse
import sys

from vct_quant import db
from vct_quant.config import RAW_VLRGG_DIR
from vct_quant.ingest import vlrgg


TARGETS_SQL = """
WITH ascension_teams AS (
    SELECT mt.team_id, max(m.completed_at) AS ascension_end
    FROM match_team mt
    JOIN match m USING (match_id)
    JOIN event e USING (event_id)
    WHERE mt.team_id IS NOT NULL
      AND m.completed_at IS NOT NULL
      AND e.tier = 2
      AND lower(e.name) LIKE '%ascension%'
    GROUP BY mt.team_id
),
promotions AS (
    SELECT a.team_id, min(m.completed_at) AS promoted_at
    FROM ascension_teams a
    JOIN match_team mt USING (team_id)
    JOIN match m USING (match_id)
    JOIN event e USING (event_id)
    WHERE e.tier = 1 AND m.completed_at > a.ascension_end
    GROUP BY a.team_id
),
appearances AS (
    SELECT mt.team_id, mt.team_name, m.match_id, m.completed_at, e.tier
    FROM match_team mt
    JOIN match m USING (match_id)
    JOIN event e USING (event_id)
    WHERE mt.team_id IS NOT NULL
      AND m.completed_at IS NOT NULL
      AND e.tier IN (1, 2)
),
ranked AS (
    SELECT a.match_id, a.team_id, a.team_name,
           row_number() OVER (
               PARTITION BY a.team_id
               ORDER BY a.completed_at DESC, a.match_id DESC
           ) AS recency
    FROM appearances a
    JOIN promotions f USING (team_id)
    WHERE a.tier = 2 AND a.completed_at < f.promoted_at
)
SELECT match_id, team_id, team_name
FROM ranked
WHERE recency <= ?
ORDER BY match_id
"""


def targets(limit_per_team: int) -> tuple[list[int], int]:
    with db.connect(read_only=True) as con:
        rows = con.execute(TARGETS_SQL, [limit_per_team]).fetchall()
    return sorted({int(row[0]) for row in rows}), len({int(row[1]) for row in rows})


def already_have(match_id: int) -> bool:
    return any(RAW_VLRGG_DIR.glob(f"match_details_{match_id}_*.json"))


def player_rows(payload: dict) -> int:
    data = payload.get("data", {})
    details = data.get("segments") or [data]
    return sum(
        len(players)
        for detail in details
        for game_map in detail.get("maps", [])
        for players in game_map.get("players", {}).values()
        if isinstance(players, list)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-per-team", type=int, default=20)
    parser.add_argument("--max-matches", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.limit_per_team < 1 or (args.max_matches is not None and args.max_matches < 1):
        parser.error("limits must be positive")

    match_ids, team_count = targets(args.limit_per_team)
    if not args.force:
        match_ids = [match_id for match_id in match_ids if not already_have(match_id)]
    if args.max_matches is not None:
        match_ids = match_ids[:args.max_matches]

    print(f"{team_count} promoted teams -> {len(match_ids)} match details to fetch")
    if args.dry_run:
        print("match ids:", " ".join(map(str, match_ids[:20])))
        return 0

    failed = empty = 0
    for index, match_id in enumerate(match_ids, 1):
        try:
            payload = vlrgg.fetch_match_details(match_id)
            count = player_rows(payload)
            empty += count == 0
            print(f"[{index}/{len(match_ids)}] {match_id}: {count} player-map rows")
        except Exception as exc:
            failed += 1
            print(
                f"[{index}/{len(match_ids)}] {match_id}: "
                f"FAILED {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    print(f"done: {len(match_ids) - failed} saved, {empty} without player stats, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
