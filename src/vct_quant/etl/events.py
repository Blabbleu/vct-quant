"""Official VCT competition scope.

Tier 1 is the primary VCT circuit. Tier 2 is the path-to-pro circuit: 2023-26
Challengers/VCL and Ascension, and from 2027 the open stages (Open Qualifiers,
Open Playoffs, Wild Card and Last Chance Qualifiers) that feed Kickoff and the
Cups. Tier 3 is Game Changers, modelled as a separate rating pool. Everything
else is out of model scope.
"""
from __future__ import annotations

import re

# VCT 2027 open stages. Open teams enter here, so keeping them out of Tier 1
# stops amateur rosters flooding the Tier-1 pool, as they did in 2021-22.
OPEN_STAGE = re.compile(r"\bopen (?:qualifier|playoff)s?\b|\bwild ?card\b")
# Before 2027 an LCQ was partner teams fighting for Champions (Tier 1); from
# 2027 it is the South Asia / Oceania path into the Pacific Kickoff and Cups.
LAST_CHANCE = re.compile(r"\blast chance\b|\blcq\b")
OPEN_ERA = 2027
# Candidate for November 2026 fixtures labeled VCT 2027. Keep disabled until
# explicit approval: moving an LCQ from Tier 1 to Tier 2 affects Elo history.
OPEN_ERA_TITLE_SEASON = False

VCT_BRANDED = re.compile(
    r"^(?:vct|valorant champions tour|champions tour|valorant champions|valorant masters)\b"
)


def _season(title: str, year: int | None, title_season_override: bool) -> int | None:
    found = re.search(r"\b(20\d\d)\b", title)
    if title_season_override and found:
        return int(found.group(1))
    if year is not None:
        return year
    return int(found.group(1)) if found else None


def competition_tier(name: str, year: int | None = None, *,
                     title_season_override: bool | None = None) -> int | None:
    """Return 1/2 for official VCT events, 3 for Game Changers, otherwise None.

    `year` matters because regional Challengers were the primary VCT circuit in
    2021-2022, before the separate Challengers League system launched in 2023,
    and because Last Chance Qualifiers change meaning in 2027. Without `year`
    the season is read from the title when it contains one. The keyword override
    is for read-only candidate audits; omitted uses the disabled-by-default flag.
    """
    if title_season_override is None:
        title_season_override = OPEN_ERA_TITLE_SEASON
    title = str(name).strip().lower()
    if not title or "off//season" in title:
        return None
    # Its own circuit and its own rating pool: GC teams never meet Tier-1 teams.
    if "game changers" in title:
        return 3

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
        # Some official pages use the long prefix instead of "VCT YYYY:".
        if (title_season_override and (_season(title, year, title_season_override) or 0) >= OPEN_ERA
                and (OPEN_STAGE.search(title) or LAST_CHANCE.search(title))):
            return 2
        # In 2021-2022, events named "... Stage N: Challengers" were the
        # primary regional VCT circuit, not the modern Tier-2 league.
        return 2 if "challengers" in title and year is not None and year >= 2023 else 1

    if (
        re.match(r"^vct \d{4}:", title)
        or title.startswith("valorant champions tour ")
        or re.match(r"^valorant champions \d{4}\b", title)
        or title.startswith("valorant masters ")
    ):
        season = _season(title, year, title_season_override)
        if OPEN_STAGE.search(title):
            return 2
        if LAST_CHANCE.search(title) and season is not None and season >= OPEN_ERA:
            return 2
        return 1

    return None


# The upcoming feed carries no series format, so it is inferred from the
# stage label. Measured on played 2023-26 results (docs/series-format.md):
# Tier-1 lower/middle/grand finals went the Bo5 distance 103 of 104 times,
# every other Tier-1 stage label 1,741 of 1,751 times ended at two maps.
# Game Changers main events play Bo5 lower and grand finals (20/20); its
# small cups and splits do not, so only a grand final keeps the legacy Bo5.
_BO5_STAGE = re.compile(r"\b(?:lower|middle|grand) final\b(?!\s*quals?\b)")
_GRAND_FINAL = re.compile(r"\bgrand final\b(?!\s*quals?\b)")
_GC_MAIN_EVENT = re.compile(
    r"^game changers 20\d\d: (?:(?:china|pacific|brazil finals|latam main event)$|championship\b)"
)


def series_best_of(event: str | None, series: str | None) -> int:
    """Best-of for a fixture from its event title and stage label (3 or 5)."""
    stage = str(series or "").strip().lower()
    title = str(event or "").strip().lower()
    if not _BO5_STAGE.search(stage):
        return 3
    if "game changers" in title and not _GC_MAIN_EVENT.match(title):
        return 5 if _GRAND_FINAL.search(stage) else 3
    return 5


def untiered_vct_titles(titles) -> list[str]:
    """VCT-branded event titles that `competition_tier` drops.

    A renamed 2027 stage (Cups have no vlr.gg naming yet) would otherwise
    vanish from the data without a trace; `vct update` prints these.
    """
    return sorted({
        t for t in titles
        if competition_tier(t) is None
        and VCT_BRANDED.match(str(t).strip().lower())
        and "off//season" not in str(t).lower()
    })
