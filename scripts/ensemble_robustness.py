"""Robustness of the fast/slow Elo ensemble found by scripts/model_lab2.py.

    python scripts/ensemble_robustness.py

1. Wider K grid (round 2's winner sat on both grid edges).
2. Neighbourhood: held-out gain for every config near the optimum -- a real
   effect is a plateau, an overfit is a spike.
3. Walk-forward folds (the scripts/benchmark_elo.py protocol) and calibration.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from model_lab import VALIDATION, Config, compare, load, losses, run  # noqa: E402

from vct_quant.eval import metrics  # noqa: E402
from vct_quant.eval.backtest import walk_forward_splits  # noqa: E402


def logit(p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def blend(runs, k1, k2, w):
    return 1 / (1 + np.exp(-(w * logit(runs[k1]) + (1 - w) * logit(runs[k2]))))


def main() -> int:
    d = load()
    base = run(d, Config())
    ks = (6.0, 8.0, 12.0, 16.0, 20.0, 24.0, 96.0, 128.0, 160.0, 192.0, 256.0)
    runs = {k: run(d, Config(k=k)) for k in ks}
    val = lambda p: losses(d, p, VALIDATION).mean()  # noqa: E731
    held = lambda p: (losses(d, base, (2025, 2026)) - losses(d, p, (2025, 2026)))  # noqa: E731

    rows = []
    for k1 in ks[:6]:
        for k2 in ks[6:]:
            for w in np.round(np.linspace(0.3, 0.8, 11), 2):
                p = blend(runs, k1, k2, w)
                h = held(p)
                rows.append((val(p), k1, k2, w, h.mean(), h.mean() / (h.std(ddof=1) / np.sqrt(len(h)))))
    rows.sort()
    print("top 10 by 2023-24 validation (held-out 2025+26 gain and paired t alongside):")
    print(f"{'val':>7} {'K_slow':>6} {'K_fast':>6} {'w_slow':>6} {'held gain':>9} {'t':>6}")
    for r in rows[:10]:
        print(f"{r[0]:7.4f} {r[1]:6g} {r[2]:6g} {r[3]:6.2f} {r[4]:+9.4f} {r[5]:+6.2f}")
    gains = np.array([r[4] for r in rows])
    ts = np.array([r[5] for r in rows])
    print(f"\nall {len(rows)} (slow<=24, fast>=96, w 0.3-0.8) configs: held-out gain > 0 in "
          f"{(gains > 0).mean():.0%}, t > 2 in {(ts > 2).mean():.0%}; median t {np.median(ts):+.2f}")

    # pick: best validation config
    _, k1, k2, w, _, _ = rows[0]
    p = blend(runs, k1, k2, w)
    print(f"\nselected on validation: {w:.2f} x K={k1:g} + {1 - w:.2f} x K={k2:g}")
    r = compare(d, base, p)
    for name, x in r.items():
        print(f"  {name:20} " + " ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in x.items()))

    # walk-forward protocol of benchmark_elo.py
    y = d["y"]
    scored = (y != 0.5) & (d["tier"] == 1)
    print("\nwalk-forward folds (benchmark_elo.py protocol):")
    yb, pb, pe = [], [], []
    for i, (_, test) in enumerate(walk_forward_splits(d["df"].match_id, n_splits=5)):
        m = test & scored
        lb, le = metrics.log_loss(y[m], base[m]), metrics.log_loss(y[m], p[m])
        print(f"  fold{i} n={m.sum():4d}  elo {lb:.4f}  ensemble {le:.4f}  {le - lb:+.4f}")
        yb.append(y[m]); pb.append(base[m]); pe.append(p[m])
    yy, bb, ee = map(np.concatenate, (yb, pb, pe))
    print(f"  POOLED n={len(yy)}  elo {metrics.log_loss(yy, bb):.4f} / brier {metrics.brier_score(yy, bb):.4f}"
          f"   ensemble {metrics.log_loss(yy, ee):.4f} / brier {metrics.brier_score(yy, ee):.4f}")
    print(f"  accuracy elo {((bb > .5) == (yy > .5)).mean():.3f}  ensemble {((ee > .5) == (yy > .5)).mean():.3f}")
    print("\ncalibration, 2025-26 held-out (ensemble):")
    m = scored & np.isin(d["year"], (2025, 2026))
    print(metrics.calibration_table(y[m], p[m]).to_string(index=False))
    print("\ncalibration, 2025-26 held-out (production Elo):")
    print(metrics.calibration_table(y[m], base[m]).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
