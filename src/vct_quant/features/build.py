"""Assemble the point-in-time feature matrix for modeling.

Output contract: one row per (match, team_a, team_b) with columns
  * features computed only from data available before the match
  * label: 1 if team_a won the series, else 0
written to data/processed/features.parquet.
"""
from __future__ import annotations

import duckdb
import pandas as pd

from .. import db

# The corpus has no date column anywhere, so ascending vlr.gg match_id is the
# chronological key (verified: per-year ID ranges are strictly increasing with
# zero overlap, 2021-2026). Everything downstream orders by this and nothing
# relies on incidental row order.
ORDER_KEY = "match_id"

_MATCH_SEQUENCE_SQL = """
SELECT
    m.match_id,
    -- team_id is NULL for ~2.8% of rows (a name mapping to two vlr.gg IDs).
    -- Falling back to the name keeps those teams distinct; keying on the raw
    -- NULL would merge every unresolved team into one.
    coalesce(CAST(a.team_id AS VARCHAR), 'name:' || lower(trim(a.team_name))) AS team_a,
    coalesce(CAST(b.team_id AS VARCHAR), 'name:' || lower(trim(b.team_name))) AS team_b,
    a.team_name AS team_a_name,
    b.team_name AS team_b_name,
    -- Bo2 draws are real (75 matches): is_winner is NULL on both sides, which
    -- falls through to 0.5 rather than being scored as a loss for team A.
    CASE WHEN a.is_winner THEN 1.0 WHEN b.is_winner THEN 0.0 ELSE 0.5 END AS score_a
FROM match m
JOIN match_team a ON a.match_id = m.match_id AND a.team_number = 1
JOIN match_team b ON b.match_id = m.match_id AND b.team_number = 2
ORDER BY m.match_id
"""


def match_sequence(con: duckdb.DuckDBPyConnection | None = None) -> pd.DataFrame:
    """Every match in chronological order: match_id, team_a, team_b, score_a.

    This is the input contract for `features.ratings.compute_elo`, which
    requires chronological order, and its match_id column is the ordering key
    for `eval.backtest.walk_forward_splits`.
    """
    owned = con is None
    con = con or db.connect(read_only=True)
    try:
        return con.execute(_MATCH_SEQUENCE_SQL).df()
    finally:
        if owned:
            con.close()


# TODO: join rolling form (features.rolling) onto the Elo columns and write
#       parquet to PROCESSED_DIR.
