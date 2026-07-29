"""Assemble the point-in-time feature matrix for modeling.

Output contract: one row per (match, team_a, team_b) with columns
  * features computed only from data available before the match
  * label: 1 if team_a won the series, else 0
written to data/processed/features.parquet.
"""
from __future__ import annotations

from collections import defaultdict, deque

import duckdb
import pandas as pd

from .. import db
from ..config import PROCESSED_DIR
from .ratings import (
    DEFAULT_BASE,
    compute_elo,
    expected_score,
    implied_map_probability,
    map_score_probabilities,
    series_score_probabilities,
)

# Margin-aware Elo won the variant comparison at this K — see CLAUDE.md.
BEST_K = 48.0
# Tier-2 team-result Elo was tested at 0/.25/.5/.75/1 on Tier-1 matches from
# both 2024 and 2025. Every positive weight lost, including on promoted-team
# matches, because the mostly isolated rating pools are not directly comparable.
# Keep Tier-2 rows for roster/player-form features, but do not move shared Elo.
TIER_2_WEIGHT = 0.0

# The corpus has no date column anywhere, so ascending vlr.gg match_id is the
# chronological key (verified: per-year ID ranges are strictly increasing with
# zero overlap, 2021-2026). Everything downstream orders by this and nothing
# relies on incidental row order.
ORDER_KEY = "match_id"

_MATCH_SEQUENCE_SQL = """
SELECT
    m.match_id,
    e.tier,
    -- The Kaggle load parks the year in date_raw (there is no real date column
    -- anywhere in the corpus). TRY_CAST so a future vlrggapi load, which writes
    -- a real date string here, yields NULL rather than blowing up.
    TRY_CAST(m.date_raw AS INTEGER) AS year,
    -- team_id is NULL for ~2.8% of rows (a name mapping to two vlr.gg IDs).
    -- Falling back to the name keeps those teams distinct; keying on the raw
    -- NULL would merge every unresolved team into one.
    coalesce(CAST(a.team_id AS VARCHAR), 'name:' || lower(trim(a.team_name))) AS team_a,
    coalesce(CAST(b.team_id AS VARCHAR), 'name:' || lower(trim(b.team_name))) AS team_b,
    a.team_name AS team_a_name,
    b.team_name AS team_b_name,
    -- Bo2 draws are real (75 matches): is_winner is NULL on both sides, which
    -- falls through to 0.5 rather than being scored as a loss for team A.
    CASE WHEN a.is_winner THEN 1.0 WHEN b.is_winner THEN 0.0 ELSE 0.5 END AS score_a,
    -- Maps won by each side. score_a is the *label* (who won); these carry how
    -- convincingly, which Elo currently throws away.
    a.series_score AS maps_a,
    b.series_score AS maps_b,
    -- Rounds won across every map of the series. Finer-grained than maps, and
    -- it puts a Bo1 on the same footing as a Bo3 sweep (~0.68 round share each)
    -- instead of the 1.0 a map-count fraction would give it. NULL for the 41
    -- forfeits, which have no map rows at all.
    r.rounds_a,
    r.rounds_b
FROM match m
JOIN event e ON e.event_id = m.event_id AND e.tier IN (1, 2)
JOIN match_team a ON a.match_id = m.match_id AND a.team_number = 1
JOIN match_team b ON b.match_id = m.match_id AND b.team_number = 2
LEFT JOIN (
    SELECT mm.match_id,
           sum(sa.total_rounds) AS rounds_a,
           sum(sb.total_rounds) AS rounds_b
    FROM match_map mm
    JOIN match_map_team_score sa
      ON sa.match_map_id = mm.match_map_id AND sa.team_number = 1
    JOIN match_map_team_score sb
      ON sb.match_map_id = mm.match_map_id AND sb.team_number = 2
    GROUP BY mm.match_id
) r ON r.match_id = m.match_id
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


_ROSTERS_SQL = """
SELECT mm.match_id, mt.team_number,
       list(DISTINCT coalesce(CAST(s.player_id AS VARCHAR),
                              'h:' || lower(trim(s.player_handle)))) AS roster
