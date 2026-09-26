"""Read-only GC two-speed / shrink lab. Frozen protocol: docs/gc-ensemble-lab.md.

Run `python -m scripts.gc_ensemble_lab tune` first; only run `test --pick NAME`
if tune selects a candidate. Never fit on or retune against the live log.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from scripts.gc_k_lab import paired_t, per_match_loss, replay

TUNE_THROUGH = 2024
WEIGHTS = (0.25, 0.50, 0.75)
SHRINK = (0.70, 0.80, 0.90, 1.10, 1.20, 1.30)
SHIP_T = 2.0


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-z))


def candidate_probabilities(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Whole-sequence, pre-match probabilities; includes non-scoring draws."""
    p96, p192, p256 = (replay(df, k) for k in (96., 192., 256.))
    z96, z192, z256 = map(_logit, (p96, p192, p256))
    out = {"reference": p192, "k_96": p96, "k_256": p256}
    for w in WEIGHTS:
        out[f"blend_{w:g}"] = _sigmoid(w * z96 + (1 - w) * z256)
    for a in SHRINK:
        out[f"shrink_{a:g}"] = _sigmoid(a * z192)
    return out


def scored_mask(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    scored = df.score_a.ne(0.5).to_numpy()
    tune = df.year.le(TUNE_THROUGH).fillna(False).to_numpy()
    test = df.year.gt(TUNE_THROUGH).fillna(False).to_numpy()
    return scored & tune, scored & test


def choose(y: np.ndarray, probabilities: dict[str, np.ndarray], mask: np.ndarray) -> tuple[str, dict[str, float]]:
    """Single tune-only selection; never evaluates component-only K keys."""
    if not mask.any():
        raise ValueError("no scored tuning matches")
    keys = [k for k in probabilities if k == "reference" or k.startswith(("blend_", "shrink_"))]
    losses = {k: float(per_match_loss(y[mask], probabilities[k][mask]).mean()) for k in keys}
    def order(key: str) -> tuple:
        distance = (0. if key == "reference" else abs(float(key.split("_")[1]) -
                    (0.5 if key.startswith("blend_") else 1.0)))
        return losses[key], key != "reference", distance, key
    return min(keys, key=order), losses


def decide(t: float, by_year_diff: dict[int, float]) -> bool:
    return bool(t >= SHIP_T and by_year_diff and all(v > 0 for v in by_year_diff.values()))


def evaluate(df: pd.DataFrame, probabilities: dict[str, np.ndarray], pick: str) -> dict:
    """Paired, once-only 2025+ evaluation against the already-frozen K=192."""
    if pick == "reference" or pick not in probabilities or pick.startswith("k_"):
        raise ValueError("pick must be a tuning-selected candidate")
    _, mask = scored_mask(df)
    if not mask.any():
        raise ValueError("no scored test matches")
    y = df.score_a.to_numpy(dtype=float)[mask]
    p0, p1 = probabilities["reference"][mask], probabilities[pick][mask]
    l0, l1 = per_match_loss(y, p0), per_match_loss(y, p1)
    years = df.year.to_numpy()[mask]
    by_year = {}
    diffs = {}
    for year in sorted(set(years.tolist())):
        m = years == year
        diffs[int(year)] = float(l0[m].mean() - l1[m].mean())
        by_year[int(year)] = {"n": int(m.sum()), "reference": float(l0[m].mean()),
                              "candidate": float(l1[m].mean()), "t": paired_t(l0[m], l1[m])}
    t = paired_t(l0, l1)
    return {"pick": pick, "n": int(mask.sum()), "reference": float(l0.mean()),
            "candidate": float(l1.mean()), "t": t,
            "brier_reference": float(((p0 - y) ** 2).mean()),
            "brier_candidate": float(((p1 - y) ** 2).mean()),
            "by_year": by_year, "propose_shadow": decide(t, diffs)}


def main() -> None:
    from vct_quant.features.build import match_sequence

    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("tune", "test"))
    ap.add_argument("--pick", help="the pick printed by the tune stage")
    args = ap.parse_args()
    df = match_sequence(tiers=(3,))
    probabilities = candidate_probabilities(df)
    y = df.score_a.to_numpy(dtype=float)
    tune_mask, _ = scored_mask(df)
    pick, losses = choose(y, probabilities, tune_mask)
    if args.stage == "tune":
        print(json.dumps({"n": int(tune_mask.sum()), "losses": losses, "pick": pick}, indent=2))
        return
    if pick == "reference":
        ap.error("reference won tuning; protocol forbids test evaluation")
    if args.pick != pick:
        ap.error(f"tune selection is {pick}; --pick must match")
    print(json.dumps(evaluate(df, probabilities, pick), indent=2))


if __name__ == "__main__":
    main()
