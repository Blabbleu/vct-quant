"""Read-only audit: can historical map records support a pre-series veto model?

    python scripts/map_veto_feasibility.py

The canonical map table records *played* maps, not an independently timestamped
pre-match veto. In a Bo3 2-0 the decider is unplayed, so even complete map
results cannot reconstruct the full pre-series pool. Counts are diagnostic,
not a model benchmark or permission to condition on post-match information.
"""
from __future__ import annotations

import pandas as pd

from vct_quant import db

ROWS_SQL = """
SELECT m.match_id, year(m.completed_at) AS year, m.best_of,
       a.series_score AS maps_a, b.series_score AS maps_b,
       coalesce(detail.map_count, 0) AS map_count,
       coalesce(detail.scored_maps, 0) AS scored_maps,
       coalesce(detail.named_maps, 0) AS named_maps,
       coalesce(detail.picks, 0) AS picks
FROM match m
JOIN event e ON e.event_id = m.event_id AND e.tier = 1
JOIN match_team a ON a.match_id = m.match_id AND a.team_number = 1
JOIN match_team b ON b.match_id = m.match_id AND b.team_number = 2
LEFT JOIN (
    SELECT mm.match_id, count(*) AS map_count,
           count(*) FILTER (WHERE sa.total_rounds IS NOT NULL
                            AND sb.total_rounds IS NOT NULL
                            AND sa.total_rounds != sb.total_rounds) AS scored_maps,
           count(DISTINCT lower(trim(mm.map_name))) AS named_maps,
           count(*) FILTER (WHERE mm.picked_by_team_id IS NOT NULL OR
                             (mm.picked_by_raw IS NOT NULL AND trim(mm.picked_by_raw) != '')) AS picks
    FROM match_map mm
    LEFT JOIN match_map_team_score sa
      ON sa.match_map_id = mm.match_map_id AND sa.team_number = 1
    LEFT JOIN match_map_team_score sb
      ON sb.match_map_id = mm.match_map_id AND sb.team_number = 2
    GROUP BY mm.match_id
) detail ON detail.match_id = m.match_id
WHERE m.completed_at >= '2023-01-01' AND m.completed_at < '2027-01-01'
ORDER BY m.match_id
"""


def summarize(rows: pd.DataFrame) -> pd.DataFrame:
    """One row/year: eligible Bo3/5, complete played maps, full pool, pick data.

    A full pool count is only a structural *upper bound*: these historical map
    names were recorded after play, with no pre-match observation timestamp.
    """
    eligible = rows.loc[rows.best_of.isin((3, 5))].copy()
    columns = ["year", "series", "played_maps_covered", "full_pool_observed",
               "series_with_picks", "early_finishes", "early_with_full_pool"]
    if eligible.empty:
        return pd.DataFrame(columns=columns)
    total = eligible.maps_a + eligible.maps_b
    valid = total.notna() & total.gt(0) & eligible.map_count.eq(total)
    valid &= eligible.scored_maps.eq(total) & eligible.named_maps.eq(total)
    eligible["played_maps_covered"] = valid
    eligible["full_pool_observed"] = valid & total.eq(eligible.best_of)
    eligible["series_with_picks"] = eligible.picks.gt(0)
    eligible["early_finishes"] = total.gt(0) & total.lt(eligible.best_of)
    eligible["early_with_full_pool"] = eligible.early_finishes & eligible.full_pool_observed
    return eligible.groupby("year", sort=True, as_index=False).agg(
        series=("match_id", "size"),
        played_maps_covered=("played_maps_covered", "sum"),
        full_pool_observed=("full_pool_observed", "sum"),
        series_with_picks=("series_with_picks", "sum"),
        early_finishes=("early_finishes", "sum"),
        early_with_full_pool=("early_with_full_pool", "sum"),
    )[columns]


def main() -> None:
    with db.connect(read_only=True) as con:
        rows = con.execute(ROWS_SQL).df()
    summary = summarize(rows)
    print(summary.to_string(index=False))
    if not summary.empty:
        print("TOTAL", summary.drop(columns="year").sum().to_dict())
    print("Full pool = structural upper bound from post-match played-map rows, "
          "NOT a timestamped pre-match veto. Early finishes omit unplayed maps.")


if __name__ == "__main__":
    main()
