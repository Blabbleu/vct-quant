"""Harvest event match lists from vlrggapi into data/raw/vlrgg/.

    python scripts/backfill_vlrgg.py --pages 12          # recent seasons
    python scripts/backfill_vlrgg.py --pages 40 --filter ''   # everything

Why this exists: the Kaggle corpus has no dates anywhere, and it thins out badly
after 2022 (331 matches for all of VCT 2023). `/v2/events/matches` returns a real
date plus both teams' scores for a whole event in one request, so a season costs
a few dozen calls rather than one per match.

Harvest only — this writes raw JSON and stops there, per the project rule that
raw is captured verbatim before anything parses it. Loading into the canonical
tables is `etl/normalize.py::load_vlrgg_match_results`.

Resumable: an event whose file already exists is skipped, so re-running after an
interruption costs nothing. Pass --force to refetch anyway (ongoing events gain
matches over time).
"""
from __future__ import annotations

import argparse
import re
import sys

from vct_quant.config import RAW_VLRGG_DIR
from vct_quant.ingest import vlrgg

# Tiers worth having. Everything else on vlr.gg is regional amateur play that the
# Kaggle corpus never covered either.
DEFAULT_FILTER = r"vct|champions|masters|challengers|game changers|vcl|ascension"


def already_have(event_id: str) -> bool:
    return any(RAW_VLRGG_DIR.glob(f"event_matches_{event_id}_*.json"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", type=int, default=12, help="event listing pages to walk")
    ap.add_argument("--filter", default=DEFAULT_FILTER, help="regex on event title; '' for all")
    ap.add_argument("--force", action="store_true", help="refetch events already on disk")
    args = ap.parse_args()

    pattern = re.compile(args.filter, re.I) if args.filter else None

    events: list[dict] = []
    for page in range(1, args.pages + 1):
        try:
            segments = vlrgg.fetch_events(page)["data"]["segments"]
        except Exception as exc:  # one bad page should not lose the whole run
            print(f"  page {page}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if not segments:
            break
        keep = [s for s in segments if pattern is None or pattern.search(s["title"])]
        events.extend(keep)
        print(f"page {page:>3}: {len(segments):>3} events, {len(keep):>3} kept")

    todo = [e for e in events if args.force or not already_have(e["event_id"])]
    print(f"\n{len(events)} events matched, {len(events) - len(todo)} already on disk, "
          f"{len(todo)} to fetch (~{len(todo) * vlrgg.REQUEST_DELAY_S / 60:.0f} min)\n")

    matches = failed = 0
    for i, event in enumerate(todo, 1):
        try:
            segments = vlrgg.fetch_event_matches(event["event_id"])["data"]["segments"]
        except Exception as exc:
            failed += 1
            print(f"[{i}/{len(todo)}] {event['title'][:50]:50} FAILED {type(exc).__name__}")
            continue
        matches += len(segments)
        print(f"[{i}/{len(todo)}] {event['title'][:50]:50} {len(segments):>4} matches")

    print(f"\n{matches:,} matches across {len(todo) - failed} events -> {RAW_VLRGG_DIR}")
    if failed:
        print(f"{failed} events failed; re-run to retry just those.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