FROM match_map_player_stat s
JOIN match_map mm ON mm.match_map_id = s.match_map_id
JOIN match_team mt ON mt.match_id = mm.match_id AND mt.team_number = s.team_number
GROUP BY 1, 2
"""


def _roster_churn(df: pd.DataFrame, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Fraction of each side's roster that is new since that team's last match.

    Uses who *lined up* for this match, which is known before it starts, but not
    anything about how it went — so this is pre-match information, not leakage.
    NaN for a team's first ever appearance, since there is nothing to compare to.
    """
    r = con.execute(_ROSTERS_SQL).df()
    rosters = {(int(m), int(t)): frozenset(x) for m, t, x in r.itertuples(index=False)}

    last: dict = {}
    out = {1: [], 2: []}
    for match_id, team_a, team_b in zip(df.match_id, df.team_a, df.team_b):
        for team, side in ((team_a, 1), (team_b, 2)):
            current, previous = rosters.get((int(match_id), side)), last.get(team)
            out[side].append(
                len(current - previous) / len(current)
                if current and previous
                else float("nan")
            )
            if current:
                last[team] = current
    return pd.DataFrame({"churn_a": out[1], "churn_b": out[2]}, index=df.index)


_PLAYER_STATS_SQL = """
SELECT mm.match_id, e.tier, s.team_number,
       coalesce(CAST(s.player_id AS VARCHAR),
                'h:' || lower(trim(s.player_handle))) AS player_key,
       CAST(s.rating AS DOUBLE) AS rating
FROM match_map_player_stat s
JOIN match_map mm USING (match_map_id)
JOIN match m USING (match_id)
JOIN event e USING (event_id)
WHERE e.tier IN (1, 2)
ORDER BY mm.match_id, mm.map_number, s.team_number, s.player_slot
"""


def _player_form_from_stats(
    matches: pd.DataFrame, stats: pd.DataFrame, window: int = 20
) -> pd.DataFrame:
    """Lineup form from prior maps only; current-match stats update history last."""
    by_match = {
        int(match_id): group
        for match_id, group in stats.groupby("match_id", sort=False)
    }
    history: dict[str, deque] = defaultdict(lambda: deque(maxlen=window))
    out = defaultdict(list)

    for match_id in matches.match_id:
        current = by_match.get(int(match_id), stats.iloc[:0])
        for side, suffix in ((1, "a"), (2, "b")):
            roster = current.loc[
                current.team_number.eq(side), "player_key"
            ].drop_duplicates()
            prior = [list(history[player]) for player in roster if history[player]]
            out[f"player_form_{suffix}"].append(
                sum(sum(rating for rating, _ in rows) / len(rows) for rows in prior)
                / len(prior)
                if prior else float("nan")
            )
            out[f"player_form_coverage_{suffix}"].append(
                len(prior) / len(roster) if len(roster) else float("nan")
            )
            observations = [item for rows in prior for item in rows]
            out[f"player_form_t2_share_{suffix}"].append(
                sum(tier == 2 for _, tier in observations) / len(observations)
                if observations else float("nan")
            )

        # Update only after both pre-match feature rows have been recorded.
        for row in current.dropna(subset=["rating"]).itertuples(index=False):
            history[row.player_key].append((float(row.rating), int(row.tier)))

    result = pd.DataFrame(out, index=matches.index)
    result["player_form_diff"] = result.player_form_a - result.player_form_b
    return result


def _player_form(
    matches: pd.DataFrame, con: duckdb.DuckDBPyConnection
) -> pd.DataFrame:
    return _player_form_from_stats(matches, con.execute(_PLAYER_STATS_SQL).df())


def margin_signal(df: pd.DataFrame) -> "pd.Series":
    """The training signal that won the variant comparison: share of maps won.

    Falls back to the binary result wherever the map score is missing (forfeits,
    and vlrggapi rows with no score). This matters more than it looks: a single
    NaN fed to `compute_elo` propagates into both teams' ratings and then across
    every opponent they ever meet, silently, without raising — one missing row
    turns the whole benchmark into NaN.
    """
    total = df.maps_a + df.maps_b
    return (df.maps_a / total).where(total > 0).fillna(df.score_a)


