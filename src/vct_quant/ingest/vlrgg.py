"""Client for the unofficial vlr.gg API (https://vlrggapi.vercel.app).

Every fetch is written verbatim to data/raw/vlrgg/ before any parsing, so
ingestion stays replayable when the unofficial API changes shape.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from ..config import RAW_VLRGG_DIR, SETTINGS

BASE_URL: str = SETTINGS["vlrgg"]["base_url"]
REQUEST_DELAY_S: float = SETTINGS["vlrgg"]["request_delay_seconds"]

_session = requests.Session()


def _get(path: str, params: dict | None = None) -> dict:
    for attempt in range(4):
        resp = _session.get(f"{BASE_URL}{path}", params=params, timeout=30)
        if resp.status_code != 429 or attempt == 3:
            break
        time.sleep(float(resp.headers.get("Retry-After", 60)) + 1)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY_S)  # be polite: unofficial API on shared hosting
    return resp.json()


def save_raw(payload: dict, name: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RAW_VLRGG_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_VLRGG_DIR / f"{name}_{ts}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _fetch_segmented(path: str, params: dict, name: str, save: bool) -> dict:
    """Archive a response, then fail closed on HTTP-200 error/malformed feeds.

    The matchday shell preflight can succeed and a later ingestion request fail;
    an error envelope must never be interpreted as zero events or fixtures.
    """
    payload = _get(path, params)
    if save:
        save_raw(payload, name)  # preserve the failed response for diagnosis
    data = payload.get("data") if isinstance(payload, dict) else None
    rows = data.get("segments") if isinstance(data, dict) else None
    if (not isinstance(payload, dict) or payload.get("status") != "success"
            or not isinstance(data, dict) or data.get("status") != 200
            or not isinstance(rows, list)
            or not all(isinstance(row, dict) for row in rows)):
        raise ValueError(f"invalid {name} feed from vlrggapi")
    return payload


def fetch_match_results(save: bool = True) -> dict:
    return _fetch_segmented("/v2/match", {"q": "results"}, "match_results", save)


def fetch_upcoming_matches(save: bool = True) -> dict:
    return _fetch_segmented("/v2/match", {"q": "upcoming"}, "match_upcoming", save)


def _valid_detail_shape(detail: dict) -> bool:
    """Reject nested values that the replay loader cannot safely traverse."""
    if not all(isinstance(team, dict) for team in detail["teams"]):
        return False
    for game_map in detail["maps"]:
        if not isinstance(game_map, dict):
            return False
        for key in ("score", "score_t", "score_ct", "score_ot", "players"):
            if key in game_map and not isinstance(game_map[key], dict):
                return False
        players = game_map.get("players", {})
        for side in ("team1", "team2"):
            if side in players and (not isinstance(players[side], list)
                                    or not all(isinstance(p, dict) for p in players[side])):
                return False
    return True


def detail_segments(payload: dict, match_id: int | str) -> list[dict]:
    """Validate a detail envelope and its identity before using it for IDs/maps.

    Older raw snapshots and small test fixtures can carry a flat data object;
    the current v2 API wraps it in segments. Neither shape may be an error
    envelope or a detail for a different match.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if (not isinstance(data, dict)
            or payload.get("status", "success") != "success"
            or data.get("status", 200) != 200):
        raise ValueError(f"invalid match_details_{match_id} feed")
    segments = data.get("segments", [data])
    if (not isinstance(segments, list) or len(segments) != 1
            or not all(isinstance(d, dict)
                       and str(d.get("match_id")) == str(match_id)
                       and isinstance(d.get("teams"), list)
                       and isinstance(d.get("maps"), list)
                       and _valid_detail_shape(d)
                       for d in segments)):
        raise ValueError(f"invalid match_details_{match_id} feed")
    return segments


def fetch_match_details(match_id: int | str, save: bool = True) -> dict:
    data = _get("/v2/match/details", {"match_id": match_id})
    if save:
        save_raw(data, f"match_details_{match_id}")
    detail_segments(data, match_id)
    return data


def fetch_team(team_id: int | str, save: bool = True) -> dict:
    data = _get("/v2/team", {"id": team_id})
    if save:
        save_raw(data, f"team_{team_id}")
    return data


def fetch_events(page: int = 1, save: bool = True) -> dict:
    """One page of the event listing (~50-72 events, newest first)."""
    return _fetch_segmented("/v2/events", {"page": page}, f"events_page{page:03d}", save)


def fetch_event_matches(event_id: int | str, save: bool = True) -> dict:
    """Every match of one event, with a real `date` per match.

    This is the backfill workhorse: the Kaggle corpus carries no dates at all,
    and one call here returns date, status, both team names, scores and winner
    for a whole event — so a season costs a few dozen requests rather than one
    per match.
    """
    return _fetch_segmented("/v2/events/matches", {"event_id": event_id},
                            f"event_matches_{event_id}", save)


def fetch_rankings(region: str, save: bool = True) -> dict:
    data = _get("/v2/rankings", {"region": region})
    if save:
        save_raw(data, f"rankings_{region}")
    return data
