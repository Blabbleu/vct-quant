"""Read-only audit of full-veto availability in raw details and current fixtures.

    python scripts/veto_source_audit.py
    python scripts/veto_source_audit.py --live --limit 8

Never writes to data/raw. A historical final-page veto is NOT pre-start evidence.
The optional live probe does not persist observations and cannot be used for
backtesting; a timestamped collector would need separate live-side approval.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
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


def live_audit(base_url: str, limit: int) -> tuple[Counter, list[str]]:
    """Probe the first N fixtures; count API errors separately from missing veto."""
    counts: Counter = Counter()
    lines: list[str] = []
    session = requests.Session()
    response = session.get(f"{base_url}/v2/match", params={"q": "upcoming"}, timeout=30)
    response.raise_for_status()
    fixtures = response.json()["data"]["segments"][:limit]
    for fixture in fixtures:
        match_id = fixture["match_page"].split("/", 1)[0]
        start = datetime.strptime(fixture["unix_timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
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
    args = parser.parse_args()
    print("archived", dict(archived_audit(RAW_VLRGG_DIR)))
    if args.live:
        counts, lines = live_audit(SETTINGS["vlrgg"]["base_url"], max(args.limit, 0))
        for line in lines:
            print(line)
        print("live", dict(counts))
    print("Historical full vetos on final pages do not establish pre-start availability.")


if __name__ == "__main__":
    main()