def elo_k(tiers: pd.Series, tier_2_weight: float = TIER_2_WEIGHT) -> "pd.Series":
    """Per-tier Elo K; Tier 2 defaults to the validated zero team-result weight."""
    return tiers.map({1: BEST_K, 2: BEST_K * tier_2_weight})


def build_features(con: duckdb.DuckDBPyConnection | None = None) -> pd.DataFrame:
    """One row per match, every feature computed from data available before it.

    Elo is pre-match by construction (`compute_elo` records the rating it used
    *before* applying the result). Churn and match counts are lagged explicitly.
    Label is 1 if team_a won; the 75 Bo2 draws are dropped, having no binary
    outcome.
    """
    owned = con is None
    con = con or db.connect(read_only=True)
    try:
        df = match_sequence(con).reset_index(drop=True)
        churn = _roster_churn(df, con)
        player_form = _player_form(df, con)
    finally:
        if owned:
            con.close()

    # Replay both official tiers, with Tier 2 at its validated zero Elo weight.
    signal = margin_signal(df).to_numpy()
    elo = pd.DataFrame(
        compute_elo(
            zip(df.match_id, df.team_a, df.team_b, signal),
            k=elo_k(df.tier),
        )[0]
    )

    out = pd.DataFrame(
        {
            "match_id": df.match_id,
            "year": df.year,
            "tier": df.tier,
            "team_a": df.team_a,
            "team_b": df.team_b,
            "elo_diff": elo.elo_a_pre - elo.elo_b_pre,
            "elo_p_a_win": elo.p_a_win,
            "churn_a": churn.churn_a,
            "churn_b": churn.churn_b,
            "player_form_a": player_form.player_form_a,
            "player_form_b": player_form.player_form_b,
            "player_form_diff": player_form.player_form_diff,
            "player_form_coverage_a": player_form.player_form_coverage_a,
            "player_form_coverage_b": player_form.player_form_coverage_b,
            "player_form_t2_share_a": player_form.player_form_t2_share_a,
            "player_form_t2_share_b": player_form.player_form_t2_share_b,
            # How many matches each side has played before this one. Elo cannot
            # express its own uncertainty, so a 1500 rating means both "average"
            # and "never seen" -- this separates the two.
            "n_prior_a": df.groupby("team_a").cumcount(),
            "n_prior_b": df.groupby("team_b").cumcount(),
            "label": df.score_a,
        }
    )
    return out[out.label != 0.5].reset_index(drop=True)


