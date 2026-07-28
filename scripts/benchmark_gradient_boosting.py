"""Untuned gradient-boosting benchmark on official Tier-1 matches.

    python scripts/benchmark_gradient_boosting.py

Train through 2024, test on 2025, and leave 2026 untouched.
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from vct_quant import db
from vct_quant.eval import metrics
from vct_quant.features.build import build_features

FEATURES = [
    "elo_diff",
    "churn_a",
    "churn_b",
    "n_prior_a",
    "n_prior_b",
    "player_form_diff",
    "player_form_coverage_a",
    "player_form_coverage_b",
    "player_form_t2_share_a",
    "player_form_t2_share_b",
]

PROMOTED_TEAMS_SQL = """
WITH ascension_teams AS (
    SELECT mt.team_id, max(m.completed_at) AS ascension_end
    FROM match_team mt
    JOIN match m USING (match_id)
    JOIN event e USING (event_id)
    WHERE mt.team_id IS NOT NULL
      AND m.completed_at IS NOT NULL
      AND e.tier = 2
      AND lower(e.name) LIKE '%ascension%'
    GROUP BY mt.team_id
)
SELECT DISTINCT a.team_id
FROM ascension_teams a
JOIN match_team mt USING (team_id)
JOIN match m USING (match_id)
JOIN event e USING (event_id)
WHERE e.tier = 1 AND m.completed_at > a.ascension_end
"""


def score(name: str, y: np.ndarray, p: np.ndarray) -> None:
    print(
        f"{name:<12} n={len(y):4d}  log loss={metrics.log_loss(y, p):.4f}"
        f"  brier={metrics.brier_score(y, p):.4f}"
    )


def main() -> None:
    df = build_features()
    train = df.tier.eq(1) & df.year.between(2022, 2024)
    test = df.tier.eq(1) & df.year.eq(2025)

    model = HistGradientBoostingClassifier(random_state=0)
    model.fit(df.loc[train, FEATURES], df.loc[train, "label"])

    y = df.loc[test, "label"].to_numpy()
    p = model.predict_proba(df.loc[test, FEATURES])[:, 1]
    elo = df.loc[test, "elo_p_a_win"].to_numpy()
    score("boosting", y, p)
    score("raw Elo", y, elo)

    with db.connect(read_only=True) as con:
        promoted = {str(row[0]) for row in con.execute(PROMOTED_TEAMS_SQL).fetchall()}
    promoted_match = (
        df.loc[test, "team_a"].isin(promoted) | df.loc[test, "team_b"].isin(promoted)
    ).to_numpy()
    if promoted_match.any():
        print("\n2025 matches involving an Ascension-promoted team:")
        score("boosting", y[promoted_match], p[promoted_match])
        score("raw Elo", y[promoted_match], elo[promoted_match])


if __name__ == "__main__":
    main()
