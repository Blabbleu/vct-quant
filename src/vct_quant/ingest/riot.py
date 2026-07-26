"""Riot official API adapter (placeholder).

Reality check before building on this:
  * VCT pro matches are played on the esports tournament realm and are NOT
    exposed by the public Riot API — pro in-game data comes from vlr.gg
    (live via vlrgg.py, historical via the Kaggle dataset).
  * The VAL-MATCH-V1 endpoints require an approved production key tied to a
    registered product; personal development keys do not include them.

What this adapter is for, if/when a key is granted: pro players' ranked-queue
matches as a "current form" signal (resolve their Riot IDs via account-v1,
then pull recent competitive matches). Keep it a supplementary feature — the
ranked distribution differs from pro play.
"""
from __future__ import annotations

from ..config import RIOT_API_KEY


def fetch_player_ranked_matches(game_name: str, tag_line: str) -> dict:
    if RIOT_API_KEY is None:
        raise RuntimeError(
            "RIOT_API_KEY is not set (.env). See module docstring for why this "
            "adapter is optional."
        )
    raise NotImplementedError(
        "Implement once a Riot production key with VAL-MATCH-V1 access exists: "
        "account-v1 riot-id lookup -> val/match/v1/matchlists/by-puuid."
    )
