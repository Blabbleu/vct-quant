"""Audit the frozen carry-over shadow against the original open-era harness.

    python scripts/benchmark_carryover.py

The historical test knows each match's actual lineup; upcoming forecasts do not.
No settings are selected or changed using the confirmation period or live log.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from model_lab import load  # noqa: E402
from open_era import loss, run, tstat  # noqa: E402

from vct_quant.config import PROCESSED_DIR
from vct_quant.features.build import load_rosters, predict_upcoming
from vct_quant.features.carryover import carryover_elo


def main() -> int:
    data = load()
    history = data["df"]
    rosters = load_rosters()
    baseline, _, _ = run(data)
    original, _, original_inherited = run(data, inherit=3, shrink=1.0, en_bloc=True)
    replay, state, inherited = carryover_elo(history, rosters)
    t1 = data["tier"] == 1
    if not np.allclose(replay[t1], original[t1], rtol=0, atol=1e-12):
        mismatches = np.flatnonzero(t1 & ~np.isclose(replay, original, rtol=0, atol=1e-12))
        raise AssertionError(f"carry-over harness mismatch: {mismatches[:10].tolist()}")
    if not np.array_equal(t1 & original_inherited, np.isin(data["match_id"], [x[0] for x in inherited])):
        raise AssertionError("inheritance decisions differ from original harness")
    if not np.allclose(carryover_elo(history, {})[0][t1], baseline[t1], rtol=0, atol=1e-12):
        raise AssertionError("empty-roster replay differs from primary Elo")
    scored = t1 & (data["y"] != 0.5)
    ids = data["match_id"]
    y22 = scored & (data["year"] == 2022)
    cut = np.median(ids[y22])
    print(f"exact harness parity: {int(t1.sum())} Tier-1 matches, {len(inherited)} inheritances, {len(state.rating)} rated teams")
    for label, mask in (
        ("2022 H1 tuning", y22 & (ids <= cut)),
        ("2022 H2 test", y22 & (ids > cut)),
        ("2023-26 confirmation", scored & (data["year"] >= 2023)),
    ):
        base_loss, candidate_loss = loss(data, baseline, mask), loss(data, replay, mask)
        print(f"{label}: n={int(mask.sum())}, Elo={base_loss.mean():.4f}, "
              f"carry-over={candidate_loss.mean():.4f}, paired t={tstat(base_loss - candidate_loss):+.2f}")
    cache = PROCESSED_DIR / "upcoming_tier1.parquet"
    if cache.exists():
        fixtures = pd.read_parquet(cache)
        if not fixtures.empty:
            # This is a read-only smoke test against the dev DB snapshot, not a
            # market or live-log scoring pass. Never write cached predictions.
            live = predict_upcoming(fixtures)
            tiers = live["tier"] if "tier" in live else pd.Series(1, index=live.index)
            official = live[tiers.ne(3)]
            if not official.empty and "p_team_a_win_carryover" in official:
                changed = (official.p_team_a_win_carryover - official.p_team_a_win).abs() > 1e-12
                print(f"cached official fixtures: {len(official)}, shadow differs: {int(changed.sum())}, "
                      f"known inherited sources: {int(official.carryover_from_a.notna().sum() + official.carryover_from_b.notna().sum())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
