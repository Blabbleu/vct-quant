"""Refresh map and player details for recently completed Tier-1 matches."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from . import db
from .config import RAW_VLRGG_DIR
from .etl import normalize
from .ingest import vlrgg

logger = logging.getLogger(__name__)

TARGETS_SQL = """
SELECT m.match_id
FROM match m
JOIN event e USING (event_id)
JOIN match_team mt1 ON mt1.match_id = m.match_id AND mt1.team_number = 1
JOIN match_team mt2 ON mt2.match_id = m.match_id AND mt2.team_number = 2
WHERE m.completed_at IS NOT NULL
  AND CAST(m.completed_at AS DATE) >= ?
  AND e.tier IN ({tiers})
  AND NOT EXISTS (SELECT 1 FROM match_map mm WHERE mm.match_id = m.match_id)
  AND mt1.series_score IS NOT NULL AND mt2.series_score IS NOT NULL
  AND (mt1.series_score > 0 OR mt2.series_score > 0)
  AND lower(coalesce(m.status, '')) NOT LIKE '%forfeit%'
  AND lower(coalesce(mt1.team_name, '') || ' ' || coalesce(mt2.team_name, '')) NOT LIKE '%forfeit%'
ORDER BY m.completed_at DESC, m.match_id DESC
"""


def targets(con, since: date, tiers: tuple[int, ...] = (1,)) -> list[int]:
    if not tiers:
        return []
    placeholders = ", ".join("?" for _ in tiers)
    rows = con.execute(TARGETS_SQL.format(tiers=placeholders), [since, *tiers]).fetchall()
    return [int(row[0]) for row in rows]


def already_have(match_id: int) -> bool:
    return any(RAW_VLRGG_DIR.glob(f"match_details_{match_id}_*.json"))


def refresh_recent_details(
    days: int = 14,
    max_matches: int = 30,
    fetch: Callable[[int], object] | None = None,
    load: Callable[[], object] | None = None,
) -> dict[str, int]:
    """Fetch recent missing details, isolating all per-match and load failures."""
    fetch = fetch or vlrgg.fetch_match_details
    load = load or normalize.load_vlrgg_match_details
    since = datetime.now(timezone.utc).date() - timedelta(days=days)
    con = db.connect(read_only=True)
    try:
        match_ids = targets(con, since)
    finally:
        con.close()

    candidates = [match_id for match_id in match_ids if not already_have(match_id)]
    selected = candidates[:max_matches]
    fetched = failed = 0
    for match_id in selected:
        try:
            fetch(match_id)
            fetched += 1
        except Exception as exc:
            failed += 1
            logger.error("recent details: %s FAILED %s: %s", match_id, type(exc).__name__, exc)

    loaded = 0
    if fetched:
        try:
            load()
            loaded = 1
        except Exception as exc:
            failed += 1
            logger.error("recent details: load FAILED %s: %s", type(exc).__name__, exc)
    return {"targets": len(selected), "fetched": fetched, "failed": failed, "loaded": loaded}
