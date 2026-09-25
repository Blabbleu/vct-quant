"""Read-only audit of already-loaded completed/TBD matches before rebuild.

    python scripts/placeholder_audit.py

A previous additive event loader admitted completed placeholders. Current replay
rejects them, but reloading does not delete existing database rows; a fresh DB
would have a different match set. This script never repairs or writes data.
"""
from __future__ import annotations

import duckdb
import pandas as pd

from vct_quant import db


_SQL = """
SELECT m.match_id, e.tier,
       a.team_name AS team_a, b.team_name AS team_b,
       a.series_score AS score_a, b.series_score AS score_b,
       (a.series_score IS NULL OR b.series_score IS NULL) AS missing_score
FROM "match" m
JOIN event e ON e.event_id = m.event_id
JOIN match_team a ON a.match_id = m.match_id AND a.team_number = 1
JOIN match_team b ON b.match_id = m.match_id AND b.team_number = 2
WHERE lower(m.status) = 'completed'
  AND (lower(trim(a.team_name)) = 'tbd' OR lower(trim(b.team_name)) = 'tbd')
ORDER BY m.match_id
"""


def placeholder_rows(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """One row per completed match with a TBD side; don't flag valid forfeits."""
    return con.execute(_SQL).df()


def main() -> None:
    with db.connect(read_only=True) as con:
        rows = placeholder_rows(con)
    print(f"Existing completed/TBD matches: {len(rows)} (additive loads retain these)")
    for tier, group in rows.groupby('tier', dropna=False):
        print(f"  tier {tier}: {len(group)}; missing a side's score: {int(group.missing_score.sum())}")
        if tier == 1:
            print('  Tier-1 IDs:', ' '.join(map(str, group.match_id)))
    print('Do not delete DB rows or change primary Elo without approval.')


if __name__ == '__main__':
    main()
