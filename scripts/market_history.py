"""Opening vs latest *observed* liquid Polymarket quotes in the forecast log.

    python scripts/market_history.py

These are sampled every matchday refresh, not exchange opening/closing trades.
Do not treat the latest observation as a closing price without checking its
hours-to-start. This report is diagnostic, not a model-selection set.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vct_quant import db
from vct_quant.config import PROCESSED_DIR
MAX_SPREAD = 0.10  # same liquidity filter as the live grader
DISAGREEMENT = 0.10  # fixed diagnostic threshold, not tuned on results


def _loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p.astype(float), 1e-12, 1 - 1e-12)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def _paired_t(diff: np.ndarray) -> float:
    sd = diff.std(ddof=1)
    return float(diff.mean() / (sd / np.sqrt(len(diff)))) if sd > 0 else 0.0


def observed_pairs(log: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """One played series with two liquid pre-match snapshots of the same pairing/market."""
    columns = ["match_id", "y", "p_market_open", "p_market_latest",
               "p_elo_open", "p_elo_latest", "latest_hours_to_start"]
    if log.empty or results.empty:
        return pd.DataFrame(columns=columns)
    rows = log.copy()
    rows["predicted_at"] = pd.to_datetime(rows.predicted_at, utc=True)
    rows["scheduled_at"] = pd.to_datetime(rows.scheduled_at, utc=True)
    rows = rows[
        rows.predicted_at.lt(rows.scheduled_at)
        & rows.p_market_a.between(0, 1, inclusive="neither")
        & rows.p_team_a_win.between(0, 1, inclusive="neither")
        & rows.market_spread.le(MAX_SPREAD)
        & rows.market_slug.notna()
    ]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    played = results[results.is_winner.notna()]
    scored = rows.merge(played, on="match_id", how="inner")
    same_team = scored.team_id.eq(scored.team_a_id).fillna(False)
    fallback = scored.team_a_id.isna() & scored.team_name.eq(scored.team_a_name)
    scored = scored[same_team | fallback]
    pairs = []
    for match_id, frame in scored.groupby("match_id"):
        group = pd.DataFrame(frame)
        # A renamed side or a different market invalidates a longitudinal price.
        if any(group[col].nunique(dropna=False) != 1 for col in
               ("team_a_key", "team_b_key", "market_slug")):
            continue
        group = group.sort_values("predicted_at").drop_duplicates("predicted_at")
        if len(group) < 2:
            continue
        first, last = group.iloc[0], group.iloc[-1]
        pairs.append({
            "match_id": match_id, "y": int(last.is_winner),
            "p_market_open": float(first.p_market_a),
            "p_market_latest": float(last.p_market_a),
            "p_elo_open": float(first.p_team_a_win),
            "p_elo_latest": float(last.p_team_a_win),
            "latest_hours_to_start": (last.scheduled_at - last.predicted_at).total_seconds() / 3600,
        })
    return pd.DataFrame(pairs, columns=columns)


def _report(label: str, pairs: pd.DataFrame, suffix: str) -> None:
    n = len(pairs)
    if n < 2:
        print(f"{label}: n={n}; paired t unavailable")
        return
    y = pairs.y.to_numpy()
    lm = _loss(y, pairs[f"p_market_{suffix}"].to_numpy())
    le = _loss(y, pairs[f"p_elo_{suffix}"].to_numpy())
    print(f"{label}: n={n}, Elo {le.mean():.4f}, market {lm.mean():.4f}, "
          f"paired t={_paired_t(lm - le):+.2f} (positive = Elo better)")


def main() -> None:
    log = pd.read_parquet(PROCESSED_DIR / "prediction_log.parquet")
    con = db.connect(read_only=True)
    try:
        results = con.execute(
            "SELECT match_id, team_id, team_name, is_winner FROM match_team"
        ).df()
    finally:
        con.close()
    pairs = observed_pairs(log, results)
    print(f"Two liquid pre-match observations on {len(pairs)} played series; "
          "first/latest sampled snapshots, NOT exchange open/close")
    if pairs.empty:
        return
    print(f"Latest snapshot hours before start: median={pairs.latest_hours_to_start.median():.1f}, "
          f"range={pairs.latest_hours_to_start.min():.1f}–"
          f"{pairs.latest_hours_to_start.max():.1f}")
    for suffix in ("open", "latest"):
        _report(suffix, pairs, suffix)
        diff = (pairs[f"p_elo_{suffix}"] - pairs[f"p_market_{suffix}"]).abs()
        _report(f"{suffix}, disagreement >= {DISAGREEMENT:.0%}", pairs[diff >= DISAGREEMENT], suffix)


if __name__ == "__main__":
    main()
