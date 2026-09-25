"""Score logged forecasts against real results. The only test the model can't leak into.

    python scripts/grade_predictions.py

Run `vct load-vlrgg` after matches finish first.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vct_quant import db
from vct_quant.config import PROCESSED_DIR
from vct_quant.eval.metrics import brier_score, calibration_table, log_loss

MAX_SPREAD = 0.10
# Walk-forward production Elo (scripts/benchmark_elo.py) after the 2026-09-24 team-ID fix.
BACKTEST_LOG_LOSS = 0.6567
BACKTEST_BRIER = 0.2320
SHADOWS = {
    "p_team_a_win_ensemble": "fast/slow ensemble",
    "p_team_a_win_calibrated": "online shrink",
    # Logged from 2026-09-24; differs from Elo only for new team keys that
    # inherit a rating (docs/roster-carryover-2026-09-24.md).
    "p_team_a_win_carryover": "roster carry-over",
}


def _loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p.astype(float), 1e-12, 1 - 1e-12)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def _paired_t(diff: np.ndarray) -> float:
    sd = diff.std(ddof=1)
    return float(diff.mean() / (sd / np.sqrt(len(diff)))) if sd > 0 else 0.0


def _print_shadow_scores(scored: pd.DataFrame, column: str, label: str) -> None:
    """Keep the preregistered pooled score; show season cohorts as diagnostics."""
    both = scored[scored[column].notna()]
    if len(both) < 2:
        print(f"\n{label}: {len(both)} graded so far")
    else:
        yy = both.y.to_numpy()
        base = _loss(yy, both.p_team_a_win.to_numpy())
        shadow = _loss(yy, both[column].to_numpy())
        print(f"\n{label}, n = {len(both)}")
        print(f"elo    {base.mean():.4f}")
        print(f"shadow {shadow.mean():.4f}   paired t = {_paired_t(base - shadow):+.2f} (positive = shadow better)")

    years = sorted({2026, 2027} | set(both.scheduled_at.dt.year.dropna().astype(int)))
    for year in years:
        cohort = both[both.scheduled_at.dt.year == year]
        n = len(cohort)
        if n < 2:
            print(f"  {year}: n = {n} (paired t unavailable)")
            continue
        yy = cohort.y.to_numpy()
        base = _loss(yy, cohort.p_team_a_win.to_numpy())
        shadow = _loss(yy, cohort[column].to_numpy())
        print(f"  {year}: n = {n}, elo {base.mean():.4f}, shadow {shadow.mean():.4f}, "
              f"paired t = {_paired_t(base - shadow):+.2f}")


def main() -> int:
    log = pd.read_parquet(PROCESSED_DIR / "prediction_log.parquet")

    forecasts = log[log.predicted_at < log.scheduled_at].sort_values("predicted_at").groupby("match_id").tail(1)

    con = db.connect(read_only=True)
    try:
        results = con.execute(
            "SELECT match_id, team_id, team_name, is_winner FROM match_team"
        ).df()
    finally:
        con.close()

    played = results[results.is_winner.notna()]
    scored = forecasts.merge(played, on="match_id")
    is_team_a = (
        scored.team_id.eq(scored.team_a_id).fillna(False)  # match by ID when there is one
        | scored.team_name.eq(scored.team_a_name)          # else by name
    )
    scored = scored[is_team_a]
    scored["y"] = scored.is_winner.astype(int)

    if scored.empty:
        print(f"{len(forecasts)} forecasts logged, none played yet")
        return 0

    y, p = scored.y, scored.p_team_a_win
    print(f"n = {len(scored)}")
    print(f"log loss {log_loss(y, p):.4f}   (backtest {BACKTEST_LOG_LOSS:.4f}, coin flip 0.6931)")
    print(f"brier    {brier_score(y, p):.4f}   (backtest {BACKTEST_BRIER:.4f}, coin flip 0.2500)")
    print(calibration_table(y, p, bins=5).to_string(index=False))

    # Shadow models: logged beside Elo since 2026-09-24, graded only where logged.
    # Positive t = the shadow beats production Elo on the same matches.
    for column, label in SHADOWS.items():
        if column in scored:
            _print_shadow_scores(scored, column, label)

    # Market benchmark: only matches with a price, only liquid-enough markets.
    # A wide bid/ask spread means nobody is really trading -- that "price" is noise.
    if "p_market_a" not in scored:
        return 0
    priced = scored[scored.p_market_a.notna() & (scored.market_spread.fillna(1) <= MAX_SPREAD)]
    if len(priced) < 2:
        print(f"\nmarket: {len(priced)} liquid priced matches graded so far")
        return 0
    y, p_elo, p_mkt = priced.y.to_numpy(), priced.p_team_a_win.to_numpy(), priced.p_market_a.to_numpy()
    loss_elo = _loss(y, p_elo)
    loss_mkt = _loss(y, p_mkt)
    t = _paired_t(loss_mkt - loss_elo)  # positive = Elo beats the market
    print(f"\nvs Polymarket (spread <= {MAX_SPREAD}), n = {len(priced)}")
    print(f"elo    {loss_elo.mean():.4f}")
    print(f"market {loss_mkt.mean():.4f}   paired t = {t:+.2f} (positive = Elo better)")
    for column, label in SHADOWS.items():
        if column in priced and priced[column].notna().sum() >= 2:
            both = priced[priced[column].notna()]
            ls = _loss(both.y.to_numpy(), both[column].to_numpy())
            lm = _loss(both.y.to_numpy(), both.p_market_a.to_numpy())
            print(f"{label:<14} {ls.mean():.4f} vs market, n = {len(both)}, "
                  f"paired t = {_paired_t(lm - ls):+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
