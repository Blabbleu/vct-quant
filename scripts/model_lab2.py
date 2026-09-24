"""Model lab, round 2: the round-1 grid-edge result plus two structural ideas.

    python scripts/model_lab2.py

  bo_aware wide   Round 1's best map scale (500) sat on the grid edge; widen it.
  ensemble        Blend a fast and a slow Elo in logit space. One K is a single
                  bias/variance trade-off; teams change at different speeds.
  stacked         Walk-forward logistic regression, retrained each year on all
                  earlier Tier-1 matches, over logit(Elo) plus leakage-safe
                  player form, roster churn, and experience (features/build.py).
                  Regularization C and a recency half-life tuned on 2023-24.

Same protocol as scripts/model_lab.py: tune on 2023-24, score 2025 and 2026.
"""
from __future__ import annotations

import json
import math
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from vct_quant.config import PROCESSED_DIR
from vct_quant.features.build import build_features

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from model_lab import PERIODS, VALIDATION, Config, compare, load, losses, run  # noqa: E402


def logit(p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def sig(z):
    return 1 / (1 + np.exp(-z))


def stacked(d: dict, base: np.ndarray, C: float, half_life_years: float, cols: list[str]) -> np.ndarray:
    f = build_features()
    idx = pd.Series(np.arange(len(d["match_id"])), index=d["match_id"])
    f = f[f.match_id.isin(idx.index)].copy()
    f["row"] = idx.loc[f.match_id].to_numpy()
    f["z_elo"] = logit(base[f.row])
    f["form_diff"] = f.player_form_diff.fillna(0.0)
    f["form_missing"] = f.player_form_diff.isna().astype(float)
    f["churn_diff"] = f.churn_a.fillna(0.0) - f.churn_b.fillna(0.0)
    f["exp_diff"] = np.log1p(f.n_prior_a) - np.log1p(f.n_prior_b)
    t1 = f[f.tier.eq(1)]
    out = base.copy()
    for year in range(2023, 2027):
        train, test = t1[t1.year < year], t1[t1.year == year]
        if test.empty:
            continue
        w = 0.5 ** ((year - 1 - train.year) / half_life_years) if half_life_years else np.ones(len(train))
        model = LogisticRegression(C=C, max_iter=1000)
        model.fit(train[cols], train.label, sample_weight=w)
        out[test.row.to_numpy()] = model.predict_proba(test[cols])[:, 1]
    return out


def report(d, base, name, label, p, results):
    r = compare(d, base, p)
    results[name] = {"label": label, **r}
    print(f"\n{name}: {label}")
    print(f"  {'period':20} {'n':>5} {'baseline':>9} {'model':>9} {'brier':>7} {'paired t':>9}")
    for period in PERIODS:
        x = r[period]
        print(f"  {period:20} {x['n']:5d} {x['baseline']:9.4f} {x['candidate']:9.4f}"
              f" {x['brier']:7.4f} {x['t']:+9.2f}")
    h = r["held-out 2025+26"]
    print(f"  {'held-out 2025+26':20} {h['n']:5d}  gain {h['gain']:+.4f}, t={h['t']:+.2f}", flush=True)


def main() -> int:
    d = load()
    base = run(d, Config())
    results: dict = {}
    val = lambda p: losses(d, p, VALIDATION).mean()  # noqa: E731
    print(f"baseline validation: {val(base):.4f}", flush=True)

    # 1. bo-aware, wide scale grid
    grid = [Config(k=k, bo_aware=True, map_scale=s) for k in (32.0, 40.0, 48.0, 64.0)
            for s in (500.0, 650.0, 800.0, 1000.0, 1300.0, 1700.0)]
    scored = [(val(p), c, p) for c in grid for p in [run(d, c)]]
    v, c, p = min(scored, key=lambda x: x[0])
    print(f"bo_aware wide best val {v:.4f}: {c.label()}", flush=True)
    report(d, base, "bo_aware_wide", c.label(), p, results)

    # 2. fast/slow ensemble
    runs = {k: run(d, Config(k=k)) for k in (16.0, 24.0, 32.0, 48.0, 64.0, 96.0, 128.0)}
    best = None
    for k1 in runs:
        for k2 in runs:
            if k2 <= k1:
                continue
            for w in np.linspace(0.1, 0.9, 9):
                p = sig(w * logit(runs[k1]) + (1 - w) * logit(runs[k2]))
                s = val(p)
                if best is None or s < best[0]:
                    best = (s, k1, k2, w, p)
    s, k1, k2, w, p = best
    lab = f"{w:.1f} x K={k1:g} + {1 - w:.1f} x K={k2:g} (logit blend)"
    print(f"ensemble best val {s:.4f}: {lab}", flush=True)
    report(d, base, "ensemble", lab, p, results)

    # 3. stacked logistic
    feature_sets = {
        "elo only (refit)": ["z_elo"],
        "elo + form": ["z_elo", "form_diff", "form_missing"],
        "elo + form + churn + exp": ["z_elo", "form_diff", "form_missing", "churn_diff", "exp_diff"],
    }
    best = None
    for fs, cols in feature_sets.items():
        for C in (0.03, 0.3, 3.0):
            for hl in (0.0, 1.0, 2.0):
                p = stacked(d, base, C, hl, cols)
                s = val(p)
                print(f"  stacked {fs:28} C={C:<5g} half-life={hl:g}y  val {s:.4f}", flush=True)
                if best is None or s < best[0]:
                    best = (s, f"{fs}, C={C:g}, recency half-life={hl:g}y", p)
    s, lab, p = best
    report(d, base, "stacked", lab, p, results)

    path = PROCESSED_DIR / "model_lab2.json"
    path.write_text(json.dumps(results, indent=2))
    print(f"\n-> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
