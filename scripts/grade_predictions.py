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
    print(f"log loss {log_loss(y, p):.4f}   (backtest 0.6569, coin flip 0.6931)")
    print(f"brier    {brier_score(y, p):.4f}   (backtest 0.2321, coin flip 0.2500)")
    print(calibration_table(y, p, bins=5).to_string(index=False))

    # Market benchmark: only matches with a price, only liquid-enough markets.
    # A wide bid/ask spread means nobody is really trading -- that "price" is noise.
    if "p_market_a" not in scored:
        return 0
    priced = scored[scored.p_market_a.notna() & (scored.market_spread.fillna(1) <= MAX_SPREAD)]
    if len(priced) < 2:
        print(f"\nmarket: {len(priced)} liquid priced matches graded so far")
        return 0
    y, p_elo, p_mkt = priced.y.to_numpy(), priced.p_team_a_win.to_numpy(), priced.p_market_a.to_numpy()
    loss_elo = -(y * np.log(p_elo) + (1 - y) * np.log(1 - p_elo))
    loss_mkt = -(y * np.log(p_mkt) + (1 - y) * np.log(1 - p_mkt))
    diff = loss_mkt - loss_elo  # positive = Elo beats the market
    t = diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))
    print(f"\nvs Polymarket (spread <= {MAX_SPREAD}), n = {len(priced)}")
    print(f"elo    {loss_elo.mean():.4f}")
    print(f"market {loss_mkt.mean():.4f}   paired t = {t:+.2f} (positive = Elo better)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
