"""The dashboard payload: every number the desk page shows.

One module so every front door agrees. `python -m vct_quant.dashboard` prints it
as JSON -- that is what server.js shells out to, since the Elo replay and the
DuckDB reads live here in Python -- and `scripts/report.py` bakes the same
payload into a standalone file for publishing.
Results are cached against the database's mtime, so a page refresh is free until
the next `vct update` rewrites the file.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
import pandas as pd

from . import db
from .config import DB_PATH, PROCESSED_DIR
from .eval import metrics
from .eval.backtest import walk_forward_splits
from .features.build import (
    GC_K,
    current_rankings,
    elo_k,
    margin_signal,
    match_sequence,
)
from .features.ratings import compute_elo

MAX_SPREAD = 0.10

# Every experiment that has been run and settled; see CLAUDE.md for the detail.
LEDGER = [
    {"name": "Margin-aware Elo (map share, K=48)", "holdout": "walk-forward Tier 1",
     "score": "0.6567", "verdict": "shipped"},
    {"name": "Binary win/loss signal", "holdout": "2023-24 Kaggle", "score": "0.6475",
     "verdict": "rejected"},
    {"name": "Round-share signal", "holdout": "2023-24 Kaggle", "score": "0.6441",
     "verdict": "rejected"},
    {"name": "Logistic calibration on Elo diff", "holdout": "2024", "score": "0.6790",
     "verdict": "rejected"},
    {"name": "Tier-2 results in the same pool", "holdout": "2025", "score": "0.6523",
     "verdict": "rejected"},
    {"name": "Gradient boosting (Elo + form + churn)", "holdout": "2025", "score": "0.6957",
     "verdict": "rejected"},
    {"name": "Glicko, season RD widening", "holdout": "2025", "score": "0.6462",
     "verdict": "rejected"},
    {"name": "Glicko, roster-churn RD widening", "holdout": "2026 (locked)", "score": "0.6670",
     "verdict": "rejected"},
    {"name": "Per-region offsets at internationals", "holdout": "2023-24 internationals",
     "score": "no gain at any k", "verdict": "rejected"},
    {"name": "One-parameter shrink, fit on prior year", "holdout": "2026", "score": "0.6634",
     "verdict": "not proven"},
    {"name": "Fast/slow Elo ensemble (0.7 K16 + 0.3 K256)", "holdout": "2025+26 (t=+1.70)",
     "score": "0.6488 wf", "verdict": "shadow"},
    {"name": "Online shrink, trailing 500", "holdout": "2025+26 (t=+1.21)",
     "score": "0.6642 '26", "verdict": "shadow"},
    {"name": "Player-level Elo blend", "holdout": "2025+26", "score": "t=+0.31",
     "verdict": "rejected"},
    {"name": "Inactivity decay (calendar days)", "holdout": "2025+26", "score": "t=+0.00",
     "verdict": "rejected"},
    {"name": "Best-of-aware map Elo", "holdout": "2025+26", "score": "t=-4.24",
     "verdict": "rejected"},
]


def _pool(tiers: tuple[int, ...], k) -> tuple[pd.DataFrame, np.ndarray]:
    df = match_sequence(tiers=tiers)
    rows = compute_elo(
        zip(df.match_id, df.team_a, df.team_b, margin_signal(df).to_numpy()),
        k=k(df) if callable(k) else k,
    )[0]
    return df, np.array([row["p_a_win"] for row in rows])


def official_backtest() -> dict:
    """Walk-forward Tier-1 Elo: the number every experiment is measured against."""
    df, p = _pool((1, 2), lambda d: elo_k(d.tier))
    y = df.score_a.to_numpy()
    scored = (y != 0.5) & df.tier.eq(1).to_numpy()
    folds, ys, ps = [], [], []
    for i, (_, test) in enumerate(walk_forward_splits(pd.Series(df.match_id), n_splits=5)):
        m = test & scored
        folds.append({"fold": i, "n": int(m.sum()),
                      "log_loss": float(metrics.log_loss(y[m], p[m]))})
        ys.append(y[m])
        ps.append(p[m])
    y, p = np.concatenate(ys), np.concatenate(ps)
    table = metrics.calibration_table(y, p, bins=10)
    return {
        "n": int(len(y)),
        "log_loss": float(metrics.log_loss(y, p)),
        "brier": float(metrics.brier_score(y, p)),
        "accuracy": float(((p > 0.5) == (y > 0.5)).mean()),
        "folds": folds,
        "calibration": [
            {"predicted": float(r.predicted), "actual": float(r.actual), "n": int(r.n)}
            for r in table.itertuples()
        ],
    }


def gc_pool() -> dict:
    """Game Changers is a separate pool; K is still the untuned placeholder."""
    df, p = _pool((3,), GC_K)
    y = df.score_a.to_numpy()
    m = (y != 0.5) & df.year.gt(2024).to_numpy()
    return {"n": int(m.sum()), "log_loss": float(metrics.log_loss(y[m], p[m])),
            "k": float(GC_K), "matches": int(len(df))}


def graded_log() -> dict:
    """Live forecasts scored against results: the only holdout never tuned on."""
    path = PROCESSED_DIR / "prediction_log.parquet"
    out = {"logged": 0, "graded": 0, "rows": []}
    if not path.exists():
        return out
    log = pd.read_parquet(path)
    forecasts = (
        log[log.predicted_at < log.scheduled_at]
        .sort_values("predicted_at")
        .groupby("match_id")
        .tail(1)
    )
    out["logged"] = int(len(forecasts))
    con = db.connect(read_only=True)
    try:
        results = con.execute(
            "SELECT match_id, team_id, team_name, is_winner FROM match_team"
        ).df()
    finally:
        con.close()
    played = results[results.is_winner.notna()]
    scored = forecasts.merge(played, on="match_id")
    is_a = (
        scored.team_id.eq(scored.team_a_id).fillna(False)
        | scored.team_name.eq(scored.team_a_name)
    )
    scored = scored[is_a]
    if scored.empty:
        return out
    y = scored.is_winner.astype(float).to_numpy()
    p = scored.p_team_a_win.to_numpy()
    out["graded"] = int(len(scored))
    out["log_loss"] = float(metrics.log_loss(y, p))
    out["brier"] = float(metrics.brier_score(y, p))
    liquid = scored.p_market_a.notna() & (scored.market_spread.fillna(1) <= MAX_SPREAD)
    if liquid.sum() >= 2:
        ym, pm = y[liquid.to_numpy()], scored.p_market_a[liquid].to_numpy()
        out["market"] = {
            "n": int(liquid.sum()),
            "elo": float(metrics.log_loss(ym, p[liquid.to_numpy()])),
            "market": float(metrics.log_loss(ym, pm)),
        }
    shadows = {}
    for column, name in (("p_team_a_win_ensemble", "ensemble"),
                         ("p_team_a_win_calibrated", "shrink")):
        if column not in scored:
            continue
        has = scored[column].notna().to_numpy()
        if has.sum():
            shadows[name] = {
                "n": int(has.sum()),
                "elo": float(metrics.log_loss(y[has], p[has])),
                "shadow": float(metrics.log_loss(y[has], scored[column].to_numpy()[has])),
            }
    out["shadows"] = shadows
    out["rows"] = [
        {"match_id": int(r.match_id), "team_a": r.team_a_name, "team_b": r.team_b_name,
         "p": float(r.p_team_a_win), "won": bool(r.is_winner),
         "market": None if pd.isna(r.p_market_a) else float(r.p_market_a)}
        for r in scored.itertuples()
    ]
    return out


def fixtures() -> list[dict]:
    path = PROCESSED_DIR / "upcoming_tier1.parquet"
    if not path.exists():
        return []
    up = pd.read_parquet(path).sort_values("scheduled_at")
    up = up[up.team_a_name.ne("TBD") & up.team_b_name.ne("TBD")]
    return [
        {
            "match_id": int(r.match_id),
            "start": r.scheduled_at.isoformat(),
            "event": r.event_name,
            "series": r.event_series,
            "tier": int(r.tier) if pd.notna(r.tier) else 1,
            "best_of": int(r.best_of),
            "team_a": r.team_a_name, "team_b": r.team_b_name,
            "elo_a": float(r.elo_a), "elo_b": float(r.elo_b),
            "p_a": float(r.p_team_a_win),
            "p_sweep": float(r.p_sweep),
            "matches_a": int(r.rating_matches_a), "matches_b": int(r.rating_matches_b),
            "market": None if pd.isna(r.p_market_a) else float(r.p_market_a),
            "spread": None if pd.isna(r.market_spread) else float(r.market_spread),
            "volume": None if pd.isna(r.market_volume) else float(r.market_volume),
            "url": r.vlr_url,
        }
        for r in up.itertuples()
    ]


def coverage() -> dict:
    con = db.connect(read_only=True)
    try:
        matches, dated, latest = con.execute(
            "SELECT count(*), count(completed_at), cast(max(completed_at) AS VARCHAR) FROM match"
        ).fetchone()
        tiers = dict(con.execute("""
            SELECT e.tier, count(*) FROM match m JOIN event e USING (event_id)
            WHERE e.tier IS NOT NULL GROUP BY 1
        """).fetchall())
    finally:
        con.close()
    return {"matches": int(matches), "dated": int(dated), "latest_result": latest,
            "tier_1": int(tiers.get(1, 0)), "tier_2": int(tiers.get(2, 0)),
            "tier_3": int(tiers.get(3, 0))}

def _db_stamp() -> float:
    """Cache key: the database's mtime, so `vct update` invalidates everything."""
    try:
        return DB_PATH.stat().st_mtime
    except OSError:
        return 0.0


@lru_cache(maxsize=4)
def _cached(stamp: float) -> dict:
    rankings = current_rankings().head(24)  # the leaderboard and the matchup picker
    return {
        "coverage": coverage(),
        "backtest": official_backtest(),
        "gc": gc_pool(),
        "rankings": [
            {"rank": int(r.rank), "team": r.team_name, "elo": float(r.elo),
             "matches": int(r.season_matches)}
            for r in rankings.itertuples()
        ],
        "season": int(rankings.season.iloc[0]) if not rankings.empty else None,
        "ledger": LEDGER,
    }


def snapshot() -> dict:
    """Everything the page renders. Elo replays are cached; fixtures never are."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **_cached(_db_stamp()),
        # Both read parquet written by `vct update`, so they are cheap and always fresh.
        "live": graded_log(),
        "fixtures": fixtures(),
    }


def main() -> None:
    """Print the payload as JSON on stdout: the backend's data source."""
    import json
    import sys

    json.dump(snapshot(), sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    main()
