"""Fetch map and player details for recent completed matches.

    python scripts/backfill_recent_details.py --dry-run
    python scripts/backfill_recent_details.py --since 2026-06-01
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from vct_quant import db
from vct_quant.etl import normalize
from vct_quant.ingest import vlrgg
from vct_quant.recent_details import TARGETS_SQL, already_have, targets


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
