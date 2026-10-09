"""Fetch map and player details for recent completed matches.

    python scripts/backfill_recent_details.py --dry-run
    python scripts/backfill_recent_details.py --since 2026-06-01
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from vct_quant import db
from vct_quant.config import RAW_VLRGG_DIR
from vct_quant.etl import normalize
from vct_quant.ingest import vlrgg


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=date.fromisoformat, default=date(2026, 6, 1))
    parser.add_argument("--tier", type=int, action="append", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-matches", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--load", action="store_true")
    args = parser.parse_args(argv)
    if args.max_matches is not None and args.max_matches < 1:
        parser.error("--max-matches must be positive")
    tiers = tuple(args.tier) if args.tier is not None else (1,)
    con = db.connect(read_only=True)
    try:
        match_ids = targets(con, args.since, tiers)
    finally:
        con.close()
    if not args.force:
        match_ids = [match_id for match_id in match_ids if not already_have(match_id)]
    if args.max_matches is not None:
        match_ids = match_ids[:args.max_matches]
    print(f"{len(match_ids)} match details to fetch")
    if args.dry_run:
        print("match ids:", " ".join(map(str, match_ids[:20])))
        return 0

    failed = 0
    for index, match_id in enumerate(match_ids, 1):
        try:
            vlrgg.fetch_match_details(match_id)
            print(f"[{index}/{len(match_ids)}] {match_id}: saved")
        except Exception as exc:
            failed += 1
            print(f"[{index}/{len(match_ids)}] {match_id}: FAILED {type(exc).__name__}: {exc}", file=sys.stderr)
    if args.load:
        try:
            report = normalize.load_vlrgg_match_details()
            print(report)
        except Exception as exc:
            failed += 1
            print(f"load: FAILED {type(exc).__name__}: {exc}", file=sys.stderr)
    print(f"done: {len(match_ids) - failed} saved, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
