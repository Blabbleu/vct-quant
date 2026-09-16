"""Glicko ratings: Elo plus an uncertainty (RD, "rating deviation") per team.

Elo gives a team one number and trusts it equally whether the team has played
300 matches or 1. Glicko carries RD alongside the rating:

* A new team starts at RD 350 (very unsure). Each match shrinks RD.
* Sitting out time grows RD again, so a returning team re-learns quickly.
* High RD means big rating moves (like a large K), low RD means small ones.
  There is no K to tune -- RD *is* the per-team learning rate.
* Predictions between uncertain teams are pulled toward 50%, which is exactly
  what log loss rewards when the model doesn't really know.

Reference: Mark Glickman, "The Glicko system" (glicko.net/glicko/glicko.pdf).
This is Glicko-1 with each match as its own rating period.

Point-in-time safe like `ratings.compute_elo`: each row carries the ratings
*before* its match was applied.
"""
from __future__ import annotations

from itertools import repeat
from math import isnan, log, pi, sqrt
from typing import Hashable, Iterable

BASE = 1500.0
MAX_RD = 350.0
Q = log(10) / 400  # converts the 400-point Elo scale to natural-log units


def g(rd: float) -> float:
    """Discount for opponent uncertainty: 1.0 at RD 0, shrinking as RD grows."""
    return 1 / sqrt(1 + 3 * Q**2 * rd**2 / pi**2)


def win_probability(r_a: float, rd_a: float, r_b: float, rd_b: float) -> float:
    """P(A beats B) when both ratings are uncertain.

    Same shape as Elo's expected_score, but the rating gap is shrunk by g() of
    the two teams' *combined* uncertainty:

        rd = sqrt(rd_a**2 + rd_b**2)
        p  = 1 / (1 + 10 ** (-g(rd) * (r_a - r_b) / 400))

    Check yourself: equal ratings -> 0.5 whatever the RDs; a 100-point edge
    gives ~0.64 at RD 50 but only ~0.58 at RD 350.
    """
    rd = sqrt(rd_a**2 + rd_b**2)
    p = 1 / (1 + 10 ** (-g(rd) * (r_a - r_b) / 400))
    return p


def update(
    r: float, rd: float, r_opp: float, rd_opp: float, score: float
) -> tuple[float, float]:
    """One team's post-match (rating, RD) after one match vs one opponent.

    score is this team's share of maps won (1.0 sweep, 0.0 swept, 2/3 for 2-1).
    All four steps use PRE-match values.

    Why it works: `1/rd**2` is how much you already knew, `1/d2` is how much this
    match tells you. They add up (precision), so RD always shrinks after a match,
    and the rating step Q/denom is large exactly when prior knowledge was small.
    `score - e` is the same surprise term as Elo.

    Note `e` uses only the OPPONENT's RD, unlike win_probability.
    """
    e = 1 / (1 + 10 ** (-g(rd_opp) * (r - r_opp) / 400))  # expected score
    d2 = 1 / (Q**2 * g(rd_opp) ** 2 * e * (1 - e))  # info in this match
    denom = 1 / rd**2 + 1 / d2  # combined precision
    return r + (Q / denom) * g(rd_opp) * (score - e), sqrt(1 / denom)


def compute_glicko(
    matches: Iterable[tuple[Hashable, Hashable, Hashable, Hashable, float]],
    c: float = 0.0,
    season_c: float = 0.0,
    initial_rd: float = MAX_RD,
    churn: Iterable[tuple[float, float]] | None = None,
    roster_c: float = 0.0,
) -> tuple[list[dict], dict]:
    """Run Glicko over (match_id, year, team_a, team_b, score_a), chronological.

    Before each match a team's RD grows: by `c` per match played (ratings go
    stale as rosters and metas drift), plus `season_c` once when the team's
    first match of a new year arrives (offseason roster turnover). The corpus
    has no reliable dates, so time is counted in matches and years, not days.

    `churn` optionally aligns (churn_a, churn_b) with `matches`: the share of
    each lineup that is new since that team's previous match (known before the
    match starts). RD then also grows by `roster_c * churn` -- the hypothesis
    being that `season_c` only helped as a stand-in for roster turnover. NaN
    churn (no previous lineup to compare) counts as no change.

    Returns (rows, final_state) with state[team] = (rating, rd).
    """
    state: dict = {}
    last_year: dict = {}
    rows: list[dict] = []
    churns = repeat((0.0, 0.0)) if churn is None else iter(churn)
    for (match_id, year, team_a, team_b, score_a), sides in zip(matches, churns):
        pre = []
        for team, team_churn in zip((team_a, team_b), sides):
            team_churn = 0.0 if isnan(team_churn) else team_churn
            r, rd = state.get(team, (BASE, initial_rd))
            rd2 = rd**2 + c**2
            if team in last_year and year != last_year[team]:
                rd2 += season_c**2
            rd2 += (roster_c * team_churn) ** 2
            last_year[team] = year
            pre.append((r, min(sqrt(rd2), MAX_RD)))
        (ra, rda), (rb, rdb) = pre
        rows.append({
            "match_id": match_id,
            "team_a": team_a,
            "team_b": team_b,
            "glicko_a_pre": ra,
            "glicko_b_pre": rb,
            "rd_a_pre": rda,
            "rd_b_pre": rdb,
            "p_a_win": win_probability(ra, rda, rb, rdb),
        })
        state[team_a] = update(ra, rda, rb, rdb, score_a)
        state[team_b] = update(rb, rdb, ra, rda, 1.0 - score_a)
    return rows, state
