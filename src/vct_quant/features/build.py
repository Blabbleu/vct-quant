"""Assemble the point-in-time feature matrix for modeling.

Output contract: one row per (match, team_a, team_b) with columns
  * features computed only from data available before the match
  * label: 1 if team_a won the series, else 0
written to data/processed/features.parquet.
"""
from __future__ import annotations

# TODO: read canonical tables from DuckDB, join Elo (features.ratings) and
#       rolling form (features.rolling), write parquet to PROCESSED_DIR.
