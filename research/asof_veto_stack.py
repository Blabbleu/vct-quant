"""Frozen production Elo plus as-of map veto edge trial."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from research import asof_economy_stack as economy_stack
from research import asof_map_veto as veto
from research import stack_ensemble as stack
from vct_quant import db
from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo

INPUTS = ("elo_logit", "veto_edge")
align = economy_stack.align
_scores = economy_stack._scores
verdict = economy_stack.verdict


def load() -> pd.DataFrame:
    """Replay prior draft features and the exact production Elo sequence."""
    con = db.connect(read_only=True)
    try:
        matches = match_sequence(con).reset_index(drop=True)
    finally:
        con.close()
    drafts, scores, ids = veto.load_raw()
    series, pools, _ = veto.build_series(matches, drafts, scores, ids)
    features = veto.replay(matches, series, pools)
    elo_rows, _ = compute_elo(
        zip(matches.match_id, matches.team_a, matches.team_b, margin_signal(matches)),
        k=elo_k(matches.tier),
    )
    elo = pd.DataFrame(elo_rows)[["match_id", "p_a_win"]].rename(columns={"p_a_win": "p_elo"})
    context = matches[["match_id", "tier", "year", "score_a"]].rename(columns={"score_a": "y"})
    return align(elo, context.merge(features, on="match_id", validate="one_to_one", sort=False))


def eligible(frame: pd.DataFrame) -> pd.Series:
    return (frame.prior_draft_series_a.ge(3) & frame.prior_draft_series_b.ge(3)
            & np.isfinite(frame.veto_edge))


def design(frame: pd.DataFrame) -> np.ndarray:
    """Registered input order: production Elo logit, then veto edge."""
    p = frame.p_elo.to_numpy(float)
    edge = frame.veto_edge.to_numpy(float)
    if not np.isfinite(p).all() or not np.isfinite(edge).all():
        raise ValueError("nonfinite stack inputs")
    if ((p < 0) | (p > 1)).any():
        raise ValueError("Elo probabilities outside [0, 1]")
    return np.column_stack((stack.logits(p), edge))


def fit_frozen(frame: pd.DataFrame) -> LogisticRegression:
    mask = (frame.tier.eq(1) & frame.y.isin((0, 1))
            & frame.year.isin((2023, 2024)) & eligible(frame))
    if not mask.any():
        raise ValueError("no eligible decisive Tier-1 fit rows in 2023-24")
    model = LogisticRegression()
    model.fit(design(frame.loc[mask]), frame.loc[mask, "y"].to_numpy(int))
    return model


def forecast(frame: pd.DataFrame, model: LogisticRegression) -> tuple[np.ndarray, int]:
    p = frame.p_elo.to_numpy(float).copy()
    use = eligible(frame).to_numpy(bool)
    if use.any():
        p[use] = model.predict_proba(design(frame.loc[use]))[:, 1]
    if not np.isfinite(p).all():
        raise ValueError("nonfinite Elo fallback")
    return p, int(use.sum())


def evaluate(frame: pd.DataFrame) -> dict:
    fit_mask = (frame.tier.eq(1) & frame.y.isin((0, 1))
                & frame.year.isin((2023, 2024)) & eligible(frame))
    model = fit_frozen(frame)
    result = {
        "sklearn_version": sklearn.__version__,
        "inputs": list(INPUTS),
        "intercept": model.intercept_.tolist(),
        "coefficients": model.coef_[0].tolist(),
        "fit_n": int(fit_mask.sum()),
        "years": {},
    }
    for year in (2025, 2026):
        part = frame.loc[frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.eq(year)]
        if part.empty:
            raise ValueError(f"no decisive Tier-1 rows for {year}")
        y = part.y.to_numpy(float)
        elo = part.p_elo.to_numpy(float)
        prediction, model_n = forecast(part, model)
        result["years"][year] = {
            "n": len(part), "eligible": model_n,
            "stack": _scores(y, prediction, elo),
            "elo": _scores(y, elo, elo),
        }
    result["verdict"] = verdict(result["years"])
    return result


def main() -> None:
    print(json.dumps(evaluate(load()), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
