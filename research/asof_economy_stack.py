"""Frozen production Elo plus as-of Kaggle economy profile trial."""
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
from research import asof_economy
from research import asof_economy_kaggle as kaggle
from research import stack_ensemble as stack
from vct_quant import db
from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo

YEARS = (2023, 2024, 2025, 2026)
INPUTS = ("elo_logit", "full_buy_diff", "pistol_diff")


def align(elo: pd.DataFrame, economy: pd.DataFrame) -> pd.DataFrame:
    """Require one economy feature row for each Elo match ID."""
    for frame in (elo, economy):
        if frame.match_id.isna().any() or frame.match_id.duplicated().any():
            raise ValueError("null or duplicate match_id")
    if set(elo.match_id) != set(economy.match_id):
        raise ValueError("mismatched match_id sets")
    return elo.merge(economy, on="match_id", validate="one_to_one", sort=False)


def load() -> pd.DataFrame:
    """Build production Elo and the audited, strictly prior economy replay."""
    con = db.connect(read_only=True)
    try:
        matches = match_sequence(con).reset_index(drop=True)
    finally:
        con.close()
    eco, ids = kaggle.load_raw()
    economy, _ = kaggle.build_economy(matches, eco, ids)
    features, failures = asof_economy.replay(matches, economy)
    if not failures.empty:
        raise ValueError(f"unexpected economy replay join failures: {failures.to_dict('records')}")
    elo_rows, _ = compute_elo(
        zip(matches.match_id, matches.team_a, matches.team_b, margin_signal(matches)),
        k=elo_k(matches.tier),
    )
    elo = pd.DataFrame(elo_rows)[["match_id", "p_a_win"]].rename(columns={"p_a_win": "p_elo"})
    context = matches[["match_id", "tier", "year", "score_a"]].rename(columns={"score_a": "y"})
    return align(elo, context.merge(features, on="match_id", validate="one_to_one", sort=False))


def eligible(frame: pd.DataFrame) -> pd.Series:
    return (frame.prior_economy_rows_a.ge(3) & frame.prior_economy_rows_b.ge(3)
            & frame.full_buy_diff.notna() & frame.pistol_diff.notna())


def design(frame: pd.DataFrame) -> np.ndarray:
    """The three unscaled registered inputs, with no imputation."""
    p = frame.p_elo.to_numpy(float)
    differences = frame[["full_buy_diff", "pistol_diff"]].to_numpy(float)
    if not np.isfinite(p).all() or not np.isfinite(differences).all():
        raise ValueError("nonfinite stack inputs")
    if ((p < 0) | (p > 1)).any():
        raise ValueError("Elo probabilities outside [0, 1]")
    x = np.column_stack((stack.logits(p), differences))
    if not np.isfinite(x).all():
        raise ValueError("nonfinite stack inputs")
    return x


def fit_frozen(frame: pd.DataFrame) -> LogisticRegression:
    mask = (frame.tier.eq(1) & frame.y.isin((0, 1))
            & frame.year.isin((2023, 2024)) & eligible(frame))
    if not mask.any():
        raise ValueError("no eligible decisive Tier-1 fit rows in 2023-24")
    model = LogisticRegression()
    model.fit(design(frame.loc[mask]), frame.loc[mask, "y"].to_numpy(int))
    return model


def forecast(frame: pd.DataFrame, model: LogisticRegression) -> tuple[np.ndarray, int]:
    """Use frozen economy model only where both histories and rates are present."""
    p = frame.p_elo.to_numpy(float).copy()
    use = eligible(frame).to_numpy(bool)
    if use.any():
        p[use] = model.predict_proba(design(frame.loc[use]))[:, 1]
    if not np.isfinite(p).all():
        raise ValueError("nonfinite Elo fallback")
    return p, int(use.sum())


def verdict(years: dict) -> str:
    rows = [years[year]["stack"] for year in (2025, 2026)]
    if all(row["t"] > 2 and row["ece"] <= row["elo_ece"] for row in rows):
        return "WIN"
    if all(row["gain_mean"] > 0 for row in rows):
        return "NOT PROVEN"
    return "REJECTED"


def _scores(y: np.ndarray, p: np.ndarray, elo: np.ndarray) -> dict:
    row = stack.metrics(y, p, elo)
    row["gain_mean"] = row["elo_loss"] - row["loss"]
    row["reliability"] = [
        [bin_id, n, predicted if n else None, observed if n else None]
        for bin_id, n, predicted, observed in stack.reliability(y, p)
    ]
    return row


def evaluate(frame: pd.DataFrame) -> dict:
    model = fit_frozen(frame)
    result = {
        "sklearn_version": sklearn.__version__,
        "inputs": list(INPUTS),
        "intercept": model.intercept_.tolist(),
        "coefficients": model.coef_[0].tolist(),
        "fit_n": int((frame.tier.eq(1) & frame.y.isin((0, 1))
                     & frame.year.isin((2023, 2024)) & eligible(frame)).sum()),
        "years": {},
    }
    for year in YEARS:
        part = frame.loc[frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.eq(year)]
        if part.empty:
            raise ValueError(f"no decisive Tier-1 rows for {year}")
        y = part.y.to_numpy(float)
        elo = part.p_elo.to_numpy(float)
        prediction, model_n = forecast(part, model)
        result["years"][year] = {
            "n": len(part), "economy_model_n": model_n,
            "stack": _scores(y, prediction, elo),
            "elo": _scores(y, elo, elo),
        }
    result["verdict"] = verdict(result["years"])
    result["holdout_note"] = "Both test years were consulted in earlier research; even a WIN needs a later clean holdout."
    return result


def main() -> None:
    print(json.dumps(evaluate(load()), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