def predict_upcoming(
    fixtures: pd.DataFrame, history: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Attach current margin-aware Elo probabilities to normalized fixtures."""
    history = match_sequence() if history is None else history
    _, ratings = compute_elo(
        zip(
            history.match_id,
            history.team_a,
            history.team_b,
            margin_signal(history),
        ),
        k=elo_k(history.tier),
    )
    counts = pd.concat([history.team_a, history.team_b]).value_counts()
    out = fixtures.copy()
    out["elo_a"] = out.team_a_key.map(lambda key: ratings.get(key, DEFAULT_BASE))
    out["elo_b"] = out.team_b_key.map(lambda key: ratings.get(key, DEFAULT_BASE))
    out["p_team_a_win"] = [
        expected_score(a, b) for a, b in zip(out.elo_a, out.elo_b)
    ]
    out["p_team_b_win"] = 1 - out.p_team_a_win
    out["rating_matches_a"] = out.team_a_key.map(counts).fillna(0).astype(int)
    out["rating_matches_b"] = out.team_b_key.map(counts).fillna(0).astype(int)
    out["ratings_through_match_id"] = (
        int(history.match_id.max()) if not history.empty else pd.NA
    )
    return add_score_predictions(out)


def add_score_predictions(
    fixtures: pd.DataFrame,
    distributions: list[dict[str, float]] | None = None,
) -> pd.DataFrame:
    """Attach exact score, sweep, and map-count forecasts to series forecasts."""
    out = fixtures.copy()
    if "best_of" not in out:
        # Upgrade cached fixtures written before the feed gained this field.
        series = (
            out["event_series"]
            if "event_series" in out
            else pd.Series("", index=out.index)
        )
        out["best_of"] = series.str.contains(
            "grand final", case=False, na=False
        ).map({True: 5, False: 3})
    distributions = distributions or [
        series_score_probabilities(float(probability), int(best_of))
        for probability, best_of in zip(out.p_team_a_win, out.best_of)
    ]
    out["score_probabilities"] = distributions
    out["most_likely_score"] = [
        max(scores, key=scores.get) for scores in distributions
    ]
    out["p_most_likely_score"] = [
        scores[score]
        for scores, score in zip(distributions, out.most_likely_score)
    ]
    out["p_sweep"] = [
        sum(probability for score, probability in scores.items() if "0" in score)
        for scores in distributions
    ]
    out["p_full_distance"] = [
        sum(
            probability
            for score, probability in scores.items()
            if sum(map(int, score.split("-"))) == best_of
        )
        for scores, best_of in zip(distributions, out.best_of)
    ]
    out["expected_maps"] = [
        sum(
            sum(map(int, score.split("-"))) * probability
            for score, probability in scores.items()
        )
        for scores in distributions
    ]
    return out


def add_map_predictions(
    fixtures: pd.DataFrame,
    maps: list[str],
    history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Condition one fixture on an explicitly supplied ordered map pool."""
    if len(fixtures) != 1:
        raise ValueError("map picks can only be applied to one match")
    out = add_score_predictions(fixtures)
    best_of = int(out.best_of.iloc[0])
    if len(maps) != best_of:
        raise ValueError(f"Bo{best_of} requires exactly {best_of} maps")

    from .maps import map_probabilities, map_sequence

    match = out.iloc[0]
    forecasts = map_probabilities(
        map_sequence() if history is None else history,
        str(match.team_a_key),
        str(match.team_b_key),
        maps,
        implied_map_probability(float(match.p_team_a_win), best_of),
    )
    distribution = map_score_probabilities([
        forecast["p_team_a_win"] for forecast in forecasts
    ])
    p_team_a_win = sum(
        probability
        for score, probability in distribution.items()
        if int(score.split("-")[0]) > int(score.split("-")[1])
    )
    out["p_team_a_win_unconditional"] = out.p_team_a_win
    out["p_team_b_win_unconditional"] = out.p_team_b_win
    out["p_team_a_win"] = p_team_a_win
    out["p_team_b_win"] = 1 - p_team_a_win
    out["map_predictions"] = [forecasts]
    return add_score_predictions(out, [distribution])


def current_rankings(history: pd.DataFrame | None = None) -> pd.DataFrame:
    """Rank teams active in the latest Tier-1 season by current Elo."""
    history = match_sequence() if history is None else history
    columns = ["rank", "season", "team_name", "elo", "season_matches", "last_match_id"]
    official = history.loc[history.tier.eq(1) & history.year.notna()]
    if official.empty:
        return pd.DataFrame(columns=columns)

    _, ratings = compute_elo(
        zip(
            history.match_id,
            history.team_a,
            history.team_b,
            margin_signal(history),
        ),
        k=elo_k(history.tier),
    )
    season = int(official.year.max())
    active = official.loc[official.year.eq(season)]
    teams: dict = {}
    for row in active.itertuples(index=False):
        for key, name in (
            (row.team_a, row.team_a_name),
            (row.team_b, row.team_b_name),
        ):
            team = teams.setdefault(
                key, {"team_name": name, "season_matches": 0, "last_match_id": 0}
            )
            team["team_name"] = name
            team["season_matches"] += 1
            team["last_match_id"] = max(team["last_match_id"], int(row.match_id))

    out = pd.DataFrame([
        {"season": season, "elo": ratings[key], **team}
        for key, team in teams.items()
    ]).sort_values(["elo", "team_name"], ascending=[False, True], ignore_index=True)
    out.insert(0, "rank", out.index + 1)
    return out[columns]


def main() -> None:
    features = build_features()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / "features.parquet"
    features.to_parquet(path, index=False)
    print(f"{len(features):,} rows x {features.shape[1]} cols -> {path}")
    print(features.describe().round(3).to_string())


if __name__ == "__main__":
    main()
