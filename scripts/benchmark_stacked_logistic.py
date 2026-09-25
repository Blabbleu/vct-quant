"""Finish the precommitted 27-cell player-form logistic grid, without refetching features.

    python scripts/benchmark_stacked_logistic.py

Protocol: docs/stacked-logistic-protocol.md. Retrospective 2025/26 are not clean
holdouts; this script neither changes primary forecasts nor tunes on the live log.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from vct_quant.config import PROCESSED_DIR
from vct_quant.features.build import build_features, elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo

FEATURE_SETS = {
    "elo only (refit)": ["z_elo"],
    "elo + form": ["z_elo", "form_diff", "form_missing"],
    "elo + form + churn + exp": ["z_elo", "form_diff", "form_missing", "churn_diff", "exp_diff"],
}
YEARS_VALIDATION = (2023, 2024)
YEARS_TEST = (2025, 2026)


def prepare(features: pd.DataFrame) -> pd.DataFrame:
    """Preserve match IDs and pre-match predictors for binary Tier-1 labels."""
    f = features.loc[features.tier.eq(1) & features.year.notna() & features.label.isin([0.0, 1.0])].copy()
    f["year"] = f.year.astype(int)
    p = np.clip(f.elo_p_a_win.to_numpy(float), 1e-9, 1 - 1e-9)
    f["z_elo"] = np.log(p / (1 - p))
    f["form_diff"] = f.player_form_diff.fillna(0.0)
    f["form_missing"] = f.player_form_diff.isna().astype(float)
    f["churn_diff"] = f.churn_a.fillna(0.0) - f.churn_b.fillna(0.0)
    f["exp_diff"] = np.log1p(f.n_prior_a) - np.log1p(f.n_prior_b)
    return f


def predict_year(f: pd.DataFrame, year: int, cols: list[str], c: float, half_life: float) -> np.ndarray:
    train = f.loc[f.year < year]
    test = f.loc[f.year.eq(year)]
    if train.empty or test.empty:
        raise ValueError(f"missing train or test for {year}")
    assert train.match_id.max() < test.match_id.min(), "match ID chronology violated"
    assert train[cols].notna().all().all() and test[cols].notna().all().all()
    weights = (0.5 ** ((year - 1 - train.year) / half_life)).to_numpy() if half_life else np.ones(len(train))
    model = LogisticRegression(C=c, max_iter=1000)
    model.fit(train[cols], train.label, sample_weight=weights)
    return model.predict_proba(test[cols])[:, 1]


def loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def metrics(f: pd.DataFrame, p: np.ndarray) -> dict:
    y, b = f.label.to_numpy(float), f.elo_p_a_win.to_numpy(float)
    base, candidate = loss(y, b), loss(y, p)
    delta = base - candidate
    sd = delta.std(ddof=1) if len(delta) > 1 else 0.0
    return {
        "n": len(f), "elo_loss": float(base.mean()), "candidate_loss": float(candidate.mean()),
        "elo_brier": float(np.mean((b - y) ** 2)),
        "candidate_brier": float(np.mean((p - y) ** 2)),
        "paired_t": float(delta.mean() * math.sqrt(len(delta)) / sd) if sd else 0.0,
    }


def check_baseline(features: pd.DataFrame) -> None:
    """Independently replay production Elo; no post-match feature used in control."""
    history = match_sequence()
    rows, _ = compute_elo(
        zip(history.match_id, history.team_a, history.team_b, margin_signal(history)),
        k=elo_k(history.tier),
    )
    reference = pd.DataFrame({"match_id": history.match_id, "p": [row["p_a_win"] for row in rows]})
    aligned = features[["match_id", "elo_p_a_win"]].merge(reference, on="match_id", validate="one_to_one")
    assert len(aligned) == len(features), "reference rows missing"
    np.testing.assert_allclose(aligned.elo_p_a_win, aligned.p, atol=1e-12, rtol=0)


def main() -> None:
    features = build_features()  # expensive: do it exactly once, not 27 times
    check_baseline(features)
    f = prepare(features)
    print(f"Baseline parity checked; Tier-1 labeled rows: {len(f)}", flush=True)
    print(f"Player-form present: {f.form_missing.eq(0).sum()}/{len(f)}", flush=True)
    grid = [(name, cols, c, hl) for name, cols in FEATURE_SETS.items()
            for c in (0.03, 0.3, 3.0) for hl in (0.0, 1.0, 2.0)]
    best = None
    validation = []
    for name, cols, c, hl in grid:
        ps = [predict_year(f, year, cols, c, hl) for year in YEARS_VALIDATION]
        block = pd.concat([f.loc[f.year.eq(year)] for year in YEARS_VALIDATION])
        val = float(loss(block.label.to_numpy(float), np.concatenate(ps)).mean())
        validation.append({"features": name, "C": c, "half_life": hl, "loss": val})
        print(f"val {name:28} C={c:<5g} half-life={hl:g} loss={val:.4f}", flush=True)
        if best is None or val < best[0]:
            best = (val, name, cols, c, hl)
    assert best is not None
    val, name, cols, c, hl = best
    print(f"Frozen selection: {name}, C={c:g}, half-life={hl:g} (validation {val:.4f})", flush=True)
    period_results = {}
    for year in (*YEARS_VALIDATION, *YEARS_TEST):
        block = f.loc[f.year.eq(year)]
        pred = predict_year(f, year, cols, c, hl)
        period_results[str(year)] = metrics(block, pred)
        print(f"{year}: {period_results[str(year)]}", flush=True)
    blocks = [f.loc[f.year.eq(y)] for y in YEARS_TEST]
    predictions = [predict_year(f, y, cols, c, hl) for y in YEARS_TEST]
    period_results["2025+26"] = metrics(pd.concat(blocks), np.concatenate(predictions))
    print(f"2025+26: {period_results['2025+26']}", flush=True)
    out = {"selected": {"features": name, "C": c, "half_life": hl},
           "validation_loss": val, "grid": validation, "periods": period_results,
           "form_present": int(f.form_missing.eq(0).sum()), "total": len(f)}
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / "stacked_logistic.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"Wrote {path}", flush=True)


if __name__ == "__main__":
    main()
