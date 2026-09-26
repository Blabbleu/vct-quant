"""Game Changers K retune lab (protocol: docs/gc-k-retune.md).

    python scripts/gc_k_lab.py tune     # years <= 2024 only; prints the pick
    python scripts/gc_k_lab.py test     # scores 2025-26 once at the pick vs K=48

Read-only: opens the DB read_only through `match_sequence`. Does not change
`features.build.GC_K`; a K change needs the owner's approval.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

TUNE_THROUGH = 2024
K_GRID = [16.0, 24.0, 32.0, 48.0, 64.0, 96.0, 128.0, 192.0, 256.0]
PRODUCTION_K = 48.0
SHIP_T = 2.0


def per_match_loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-15, 1 - 1e-15)
    y = np.asarray(y, dtype=float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def paired_t(loss_base: np.ndarray, loss_new: np.ndarray) -> float:
    """Positive = new is better."""
    diff = np.asarray(loss_base) - np.asarray(loss_new)
    sd = diff.std(ddof=1)
    if len(diff) < 2 or sd == 0:
        return float("nan")
    return float(diff.mean() / (sd / np.sqrt(len(diff))))


def replay(df: pd.DataFrame, k: float) -> np.ndarray:
    from vct_quant.features.build import margin_signal
    from vct_quant.features.ratings import compute_elo

    signal = margin_signal(df).to_numpy()
    rows = compute_elo(zip(df.match_id, df.team_a, df.team_b, signal), k=k)[0]
    return np.array([row["p_a_win"] for row in rows])


def pick_k(losses: dict[float, float], grid: list[float]) -> tuple[float, bool]:
    """Lowest mean tune loss; second value True if it sits on a grid edge."""
    best = min(grid, key=lambda k: (losses[k], k))
    return best, best in (grid[0], grid[-1])


def extend_grid(grid: list[float], edge: float) -> list[float]:
    step = 1.5
    return sorted(set(grid) | {edge * step if edge == grid[-1] else edge / step})


def tune(df: pd.DataFrame) -> dict:
    y = df.score_a.to_numpy()
    mask = (y != 0.5) & df.year.le(TUNE_THROUGH).to_numpy()
    grid = list(K_GRID)
    losses: dict[float, float] = {}
    while True:
        for k in grid:
            if k not in losses:
                losses[k] = float(per_match_loss(y[mask], replay(df, k)[mask]).mean())
        best, on_edge = pick_k(losses, grid)
        if not on_edge or best < 4 or best > 4096:
            break
        grid = extend_grid(grid, best)
    return {"n": int(mask.sum()), "losses": losses, "best_k": best}


def test(df: pd.DataFrame, k: float, skip_label: str = "") -> dict:
    from vct_quant.eval import metrics

    y = df.score_a.to_numpy()
    mask = (y != 0.5) & df.year.gt(TUNE_THROUGH).to_numpy()
    p0 = replay(df, PRODUCTION_K)
    p1 = replay(df, k)
    l0 = per_match_loss(y[mask], p0[mask])
    l1 = per_match_loss(y[mask], p1[mask])
    out = {
        "label": skip_label, "n": int(mask.sum()), "k": k,
        "loss_48": float(l0.mean()), "loss_k": float(l1.mean()),
        "brier_48": float(((p0[mask] - y[mask]) ** 2).mean()),
        "brier_k": float(((p1[mask] - y[mask]) ** 2).mean()),
        "t": paired_t(l0, l1), "by_year": {},
    }
    years = df.year.to_numpy()[mask]
    for yr in sorted(set(years.tolist())):
        m = years == yr
        out["by_year"][int(yr)] = {
            "n": int(m.sum()), "loss_48": float(l0[m].mean()),
            "loss_k": float(l1[m].mean()), "t": paired_t(l0[m], l1[m]),
        }
    out["calibration_48"] = metrics.calibration_table(y[mask], p0[mask]).to_dict("records")
    out["calibration_k"] = metrics.calibration_table(y[mask], p1[mask]).to_dict("records")
    return out


def main() -> None:
    from vct_quant.features.build import match_sequence

    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["tune", "test"])
    ap.add_argument("--k", type=float, help="tuned K for the test stage")
    args = ap.parse_args()
    df = match_sequence(tiers=(3,))
    print(f"GC matches {len(df):,}")
    if args.stage == "tune":
        res = tune(df)
        for k in sorted(res["losses"]):
            print(f"K={k:7.2f}  tune log loss {res['losses'][k]:.6f}")
        print(json.dumps({"tune_n": res["n"], "best_k": res["best_k"]}))
        return
    if args.k is None:
        ap.error("test needs --k from the tune stage")
    results = [test(df, args.k, "production flags")]
    results.append(test(match_sequence(tiers=(3,), skip_unscored=True), args.k,
                        "SKIP_UNSCORED_FORFEITS on (A72)"))
    for r in results:
        print(f"\n[{r['label']}] n={r['n']}  K=48 {r['loss_48']:.6f}  K={r['k']:g} "
              f"{r['loss_k']:.6f}  paired t={r['t']:+.2f}  "
              f"Brier {r['brier_48']:.5f} -> {r['brier_k']:.5f}")
        for yr, v in r["by_year"].items():
            print(f"   {yr}: n={v['n']}  {v['loss_48']:.6f} -> {v['loss_k']:.6f}  t={v['t']:+.2f}")
    r = results[0]
    for name in ("calibration_48", "calibration_k"):
        print(f"\n{name}")
        for row in r[name]:
            print(f"  {str(row['bucket']):>14}  n={row['n']:5d}  pred {row['predicted']:.3f}  "
                  f"actual {row['actual']:.3f}")
    ship = r["k"] != PRODUCTION_K and r["t"] >= SHIP_T
    print(f"\ndecision (frozen rule t >= {SHIP_T}): {'PROPOSE K=%g' % r['k'] if ship else 'keep K=48'}")


if __name__ == "__main__":
    main()
