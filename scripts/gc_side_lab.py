"""Game Changers side-1 advantage lab (protocol: docs/gc-side-advantage.md).

    python scripts/gc_side_lab.py tune    # years <= 2024 only; prints the (K, h) pick
    python scripts/gc_side_lab.py test    # scores 2025-26 once, only if h > 0

Read-only; changes nothing in production.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

TUNE_THROUGH = 2024
BASE = 1500.0
SHIP_T = 2.0
K_GRID = [96.0, 128.0, 192.0, 256.0]
H_GRID = [float(h) for h in range(0, 121, 10)]
H_STEP = 20.0
REFERENCE = (192.0, 0.0)  # A73 candidate: margin K=192, no side advantage


def replay(team_a, team_b, s, k: float, h: float = 0.0) -> np.ndarray:
    """Pre-match P(side 1 wins) with a side-1 advantage of h Elo points.

    h enters prediction and update alike (standard home-advantage Elo), so
    h = 0 is exactly `compute_elo` at the same K.
    """
    ratings: dict = {}
    p = np.empty(len(s))
    for i, (a, b, sa) in enumerate(zip(team_a, team_b, s)):
        ra = ratings.get(a, BASE)
        rb = ratings.get(b, BASE)
        e = 1.0 / (1.0 + 10.0 ** ((rb - ra - h) / 400.0))
        p[i] = e
        ratings[a] = ra + k * (sa - e)
        ratings[b] = rb - k * (sa - e)
    return p


def per_match_loss(y, p) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-15, 1 - 1e-15)
    y = np.asarray(y, dtype=float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def paired_t(loss_base, loss_new) -> float:
    """Positive = new is better."""
    diff = np.asarray(loss_base) - np.asarray(loss_new)
    if len(diff) < 2:
        return float("nan")
    sd = diff.std(ddof=1)
    if sd == 0:
        return float("nan")
    return float(diff.mean() / (sd / np.sqrt(len(diff))))


def predict(df: pd.DataFrame, cfg) -> np.ndarray:
    from vct_quant.features.build import margin_signal

    k, h = cfg
    return replay(df.team_a.to_numpy(), df.team_b.to_numpy(),
                  margin_signal(df).to_numpy(dtype=float), k, h)


def select(losses: dict) -> tuple:
    """Lowest loss; ties prefer the smaller h, then the reference K."""
    return min(losses, key=lambda c: (losses[c], c[1], c != REFERENCE, c[0]))


def tune(df: pd.DataFrame) -> dict:
    y = df.score_a.to_numpy(dtype=float)
    mask = (y != 0.5) & df.year.le(TUNE_THROUGH).to_numpy()
    hs = list(H_GRID)
    losses: dict = {}
    while True:
        for k in K_GRID:
            for h in hs:
                if (k, h) not in losses:
                    losses[(k, h)] = float(per_match_loss(y[mask], predict(df, (k, h))[mask]).mean())
        best = select(losses)
        if best[1] < max(hs) or max(hs) >= 400:
            break
        hs.append(max(hs) + H_STEP)
    return {"n": int(mask.sum()), "losses": losses, "selected": best}


def decide(t: float, year_diffs: dict) -> bool:
    """Frozen rule: t >= 2 and H better (lower mean loss) in every test year."""
    return bool(t >= SHIP_T and year_diffs and all(d > 0 for d in year_diffs.values()))


def test(df: pd.DataFrame, cfg) -> dict:
    from vct_quant.eval import metrics

    if cfg[1] == 0.0:
        raise ValueError("selection has h = 0: protocol says do not score")
    y = df.score_a.to_numpy(dtype=float)
    mask = (y != 0.5) & df.year.gt(TUNE_THROUGH).to_numpy()
    pr = predict(df, REFERENCE)[mask]
    pc = predict(df, cfg)[mask]
    ym = y[mask]
    lr, lc = per_match_loss(ym, pr), per_match_loss(ym, pc)
    out = {"n": int(mask.sum()), "cfg": list(cfg),
           "loss_ref": float(lr.mean()), "loss_cfg": float(lc.mean()),
           "t": paired_t(lr, lc),
           "brier_ref": float(((pr - ym) ** 2).mean()),
           "brier_cfg": float(((pc - ym) ** 2).mean()),
           "side1_rate": float(ym.mean()), "mean_p_ref": float(pr.mean()),
           "mean_p_cfg": float(pc.mean()), "by_year": {}}
    years = df.year.to_numpy()[mask]
    diffs = {}
    for yr in sorted(set(years.tolist())):
        m = years == yr
        diffs[int(yr)] = float(lr[m].mean() - lc[m].mean())
        out["by_year"][int(yr)] = {"n": int(m.sum()), "loss_ref": float(lr[m].mean()),
                                   "loss_cfg": float(lc[m].mean()),
                                   "t": paired_t(lr[m], lc[m])}
    out["calibration_cfg"] = metrics.calibration_table(ym, pc).to_dict("records")
    out["propose_shadow"] = decide(out["t"], diffs)
    return out


def main() -> None:
    from vct_quant.features.build import match_sequence

    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["tune", "test"])
    args = ap.parse_args()
    df = match_sequence(tiers=(3,))
    print(f"GC matches {len(df):,}")
    res = tune(df)
    if args.stage == "tune":
        for k in K_GRID:
            row = "  ".join(f"h{int(h)}={res['losses'][(k, h)]:.5f}"
                            for h in sorted(h for kk, h in res["losses"] if kk == k))
            print(f"K={k:g}: {row}")
        sel = res["selected"]
        print(json.dumps({"tune_n": res["n"], "selected_k": sel[0], "selected_h": sel[1],
                          "ref_loss": res["losses"][REFERENCE],
                          "sel_loss": res["losses"][sel]}))
        return
    out = test(df, res["selected"])
    print(json.dumps({k: v for k, v in out.items() if k != "calibration_cfg"}, indent=1))
    for row in out["calibration_cfg"]:
        print(f"  {str(row['bucket']):>14}  n={row['n']:5d}  pred {row['predicted']:.3f}  "
              f"actual {row['actual']:.3f}")
    print(f"\ndecision (frozen: t >= {SHIP_T} and both years favour H): "
          f"{'PROPOSE GC side-advantage SHADOW' if out['propose_shadow'] else 'negative, A73 stands'}")


if __name__ == "__main__":
    main()
