"""Read-only audit of full-veto availability in raw details and current fixtures.

    python scripts/veto_source_audit.py
    python scripts/veto_source_audit.py --live --limit 8
    python scripts/veto_source_audit.py --live --within-hours 1 --limit 8

Never writes to data/raw. A historical final-page veto is NOT pre-start evidence.
The optional live probe does not persist observations and cannot be used for
backtesting; a timestamped collector would need separate live-side approval.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from vct_quant.config import RAW_VLRGG_DIR, SETTINGS


def parse_full_veto(text: str) -> dict | None:
    """Accept seven unique map decisions with two (Bo3) or four (Bo5) picks."""
    parts = [part.strip() for part in text.split(";")]
    if len(parts) != 7:
        return None
    picks, bans, deciders = [], [], []
    for part in parts:
        if " pick " in part:
            team, name = part.split(" pick ", 1)
            if not team.strip() or not name.strip():
                return None
            picks.append(name.strip())
        elif " ban " in part:
            team, name = part.split(" ban ", 1)
            if not team.strip() or not name.strip():
                return None
            bans.append(name.strip())
        elif part.endswith(" remains"):
            deciders.append(part.removesuffix(" remains").strip())
        else:
            return None
    maps = picks + bans + deciders
    if (len(deciders) != 1 or len(picks) not in (2, 4)
            or len(bans) != 6 - len(picks)
            or len({name.casefold() for name in maps}) != 7
            or not all(maps)):
        return None
    return {"best_of": len(picks) + 1, "picks": picks, "decider": deciders[0]}


def segment(payload: dict) -> dict | None:
    """API v2 nests match details under data.segments[0]."""
    data = payload.get("data") or {}
    segments = data.get("segments") or []
    return segments[0] if segments and isinstance(segments[0], dict) else None


def archived_audit(root: Path) -> Counter:
    counts: Counter = Counter()
    for path in root.glob("match_details_*.json"):
        counts["detail_snapshots"] += 1
        try:
            detail = segment(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            detail = None
        if detail is None:
            counts["unreadable"] += 1
            continue
        status = str(detail.get("status", ""))
        counts["final"] += status == "final"
        veto = str(detail.get("map_vetos") or "").strip()
        counts["nonempty_veto"] += bool(veto)
        counts["full_veto"] += parse_full_veto(veto) is not None
        counts["incomplete_or_placeholder"] += bool(veto) and parse_full_veto(veto) is None
    return counts


def live_audit(base_url: str, limit: int, within_hours: float | None = None) -> tuple[Counter, list[str]]:
    """Probe fixtures, optionally selecting the nearest pre-start window."""
    counts: Counter = Counter()
    lines: list[str] = []
    session = requests.Session()
    try:
        response = session.get(f"{base_url}/v2/match", params={"q": "upcoming"}, timeout=30)
        response.raise_for_status()
        fixtures = response.json()["data"]["segments"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        counts["feed_api_errors"] += 1
        lines.append(f"Upcoming feed unavailable: {type(exc).__name__}: {exc}")
        return counts, lines
    # A TBD/rescheduled fixture can have no parseable start. Keep it distinct
    # from an observed negative veto and never let it abort the other probes.
    dated = []
    for fixture in fixtures:
        try:
            start = datetime.strptime(fixture["unix_timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError, KeyError):
            counts["invalid_start"] += 1
            lines.append(f"{fixture.get('match_page', '<unknown>')}: invalid start {fixture.get('unix_timestamp')!r}")
            continue
        dated.append((start, fixture))
    if within_hours is not None:
        cutoff = datetime.now(timezone.utc) + timedelta(hours=within_hours)
        near = []
        for start, fixture in dated:
            if start > cutoff:
                counts["outside_window"] += 1
            elif start > datetime.now(timezone.utc):
                near.append((start, fixture))
            else:
                counts["at_or_after_start"] += 1
        counts["window_eligible"] = len(near)
        dated = sorted(near, key=lambda pair: pair[0])
    for start, fixture in dated[:limit]:
        match_id = fixture["match_page"].split("/", 1)[0]
        observed = datetime.now(timezone.utc)
        if observed >= start:
            counts["at_or_after_start"] += 1
            continue
        counts["prestart_attempts"] += 1
        try:
            response = session.get(f"{base_url}/v2/match/details", params={"match_id": match_id}, timeout=30)
            response.raise_for_status()
            detail = segment(response.json())
            if detail is None:
                raise ValueError("missing detail segment")
        except (requests.RequestException, ValueError, KeyError) as exc:
            counts["api_errors"] += 1
            lines.append(f"{match_id}: API error {type(exc).__name__}")
            continue
        received = datetime.now(timezone.utc)
        if received >= start:
            counts["at_or_after_start"] += 1
            continue
        if str(detail.get("status") or "").lower() == "final":
            # Feed time may be stale after a reschedule; a completed detail
            # cannot prove its veto was published before play.
            counts["stale_final_detail"] += 1
            lines.append(f"{match_id}: detail already final despite future fixture start={start.isoformat()}")
            continue
        if str(detail.get("status") or "").strip().lower() in {"live", "in progress", "in-progress", "ongoing"}:
            counts["stale_started_detail"] += 1
            lines.append(f"{match_id}: detail already {detail.get('status')!r} despite future fixture start={start.isoformat()}")
            continue
        if any(isinstance(m, dict) and isinstance(m.get("score"), dict)
               and any(str(m["score"].get(side) or "").strip() not in {"", "0"}
                       for side in ("team1", "team2"))
               for m in detail.get("maps") or []):
            counts["stale_played_map"] += 1
            lines.append(f"{match_id}: detail has a played map despite future fixture start={start.isoformat()}")
            continue
        veto = str(detail.get("map_vetos") or "").strip()
        parsed = parse_full_veto(veto)
        counts["successful_prestart"] += 1
        counts["full_prestart_veto"] += parsed is not None
        counts["empty_prestart_veto"] += not bool(veto)
        counts["partial_or_other_prestart_veto"] += bool(veto) and parsed is None
        lines.append(f"{match_id}: observed={received.isoformat()} start={start.isoformat()} "
                     f"status={detail.get('status')!r} full_veto={parsed is not None} "
                     f"map_names={[m.get('map_name') for m in detail.get('maps') or []]}")
    return counts, lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="read-only API probe, no raw save")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--within-hours", type=float, help="only probe fixtures starting within this many hours")
    args = parser.parse_args()
    if args.within_hours is not None and args.within_hours <= 0:
        parser.error("--within-hours must be positive")
    print("archived", dict(archived_audit(RAW_VLRGG_DIR)))
    if args.live:
        counts, lines = live_audit(SETTINGS["vlrgg"]["base_url"], max(args.limit, 0), args.within_hours)
        for line in lines:
            print(line)
        print("live", dict(counts))
        if counts["feed_api_errors"]:
            raise SystemExit(1)
    print("Historical full vetos on final pages do not establish pre-start availability.")


if __name__ == "__main__":
    main()
