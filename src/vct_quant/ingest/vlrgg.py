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
    resp = _session.get(f"{BASE_URL}{path}", params=params, timeout=30)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY_S)  # be polite: unofficial API on shared hosting
    return resp.json()


def save_raw(payload: dict, name: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RAW_VLRGG_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_VLRGG_DIR / f"{name}_{ts}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def fetch_match_results(save: bool = True) -> dict:
    data = _get("/v2/match", {"q": "results"})
    if save:
        save_raw(data, "match_results")
    return data


def fetch_upcoming_matches(save: bool = True) -> dict:
    data = _get("/v2/match", {"q": "upcoming"})
    if save:
        save_raw(data, "match_upcoming")
    return data


def fetch_match_details(match_id: int | str, save: bool = True) -> dict:
    data = _get("/v2/match/details", {"match_id": match_id})
    if save:
        save_raw(data, f"match_details_{match_id}")
    return data


def fetch_team(team_id: int | str, save: bool = True) -> dict:
    data = _get("/v2/team", {"id": team_id})
    if save:
        save_raw(data, f"team_{team_id}")
    return data


def fetch_rankings(region: str, save: bool = True) -> dict:
    data = _get("/v2/rankings", {"region": region})
    if save:
        save_raw(data, f"rankings_{region}")
    return data
