"""Read-only 2027 title audit across vlr.gg events and upcoming fixtures.

    python scripts/open_era_title_audit.py
    python scripts/open_era_title_audit.py --events-json path --upcoming-json path

Unlike ingestion this never saves a response into data/raw. A failed endpoint is
reported as unknown, not as evidence that no 2027 event exists. Archived mode
reads previously saved payloads without network access.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import requests

from vct_quant.etl.events import VCT_BRANDED, competition_tier
from vct_quant.ingest import vlrgg

SEASON = re.compile(r"\b2027\b")


def segments(payload: dict) -> list[dict]:
    """Reject API error envelopes instead of interpreting them as empty pages."""
    if payload.get("status") != "success" or payload.get("data", {}).get("status") != 200:
        raise ValueError("API did not report success")
    rows = payload["data"]["segments"]
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("invalid segments")
    return rows


def audit(events: dict | None, upcoming: dict | None) -> list[dict]:
    """Return observed 2027 titles; unknown fixture counts remain null on outage."""
    titles: dict[str, dict] = {}
    for event in segments(events) if events is not None else []:
        title = str(event.get("title") or "").strip()
        if not SEASON.search(title):
            continue
        row = titles.setdefault(title, {"title": title, "event_url": None, "event_id": None,
                                        "upcoming_fixtures": 0 if upcoming is not None else None})
        row["event_url"] = event.get("url_path")
        row["event_id"] = event.get("event_id")
    for fixture in segments(upcoming) if upcoming is not None else []:
        title = str(fixture.get("match_event") or "").strip()
        if not SEASON.search(title):
            continue
        row = titles.setdefault(title, {"title": title, "event_url": None, "event_id": None,
                                        "upcoming_fixtures": 0})
        row["upcoming_fixtures"] += 1
    result = []
    for row in titles.values():
        title = row["title"]
        row["vct_branded"] = bool(VCT_BRANDED.match(title.lower()))
        row["tier_current"] = competition_tier(title, 2026)
        row["tier_by_title"] = competition_tier(title)
        result.append(row)
    return sorted(result, key=lambda row: row["title"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-json", type=Path, help="archived event page (read only)")
    parser.add_argument("--upcoming-json", type=Path, help="archived upcoming feed (read only)")
    args = parser.parse_args()
    if bool(args.events_json) != bool(args.upcoming_json):
        parser.error("provide both archived payloads or neither")
    errors = {}
    payloads = {}
    sources = {
        "events": (args.events_json, lambda: vlrgg.fetch_events(1, save=False)),
        "upcoming": (args.upcoming_json, lambda: vlrgg.fetch_upcoming_matches(save=False)),
    }
    for name, (path, fetch) in sources.items():
        try:
            payload = json.loads(path.read_text(encoding="utf-8")) if path else fetch()
            segments(payload)
            payloads[name] = payload
        except (OSError, ValueError, KeyError, TypeError, requests.RequestException) as exc:
            # A failed source is unknown, never a negative 2027 observation.
            errors[name] = f"{type(exc).__name__}: {exc}"
    rows = audit(payloads.get("events"), payloads.get("upcoming"))
    report = {"source": "archive" if args.events_json else "live",
              "complete": not errors,
              "event_rows": len(segments(payloads["events"])) if "events" in payloads else None,
              "fixture_rows": len(segments(payloads["upcoming"])) if "upcoming" in payloads else None}
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
