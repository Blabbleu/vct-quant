"""Frozen offline Elo plus strictly prior lineup player-form trial."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "src"))
import asof_player_form as asof
import stack_ensemble as stack
from vct_quant.features.build import elo_k, margin_signal
from vct_quant.features.ratings import compute_elo

FEATURES = ("form_diff", "coverage_diff", "lineup_diff", "missing_diff")
YEARS = (2023, 2024, 2025, 2026)


def align(elo: pd.DataFrame, form: pd.DataFrame) -> pd.DataFrame:
    """Join full histories by ID, refusing missing IDs and reversed sides."""
    for frame in (elo, form):
        if frame.match_id.isna().any() or frame.match_id.duplicated().any():
            raise ValueError("null or duplicate match_id")
    if set(elo.match_id) != set(form.match_id):
        raise ValueError("mismatched match_id sets")
    out = elo.merge(form, on="match_id", validate="one_to_one", suffixes=("", "_form"), sort=False)
    if not ((out.team_a == out.team_a_form).all() and (out.team_b == out.team_b_form).all()):
        raise ValueError("team-A/team-B sides disagree")
    return out.drop(columns=["team_a_form", "team_b_form"])


def load() -> pd.DataFrame:
    """Build exactly the production Elo replay and the as-of replay on one snapshot."""
    matches, identities, stats = asof.load_snapshot()
    if matches.match_id.isna().any() or matches.match_id.duplicated().any():
        raise ValueError("null or duplicate match_id in match sequence")
    matches = matches.reset_index(drop=True)
    features = asof.replay(matches, identities, stats).reset_index(drop=True)
    if (features.match_id.isna().any() or features.match_id.duplicated().any()
            or set(features.match_id) != set(matches.match_id)):
        raise ValueError("as-of replay has null, duplicate, missing or extra match_id")
    elo_rows, _ = compute_elo(zip(matches.match_id, matches.team_a, matches.team_b,
                                  margin_signal(matches)), k=elo_k(matches.tier))
    elo = pd.DataFrame(elo_rows)[["match_id", "team_a", "team_b", "p_a_win"]].rename(
        columns={"p_a_win": "p_elo"})
    form = matches[["match_id", "team_a", "team_b", "score_a", "tier", "completed_at"]].merge(
        features, on="match_id", validate="one_to_one", sort=False)
    out = align(elo, form)
    out["year"] = pd.to_datetime(out.completed_at, utc=True).dt.year
    return out.rename(columns={"score_a": "y"})


def design(frame: pd.DataFrame) -> np.ndarray:
    """Unscaled columns in the registered order; absent form difference is zero."""
    x = np.column_stack((
        stack.logits(frame.p_elo.to_numpy(float)),
        frame.player_form_diff.fillna(0).to_numpy(float),
        (frame.rating_coverage_a - frame.rating_coverage_b).to_numpy(float),
        (frame.prior_lineup_a.astype(int) - frame.prior_lineup_b.astype(int)).to_numpy(float),
        (frame.player_form_missing_a.astype(int) - frame.player_form_missing_b.astype(int)).to_numpy(float),
    ))
    if not np.isfinite(x).all():
        raise ValueError("nonfinite stack inputs")
    return x


def fit_frozen(frame: pd.DataFrame) -> dict:
    fit_rows = frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.isin((2023, 2024))
    if not fit_rows.any():
        raise ValueError("no decisive Tier-1 fit rows in 2023-24")
    x = design(frame.loc[fit_rows])
    y = frame.loc[fit_rows, "y"].to_numpy(float)
    scales = x[:, 1:].std(axis=0, ddof=0)
    scales[scales == 0] = 1.0
    x[:, 1:] /= scales
    weights = stack.fit(x, y, anchor=np.array([1., 0., 0., 0., 0.]))
    diagnostic = stack.fit(x[:, :2], y, anchor=np.array([1., 0.]))
    return {"weights": weights, "scales": scales, "diagnostic_weights": diagnostic}


def verdict(years: dict) -> str:
    tests = [years[year]["stack"] for year in (2025, 2026)]
    if all(row["t"] > 2 and row["ece"] <= row["elo_ece"] for row in tests):
        return "WIN"
    if all(row["t"] > 0 for row in tests):
        return "NOT PROVEN"
    return "REJECTED"


def evaluate(frame: pd.DataFrame) -> dict:
    frozen = fit_frozen(frame)
    result = {name: value.tolist() for name, value in frozen.items()}
    result["years"] = {}
    for year in YEARS:
        part = frame.loc[frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.eq(year)]
        if part.empty:
            raise ValueError(f"no decisive Tier-1 rows for {year}")
        x = design(part)
        x[:, 1:] /= frozen["scales"]
        y = part.y.to_numpy(float)
        elo = part.p_elo.to_numpy(float)
        forecasts = {
            "stack": stack.predict(x, frozen["weights"]),
            "Elo": elo,
            "Elo+form diagnostic": stack.predict(x[:, :2], frozen["diagnostic_weights"]),
        }
        result["years"][year] = {
            name: {**stack.metrics(y, p, elo), "reliability": [
                [bin_id, n, pred if n else None, actual if n else None]
                for bin_id, n, pred, actual in stack.reliability(y, p)]}
            for name, p in forecasts.items()
        }
    result["verdict"] = verdict(result["years"])
    return result


def main() -> None:
    print(json.dumps(evaluate(load()), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
