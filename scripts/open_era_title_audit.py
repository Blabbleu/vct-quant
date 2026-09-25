"""Read-only 2027 title audit across vlr.gg events and upcoming fixtures.

    python scripts/open_era_title_audit.py
    python scripts/open_era_title_audit.py --event-pages 9
    python scripts/open_era_title_audit.py --events-json page1.json page2.json --upcoming-json feed.json

Unlike ingestion this never saves a response into data/raw. A failed endpoint or
requested page is reported as unknown, not as evidence that no 2027 event exists.
Archived mode reads previously saved payloads without network access. "complete"
means every requested source succeeded, not that every vlr.gg event was searched.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import requests

from vct_quant.etl.events import LAST_CHANCE, OPEN_STAGE, VCT_BRANDED, competition_tier
from vct_quant.ingest import vlrgg

SEASON = re.compile(r"\b2027\b")


def segments(payload: dict) -> list[dict]:
    """Reject API error envelopes instead of interpreting them as empty pages."""
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise ValueError("API did not report success")
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("status") != 200:
        raise ValueError("API did not report success")
    rows = data.get("segments")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("invalid segments")
    return rows


def audit(events: dict | list[dict] | None, upcoming: dict | None) -> list[dict]:
    """Return observed 2027 titles; unknown fixture counts remain null on outage."""
    titles: dict[str, dict] = {}
    event_pages = events if isinstance(events, list) else [events] if events is not None else []
    for event in (row for page in event_pages for row in segments(page)):
        title = str(event.get("title") or "").strip()
        if not SEASON.search(title):
            continue
        row = titles.setdefault(title, {"title": title, "event_url": None, "event_id": None,
                                        "upcoming_fixtures": 0 if upcoming is not None else None,
                                        "fixture_calendar_years": [] if upcoming is not None else None,
                                        "calendar_tier_mismatches": [] if upcoming is not None else None,
                                        "candidate_scope_changes": [] if upcoming is not None else None,
                                        "unparsed_fixture_dates": 0 if upcoming is not None else None})
        row["event_url"] = event.get("url_path")
        row["event_id"] = event.get("event_id")
    for fixture in segments(upcoming) if upcoming is not None else []:
        title = str(fixture.get("match_event") or "").strip()
        if not SEASON.search(title):
            continue
        row = titles.setdefault(title, {"title": title, "event_url": None, "event_id": None,
                                        "upcoming_fixtures": 0, "fixture_calendar_years": [],
                                        "calendar_tier_mismatches": [],
                                        "candidate_scope_changes": [],
                                        "unparsed_fixture_dates": 0})
        row["upcoming_fixtures"] += 1
        when = str(fixture.get("unix_timestamp") or "")
        try:
            year = datetime.fromisoformat(when).year
        except ValueError:
            row["unparsed_fixture_dates"] += 1
            continue  # A missing or malformed date is not evidence of a safe tier.
        if year not in row["fixture_calendar_years"]:
            row["fixture_calendar_years"].append(year)
        calendar_tier = competition_tier(title, year, title_season_override=False)
        title_tier = competition_tier(title, title_season_override=False)
        candidate_tier = competition_tier(title, year, title_season_override=True)
        if calendar_tier != candidate_tier:
            row["candidate_scope_changes"].append({
                "match_page": fixture.get("match_page"), "scheduled_at": when,
                "current_tier": calendar_tier, "candidate_tier": candidate_tier,
            })
        if calendar_tier != title_tier:
            row["calendar_tier_mismatches"].append({
                "match_page": fixture.get("match_page"), "scheduled_at": when,
                "calendar_tier": calendar_tier, "title_tier": title_tier,
            })
    result = []
    for row in titles.values():
        title = row["title"]
        row["vct_branded"] = bool(VCT_BRANDED.match(title.lower()))
        row["tier_if_2026"] = competition_tier(title, 2026, title_season_override=False)
        row["tier_by_title"] = competition_tier(title, title_season_override=False)
        row["candidate_tier_if_2026"] = competition_tier(title, 2026, title_season_override=True)
        row["candidate_tier_by_title"] = competition_tier(title, title_season_override=True)
        if row["fixture_calendar_years"] is not None:
            row["fixture_calendar_years"].sort()
        result.append(row)
    return sorted(result, key=lambda row: row["title"])


def yearless_open_event_candidates(events: list[dict]) -> list[dict] | None:
    """Flag upcoming VCT open-stage event cards even before fixtures are listed.

    Event cards often give month/day but no year; neither status nor a date
    string verifies which VCT season the event belongs to.
    """
    if not events:
        return None  # An event outage is not an empty candidate set.
    found = {}
    for event in (row for page in events for row in segments(page)):
        title = str(event.get("title") or "").strip()
        lower = title.lower()
        if (str(event.get("status") or "").lower() != "upcoming"
                or re.search(r"\b20\d\d\b", lower)
                or not VCT_BRANDED.match(lower)
                or not (OPEN_STAGE.search(lower) or LAST_CHANCE.search(lower))):
            continue
        key = event.get("event_id") or title
        found[key] = {"title": title, "event_id": event.get("event_id"),
                      "event_url": event.get("url_path"), "status": event.get("status"),
                      "dates_raw": event.get("dates")}
    return sorted(found.values(), key=lambda row: row["title"])


def yearless_open_candidates(upcoming: dict | None) -> list[dict] | None:
    """Surface dated open-stage fixtures lacking a year in their event title.

    A late-2026 match *might* qualify for 2027, but neither its date nor its
    stage proves the event season. Keep these separate from observed 2027 titles.
    """
    if upcoming is None:
        return None  # Feed outage is not an empty candidate set.
    found: dict[str, dict] = {}
    for fixture in segments(upcoming):
        title = str(fixture.get("match_event") or "").strip()
        lower = title.lower()
        if (re.search(r"\b20\d\d\b", lower) or not VCT_BRANDED.match(lower)
                or not (OPEN_STAGE.search(lower) or LAST_CHANCE.search(lower))):
            continue
        when = str(fixture.get("unix_timestamp") or "")
        try:
            start = datetime.fromisoformat(when)
        except ValueError:
            continue
        if not ((start.year == 2026 and start.month >= 11) or start.year == 2027):
            continue
        row = found.setdefault(title, {"title": title, "fixture_count": 0, "fixtures": []})
        row["fixture_count"] += 1
        row["fixtures"].append({"match_page": fixture.get("match_page"), "scheduled_at": when})
    return sorted(found.values(), key=lambda row: row["title"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-json", type=Path, nargs="+", help="archived event pages (read only)")
    parser.add_argument("--upcoming-json", type=Path, help="archived upcoming feed (read only)")
    parser.add_argument("--event-pages", type=int, default=1,
                        help="number of live event pages to inspect (default: 1, max: 9)")
    args = parser.parse_args()
    if bool(args.events_json) != bool(args.upcoming_json):
        parser.error("provide both archived payloads or neither")
    if not 1 <= args.event_pages <= 9:
        parser.error("--event-pages must be between 1 and 9")
    if args.events_json and args.event_pages != 1:
        parser.error("--event-pages applies to live mode; list archive paths instead")
    errors = {}
    event_pages = []
    checked = []
    seen_nonempty_pages = {}
    paths = args.events_json if args.events_json else [None] * args.event_pages
    for page_num, path in enumerate(paths, 1):
        try:
            payload = (json.loads(path.read_text(encoding="utf-8")) if path
                       else vlrgg.fetch_events(page_num, save=False))
            rows = segments(payload)
            # A repeated nonempty page is a pagination failure, not more coverage.
            # Empty pages can legitimately repeat at the end of the listing.
            if rows:
                signature = json.dumps(rows, sort_keys=True)
                if signature in seen_nonempty_pages:
                    raise ValueError(f"duplicate of page {seen_nonempty_pages[signature]}")
                seen_nonempty_pages[signature] = page_num
            event_pages.append(payload)
            checked.append(page_num)
        except (OSError, ValueError, KeyError, TypeError, requests.RequestException) as exc:
            # A failed page is unknown, never a negative 2027 observation.
            errors["events" if page_num == 1 else f"events_page_{page_num}"] = f"{type(exc).__name__}: {exc}"
    upcoming = None
    try:
        upcoming = (json.loads(args.upcoming_json.read_text(encoding="utf-8"))
                    if args.upcoming_json else vlrgg.fetch_upcoming_matches(save=False))
        segments(upcoming)
    except (OSError, ValueError, KeyError, TypeError, requests.RequestException) as exc:
        errors["upcoming"] = f"{type(exc).__name__}: {exc}"
        upcoming = None
    rows = audit(event_pages, upcoming)
    report = {"source": "archive" if args.events_json else "live",
              "complete": not errors,
              "event_pages_checked": checked,
              "event_rows": sum(len(segments(page)) for page in event_pages) if checked else None,
              "fixture_rows": len(segments(upcoming)) if upcoming is not None else None,
              "yearless_open_event_candidates": yearless_open_event_candidates(event_pages),
              "yearless_open_candidates": yearless_open_candidates(upcoming)}
    if errors:
        # Observations from a healthy source survive a partial outage, but an
        # empty list cannot establish that no 2027 title exists across sources.
        report["errors"] = errors
        report["observed_2027_titles"] = rows
        print(json.dumps(report, indent=2))
        raise SystemExit(1)
    report["season_2027_titles"] = rows
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
