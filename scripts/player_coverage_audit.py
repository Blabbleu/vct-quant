"""Read-only audit of freshness for scored Tier-1 player-map statistics."""
from __future__ import annotations

import json

from vct_quant import db


_SQL = """
SELECT mt.team_id, t.name, m.match_id, m.completed_at,
       count(DISTINCT CASE WHEN own.total_rounds IS NOT NULL
                                AND opp.total_rounds IS NOT NULL
                                AND own.total_rounds + opp.total_rounds > 0
                           THEN mm.match_map_id END) AS scored_maps,
       count(DISTINCT CASE WHEN own.total_rounds IS NOT NULL
                                AND opp.total_rounds IS NOT NULL
                                AND own.total_rounds + opp.total_rounds > 0
                           THEN s.match_map_id END) AS covered_maps
FROM match m
JOIN event e ON e.event_id = m.event_id AND e.tier = 1
JOIN match_team mt ON mt.match_id = m.match_id AND mt.team_id IS NOT NULL
JOIN match_team opp_team ON opp_team.match_id = m.match_id
    AND opp_team.team_number = 3 - mt.team_number AND opp_team.team_id IS NOT NULL
JOIN team t ON t.team_id = mt.team_id
LEFT JOIN match_map mm ON mm.match_id = m.match_id
LEFT JOIN match_map_team_score own
  ON own.match_map_id = mm.match_map_id AND own.team_number = mt.team_number
LEFT JOIN match_map_team_score opp
  ON opp.match_map_id = mm.match_map_id AND opp.team_number = opp_team.team_number
LEFT JOIN match_map_player_stat s
  ON s.match_map_id = mm.match_map_id AND s.team_number = mt.team_number
WHERE m.completed_at IS NOT NULL AND mt.is_winner IS NOT NULL
  AND mt.series_score IS NOT NULL AND opp_team.series_score IS NOT NULL
  AND mt.series_score + opp_team.series_score > 0
  AND lower(trim(mt.team_name)) <> 'tbd'
  AND lower(trim(opp_team.team_name)) <> 'tbd'
GROUP BY mt.team_id, t.name, m.match_id, m.completed_at
ORDER BY mt.team_id, m.completed_at, m.match_id
"""


def summarize(rows: list[tuple]) -> list[dict]:
    """Summarize chronological (team, name, match, date, scored-map, covered-map) rows."""
    by_team: dict[int, list[tuple]] = {}
    names: dict[int, str] = {}
    for team_id, name, match_id, completed_at, scored_maps, covered_maps in rows:
        team_id = int(team_id)
        by_team.setdefault(team_id, []).append(
            (int(match_id), completed_at, int(scored_maps), int(covered_maps))
        )
        names[team_id] = str(name)

    result = []
    for team_id, matches in by_team.items():
        covered = [row for row in matches if row[3] > 0]
        latest = matches[-1]
        latest_covered = covered[-1] if covered else None
        since_covered = 0
        for row in reversed(matches):
            if row[3] > 0:
                break
            since_covered += 1
        recent = matches[-5:]
        result.append({
            "team_id": team_id,
            "team": names[team_id],
            "played_series": len(matches),
            "latest_series_match_id": latest[0],
            "latest_series_date": latest[1].date().isoformat(),
            "scored_maps_in_latest_series": latest[2],
            "scored_maps_in_history": sum(row[2] for row in matches),
            "maps_with_player_stats_in_history": sum(row[3] for row in matches),
            "scored_maps_missing_player_stats": sum(max(0, row[2] - row[3]) for row in matches),
            "latest_player_stats_match_id": latest_covered[0] if latest_covered else None,
            "latest_player_stats_date": latest_covered[1].date().isoformat() if latest_covered else None,
            "series_since_player_stats": since_covered if latest_covered else len(matches),
            "recent_5_series_with_player_stats": sum(row[3] > 0 for row in recent),
        })
    return sorted(result, key=lambda item: (
        -item["series_since_player_stats"], item["team"].casefold(), item["team_id"]
    ))


def audit() -> list[dict]:
    con = db.connect(read_only=True)
    try:
        return summarize(con.execute(_SQL).fetchall())
    finally:
        con.close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20,
                        help="maximum worst-coverage teams to print (default: 20)")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    rows = audit()
    print(json.dumps({"team_count": len(rows),
                      "teams_with_no_player_stats": sum(r["latest_player_stats_match_id"] is None for r in rows),
                      "teams_with_recent_gap": sum(r["series_since_player_stats"] > 0 for r in rows),
                      "teams_with_scored_maps_missing_stats": sum(r["scored_maps_missing_player_stats"] > 0 for r in rows),
                      "scored_maps_missing_player_stats": sum(r["scored_maps_missing_player_stats"] for r in rows),
                      "worst_coverage": rows[:args.limit]}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
