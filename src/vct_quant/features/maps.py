"""Opponent-adjusted map ratings for forecasts with a known veto."""
from __future__ import annotations

from math import log10

import duckdb
import pandas as pd

from .. import db
from .ratings import DEFAULT_BASE, expected_score, update

# Validation-selected conservative adjustment; map Elo did not beat global Elo
# significantly, so this is used only when callers explicitly provide maps.
MAP_K = 8.0
MAP_PRIOR = 160.0

_MAP_SEQUENCE_SQL = """
SELECT mm.match_id, mm.map_number, lower(trim(mm.map_name)) AS map_name,
       coalesce(CAST(a.team_id AS VARCHAR),
                'name:' || lower(trim(a.team_name))) AS team_a,
       coalesce(CAST(b.team_id AS VARCHAR),
                'name:' || lower(trim(b.team_name))) AS team_b,
       CASE WHEN sa.total_rounds > sb.total_rounds THEN 1.0 ELSE 0.0 END AS score_a
FROM match_map mm
JOIN match m USING (match_id)
JOIN event e USING (event_id)
JOIN match_team a ON a.match_id = m.match_id AND a.team_number = 1
JOIN match_team b ON b.match_id = m.match_id AND b.team_number = 2
JOIN match_map_team_score sa
  ON sa.match_map_id = mm.match_map_id AND sa.team_number = 1
JOIN match_map_team_score sb
  ON sb.match_map_id = mm.match_map_id AND sb.team_number = 2
WHERE e.tier = 1 AND sa.total_rounds != sb.total_rounds
ORDER BY mm.match_id, mm.map_number
"""


def map_sequence(
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    owned = con is None
    con = con or db.connect(read_only=True)
    try:
        return con.execute(_MAP_SEQUENCE_SQL).df()
    finally:
        if owned:
            con.close()


def map_probabilities(
    history: pd.DataFrame,
    team_a: str,
    team_b: str,
    maps: list[str],
    p_global_map_a: float,
    k: float = MAP_K,
    prior: float = MAP_PRIOR,
) -> list[dict]:
    """Blend map Elo with the global map probability, shrinking sparse maps."""
    maps = [name.strip().lower() for name in maps]
    if len(set(maps)) != len(maps):
        raise ValueError("map picks must be unique")
    known = set(history.map_name)
    unknown = sorted(set(maps) - known)
    if unknown:
        raise ValueError(
            f"unknown map(s): {', '.join(unknown)}; known maps: {', '.join(sorted(known))}"
        )

    ratings: dict = {}
    counts: dict = {}
    for row in history.itertuples(index=False):
        key_a, key_b = (row.map_name, row.team_a), (row.map_name, row.team_b)
        rating_a = ratings.get(key_a, DEFAULT_BASE)
        rating_b = ratings.get(key_b, DEFAULT_BASE)
        ratings[key_a], ratings[key_b] = update(
            rating_a, rating_b, row.score_a, k
        )
        counts[key_a] = counts.get(key_a, 0) + 1
        counts[key_b] = counts.get(key_b, 0) + 1

    p_global_map_a = min(max(p_global_map_a, 1e-12), 1 - 1e-12)
    global_diff = 400 * log10(p_global_map_a / (1 - p_global_map_a))
    out = []
    for name in maps:
        key_a, key_b = (name, team_a), (name, team_b)
        rating_a = ratings.get(key_a, DEFAULT_BASE)
        rating_b = ratings.get(key_b, DEFAULT_BASE)
        evidence = min(counts.get(key_a, 0), counts.get(key_b, 0))
        weight = evidence / (evidence + prior)
        difference = (1 - weight) * global_diff + weight * (rating_a - rating_b)
        probability = expected_score(
            DEFAULT_BASE + difference / 2, DEFAULT_BASE - difference / 2
        )
        out.append({
            "map": name,
            "p_team_a_win": probability,
            "p_team_b_win": 1 - probability,
            "team_a_map_matches": counts.get(key_a, 0),
            "team_b_map_matches": counts.get(key_b, 0),
        })
    return out
