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
    """Keep every response, including two fetches for a source in one second.

    Exclusive creation avoids overwriting an earlier good snapshot with an
    HTTP-200 error. Numbered collisions sort after the unsuffixed snapshot,
    preserving fetch order for the replay loader's latest-valid selection.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RAW_VLRGG_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=2)
    for number in range(10000):
        suffix = f"_{number:04d}" if number else ""
        path = RAW_VLRGG_DIR / f"{name}_{ts}{suffix}.json"
        try:
            with path.open("x", encoding="utf-8") as output:
                output.write(body)
            return path
        except FileExistsError:
            continue
    raise FileExistsError(f"raw snapshot names exhausted for {name}_{ts}")


def _positive_unique_ids(rows: list[dict], field: str) -> bool:
    """Do not replay zero IDs or two versions of one entity in one response."""
    ids = []
    for row in rows:
        value = str(row.get(field, ""))
        if not value.isascii() or not value.isdecimal() or int(value) <= 0:
            return False
        ids.append(int(value))
    return len(ids) == len(set(ids))


def valid_feed_rows(rows: list[dict], name: str) -> bool:
    """Check fields consumed by the event replay and upcoming normalizer.

    Fail a whole response instead of letting a truncated row masquerade as a
    valid empty/partial harvest. Keep optional values and unknown fields intact.
    """
    if name.startswith("events_page"):
        required = {"event_id", "title", "status", "region", "dates", "prize", "thumb", "url_path"}
        return (_positive_unique_ids(rows, "event_id") and all(
            required <= row.keys() and isinstance(row["title"], str) for row in rows))
    if name.startswith("event_matches_"):
        required = {"match_id", "date", "status", "event_series", "team1", "team2"}
        return _positive_unique_ids(rows, "match_id") and all(
            required <= row.keys() and isinstance(row["status"], str)
            and (row["status"].lower() != "completed" or all(
                isinstance(row[side], dict) and {"name", "score"} <= row[side].keys()
                for side in ("team1", "team2")
            )) for row in rows
        )
    if name == "match_upcoming":
        required = {"match_event", "unix_timestamp", "match_page", "match_series",
                    "team1", "team2", "time_until_match"}
        match_ids = []
        for row in rows:
            if not required <= row.keys() or not all(
                isinstance(row[field], str)
                for field in ("match_event", "unix_timestamp", "match_series", "team1", "team2")
            ):
                return False
            page = row["match_page"]
            if not isinstance(page, str):
                return False
            prefix = page.split("/", 1)[0]
            if not prefix.isascii() or not prefix.isdecimal() or int(prefix) <= 0:
                return False
            match_ids.append(int(prefix))
        # Duplicate IDs (including changed slugs) would log two forecasts for
        # one fixture, and malformed IDs otherwise disappear during normalization.
        return len(match_ids) == len(set(match_ids))
    return True  # Results are archived but not used by the event replay.


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
            or not all(isinstance(row, dict) for row in rows)
            or not valid_feed_rows(rows, name)):
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
