"""Score logged forecasts against real results. The only test the model can't leak into.

    python scripts/grade_predictions.py

Your job: fill in the three TODOs. Run `vct load-vlrgg` after matches finish first.
"""
from __future__ import annotations

import pandas as pd

from vct_quant import db
from vct_quant.config import PROCESSED_DIR
from vct_quant.eval.metrics import brier_score, calibration_table, log_loss


def main() -> int:
    log = pd.read_parquet(PROCESSED_DIR / "prediction_log.parquet")

    # TODO 1: keep only forecasts made BEFORE the match started
    #         (predicted_at < scheduled_at), then keep the LAST one per match_id.
    #         Hint: sort_values + groupby("match_id").tail(1)
    forecasts = log[log.predicted_at < log.scheduled_at].sort_values("predicted_at").groupby("match_id").tail(1)

    con = db.connect(read_only=True)
    try:
        results = con.execute(
            "SELECT match_id, team_id, team_name, is_winner FROM match_team"
        ).df()
    finally:
        con.close()

    # TODO 2: label y = 1 if team A won, else 0. Careful: team A in the log is
    #         NOT guaranteed to be team_number 1 in match_team. Join on
    #         team_a_id (fall back to team_a_name when the id is missing).
    #         Drop unplayed matches and draws (is_winner NULL).
    played = results[results.is_winner.notna()]
    scored = forecasts.merge(played, on="match_id")
    is_team_a = (
        scored.team_id.eq(scored.team_a_id).fillna(False)  # match by ID when there is one
        | scored.team_name.eq(scored.team_a_name)          # else by name
    )
    scored = scored[is_team_a]
    scored["y"] = scored.is_winner.astype(int)
    
    # TODO 3: print n, log_loss, brier_score, and calibration_table using
    #         y and p_team_a_win. Compare to the 0.6525 backtest number.
    if scored.empty:
        print(f"{len(forecasts)} forecasts logged, none played yet")
        return 0

    y, p = scored.y, scored.p_team_a_win
    print(f"n = {len(scored)}")
    print(f"log loss {log_loss(y, p):.4f}   (backtest 0.6525, coin flip 0.6931)")
    print(f"brier    {brier_score(y, p):.4f}   (backtest 0.2302, coin flip 0.2500)")
    print(calibration_table(y, p, bins=5).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
