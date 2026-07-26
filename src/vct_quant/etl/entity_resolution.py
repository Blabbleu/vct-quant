"""Resolve teams/players across sources (Kaggle names vs vlr.gg IDs vs Riot).

This is where most real data work in this project lives: orgs rebrand, players
change handles, and the Kaggle scrape keys on names while vlrggapi exposes
numeric vlr.gg IDs. The Kaggle dataset ships *_ids mapping files that link
names to vlr.gg URLs — parse the numeric ID out of those URLs to join the two
worlds before resorting to fuzzy name matching.
"""
from __future__ import annotations

import re


def normalize_name(name: str) -> str:
    """Canonical key for name-based joins: lowercased, whitespace collapsed."""
    return re.sub(r"\s+", " ", name).strip().lower()


def vlr_id_from_url(url: str) -> int | None:
    """Extract the numeric vlr.gg entity ID from a URL like
    https://www.vlr.gg/team/2593/fnatic or /player/9/tenz."""
    m = re.search(r"vlr\.gg/(?:team|player|event)/(\d+)", url)
    if m is None:
        m = re.search(r"^/?(?:team|player|event)/(\d+)", url)
    return int(m.group(1)) if m else None
