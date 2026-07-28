"""Official VCT competition scope.

Tier 1 is the primary VCT circuit. Tier 2 is the post-2022 path-to-pro circuit
(Challengers/VCL and Ascension). Everything else is out of model scope.
"""
from __future__ import annotations

import re


def competition_tier(name: str, year: int | None = None) -> int | None:
    """Return 1/2 for official VCT events, otherwise None.

    `year` matters because regional Challengers were the primary VCT circuit in
    2021-2022, before the separate Challengers League system launched in 2023.
    """
    title = str(name).strip().lower()
    if not title or "game changers" in title or "off//season" in title:
        return None

    if "ascension" in title and (
        title.startswith(("vct ", "champions tour ")) or "challengers" in title
    ):
        return 2

    modern_challengers = (
        "challengers league" in title
        or re.match(r"^challengers \d{4}\b", title)
        or re.match(r"^vcl(?:\s|$)", title)
    )
    if modern_challengers:
        return 1 if year is not None and year <= 2022 else 2

    if title.startswith("champions tour "):
        # In 2021-2022, events named "... Stage N: Challengers" were the
        # primary regional VCT circuit, not the modern Tier-2 league.
        return 2 if "challengers" in title and year is not None and year >= 2023 else 1

    if (
        re.match(r"^vct \d{4}:", title)
        or title.startswith("valorant champions tour ")
        or re.match(r"^valorant champions \d{4}\b", title)
        or title.startswith("valorant masters ")
    ):
        return 1

    return None
