"""Polymarket prices for Valorant matches (public Gamma API, no key).

Read-only: this fetches market prices to benchmark the model against. Each
fetch is written verbatim to data/raw/polymarket/ before parsing, like vlrgg.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import requests

from ..config import RAW_POLYMARKET_DIR

GAMMA_URL = "https://gamma-api.polymarket.com/events"
PAGE = 100


def fetch_valorant_events(save: bool = True) -> list[dict]:
    """Every open Valorant event, all pages."""
    events: list[dict] = []
    while True:
        resp = requests.get(GAMMA_URL, params={
            "tag_slug": "valorant", "closed": "false", "limit": PAGE, "offset": len(events),
        }, timeout=30)
        resp.raise_for_status()
        page = resp.json()
        events.extend(page)
        if len(page) < PAGE:
            break
    if save:
        RAW_POLYMARKET_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (RAW_POLYMARKET_DIR / f"valorant_events_{ts}.json").write_text(
            json.dumps(events, indent=2), encoding="utf-8"
        )
    return events
