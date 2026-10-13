"""Train-only experience gate between the frozen three-input stack and fast/slow."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from research import stack_ensemble as stack
from research import stack_fastslow as fs
from vct_quant import db
from vct_quant.features.build import match_sequence

PENALTY = 0.01


def prior_experience(matches: pd.DataFrame) -> pd.DataFrame:
    """Minimum Tier-1 appearances before each fixture, in match-ID order."""
    if (matches.match_id.isna().any() or matches.match_id.duplicated().any()
            or not matches.match_id.is_monotonic_increasing):
        raise ValueError("match sequence needs unique, ordered, non-null match IDs")
    counts: dict[object, int] = {}
    rows = []
    for row in matches.itertuples(index=False):
        if pd.isna(row.team_a) or pd.isna(row.team_b) or row.team_a == row.team_b:
            raise ValueError("fixture needs distinct, non-null teams")
        if row.tier == 1:
            rows.append((row.match_id, min(counts.get(row.team_a, 0), counts.get(row.team_b, 0))))
            counts[row.team_a] = counts.get(row.team_a, 0) + 1
            counts[row.team_b] = counts.get(row.team_b, 0) + 1
        else:
            rows.append((row.match_id, np.nan))
    return pd.DataFrame(rows, columns=["match_id", "prior_min"])


def align_counts(frame: pd.DataFrame, counts: pd.DataFrame) -> pd.DataFrame:
    for part in (frame, counts):
        if part.match_id.isna().any() or part.match_id.duplicated().any():
            raise ValueError("null or duplicate match ID")
    if set(frame.match_id) != set(counts.match_id):
        raise ValueError("missing or extra match ID in count replay")
    out = frame.merge(counts, on="match_id", validate="one_to_one")
    tier_one = out.tier.eq(1)
    if out.loc[tier_one, "prior_min"].isna().any():
        raise ValueError("missing Tier-1 prior count")
    return out


def blend(p3: np.ndarray, pfs: np.ndarray, weight: np.ndarray | float) -> np.ndarray:
    return stack.sigmoid(np.asarray(weight) * stack.logits(p3)
                         + (1 - np.asarray(weight)) * stack.logits(pfs))


def fit_weight(y: np.ndarray, p3: np.ndarray, pfs: np.ndarray,
               anchor: float = 0.5, penalty: float = 0.0) -> float:
    y = np.asarray(y, float)
    p3, pfs = np.asarray(p3, float), np.asarray(pfs, float)
    if (not len(y) or y.shape != p3.shape or y.shape != pfs.shape
            or not np.isin(y, (0, 1)).all()
            or not np.isfinite(np.column_stack((p3, pfs))).all()
            or np.any((p3 <= 0) | (p3 >= 1) | (pfs <= 0) | (pfs >= 1))):
        raise ValueError("invalid gate training rows")
    a, b = stack.logits(p3), stack.logits(pfs)

    def objective(w: float) -> float:
        z = w * a + (1 - w) * b
        return float(np.mean(np.logaddexp(0, z) - y * z) + penalty / 2 * (w-anchor)**2)

    solution = minimize_scalar(objective, bounds=(0, 1), method="bounded",
                               options={"xatol": 1e-12})
    if not solution.success:
        raise RuntimeError("gate weight optimization failed")
    candidates = [0.0, 1.0, float(anchor), float(solution.x)]
    best = min(objective(w) for w in candidates)
    return min((w for w in candidates if objective(w) <= best + 1e-12),
               key=lambda w: (abs(w-anchor), w))


def fit_gate(frame: pd.DataFrame) -> dict:
    train = frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.isin((2023, 2024))
    part = frame.loc[train]
    if part.empty or part.prior_min.isna().any():
        raise ValueError("no complete training rows")
    three, four = fs.fit_frozen(frame)
    threshold = float(part.prior_min.median())
    x = stack.logits(part[["p_elo", "p_rs", "p_ls"]].to_numpy(float))
    p3 = stack.predict(x, three)
    pfs = part.p_fs.to_numpy(float)
    y = part.y.to_numpy(float)
    global_weight = fit_weight(y, p3, pfs)
    low = part.prior_min.to_numpy(float) <= threshold
    if not low.any() or low.all():
        raise ValueError("experience split has an empty training group")
    weights = {name: fit_weight(y[mask], p3[mask], pfs[mask], global_weight, PENALTY)
               for name, mask in (("low", low), ("high", ~low))}
    return {"three": three, "four": four, "threshold": threshold,
            "global_weight": global_weight, "weights": weights,
            "train_n": int(len(part)), "train_groups": {"low": int(low.sum()), "high": int((~low).sum())}}


def predictions(part: pd.DataFrame, fitted: dict) -> dict[str, np.ndarray]:
    x = stack.logits(part[["p_elo", "p_rs", "p_ls", "p_fs"]].to_numpy(float))
    low = part.prior_min.to_numpy(float) <= fitted["threshold"]
    weight = np.where(low, fitted["weights"]["low"], fitted["weights"]["high"])
    p3 = stack.predict(x[:, :3], fitted["three"])
    return {"Elo": part.p_elo.to_numpy(float), "three-input": p3,
            "fast/slow": part.p_fs.to_numpy(float),
            "four-input": stack.predict(x, fitted["four"]),
            "experience gate": blend(p3, part.p_fs.to_numpy(float), weight)}


def evaluate(frame: pd.DataFrame) -> dict:
    fitted = fit_gate(frame)
    result = {"fit": {k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in fitted.items()},
              "years": {}}
    for year in (2025, 2026):
        part = frame.loc[frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.eq(year)]
        if part.empty or part.prior_min.isna().any():
            raise ValueError(f"no complete decisive Tier-1 rows for {year}")
        y = part.y.to_numpy(float)
        ps = predictions(part, fitted)
        low = part.prior_min.to_numpy(float) <= fitted["threshold"]
        models = {}
        for name, p in ps.items():
            row = stack.metrics(y, p, ps["Elo"])
            row["calibration"] = [[i, n, pred if n else None, actual if n else None]
                                  for i, n, pred, actual in stack.reliability(y, p)]
            models[name] = row
        groups = {name: {"n": int(mask.sum()), "losses": {
            model: float(np.mean(np.logaddexp(0, stack.logits(p[mask]))
                                 - y[mask] * stack.logits(p[mask]))) if mask.any() else None
            for model, p in ps.items()}}
            for name, mask in (("low", low), ("high", ~low))}
        result["years"][year] = {"match_ids": part.match_id.tolist(), "models": models, "groups": groups}
    tests = [result["years"][year]["models"]["experience gate"] for year in (2025, 2026)]
    result["verdict"] = ("WIN" if all(r["t"] > 2 and r["ece"] <= r["elo_ece"] for r in tests)
                         else "NOT PROVEN" if all(r["t"] > 0 for r in tests) else "REJECTED")
    return result


def load() -> pd.DataFrame:
    components = fs.load()
    con = db.connect(read_only=True)
    try:
        matches = match_sequence(con).reset_index(drop=True)
    finally:
        con.close()
    return align_counts(components, prior_experience(matches))


def main() -> None:
    print(json.dumps(evaluate(load()), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
