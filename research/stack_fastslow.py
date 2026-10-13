"""Frozen fast/slow Elo as a fourth input to the Tier-1 stack."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "src"))
import stack_ensemble as stack
from vct_quant import db
from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo


def replay(matches: pd.DataFrame) -> pd.DataFrame:
    """Return pre-match fast/slow and baseline forecasts in team-A orientation."""
    if matches.match_id.isna().any() or matches.match_id.duplicated().any():
        raise ValueError("null or duplicate match_id in match sequence")
    if not matches.match_id.is_monotonic_increasing:
        raise ValueError("match sequence must be in match-ID order")
    signal = margin_signal(matches)
    if not np.isfinite(signal.to_numpy(float)).all():
        raise ValueError("nonfinite match signal")
    games = list(zip(matches.match_id, matches.team_a, matches.team_b, signal))
    forecasts = {}
    for name, k in (("p_elo_check", elo_k(matches.tier)),
                    ("p_16", matches.tier.map({1: 16.0}).fillna(0.0)),
                    ("p_256", matches.tier.map({1: 256.0}).fillna(0.0))):
        rows, _ = compute_elo(games, k=k)
        forecasts[name] = np.array([row["p_a_win"] for row in rows], dtype=float)
        if any(row["team_a"] != a or row["team_b"] != b
               for row, a, b in zip(rows, matches.team_a, matches.team_b)):
            raise ValueError("replay side orientation disagrees with match sequence")
    forecasts["p_fs"] = stack.sigmoid(
        .7 * stack.logits(forecasts["p_16"]) + .3 * stack.logits(forecasts["p_256"]))
    return pd.DataFrame({"match_id": matches.match_id.to_numpy(),
                         "y_check": matches.score_a.to_numpy(), **forecasts})


def align(components: pd.DataFrame, shadow: pd.DataFrame) -> pd.DataFrame:
    """Require one-to-one coverage and Elo/outcome parity before any filtering."""
    for frame in (components, shadow):
        if frame.match_id.isna().any() or frame.match_id.duplicated().any():
            raise ValueError("null or duplicate match_id")
    if set(components.match_id) != set(shadow.match_id):
        raise ValueError("missing or extra match_id rows")
    out = components.merge(shadow, on="match_id", validate="one_to_one")
    if not np.array_equal(out.y.to_numpy(float), out.y_check.to_numpy(float), equal_nan=True):
        raise ValueError("team-A outcomes or side orientation disagree")
    if not np.allclose(out.p_elo.to_numpy(float), out.p_elo_check.to_numpy(float),
                       rtol=0, atol=1e-12, equal_nan=False):
        raise ValueError("production Elo baseline or side orientation disagrees")
    probabilities = out[["p_elo", "p_rs", "p_ls", "p_fs", "p_16", "p_256"]].to_numpy(float)
    if not np.isfinite(probabilities).all() or np.any((probabilities <= 0) | (probabilities >= 1)):
        raise ValueError("component probabilities must be finite and within (0, 1)")
    return out.drop(columns=["y_check", "p_elo_check"])


def fit_frozen(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    train = frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.isin((2023, 2024))
    if not train.any():
        raise ValueError("no 2023-24 decisive Tier-1 training matches")
    y = frame.loc[train, "y"].to_numpy(float)
    x = stack.logits(frame.loc[train, ["p_elo", "p_rs", "p_ls", "p_fs"]].to_numpy(float))
    return (stack.fit(x[:, :3], y), stack.fit(x, y, anchor=np.array([1., 0., 0., 0.])))


def evaluate(frame: pd.DataFrame) -> dict:
    three, four = fit_frozen(frame)
    result = {"weights_three": three.tolist(), "weights_four": four.tolist(), "years": {}}
    for year in (2025, 2026):
        eligible = frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.eq(year)
        part = frame.loc[eligible]
        if part.empty:
            raise ValueError(f"no decisive Tier-1 rows for {year}")
        y = part.y.to_numpy(float)
        elo = part.p_elo.to_numpy(float)
        x = stack.logits(part[["p_elo", "p_rs", "p_ls", "p_fs"]].to_numpy(float))
        predictions = {"Elo": elo, "fast/slow": part.p_fs.to_numpy(float),
                       "three-input": stack.predict(x[:, :3], three),
                       "four-input": stack.predict(x, four)}
        result["years"][year] = {
            name: {**stack.metrics(y, p, elo), "calibration": [
                [bin_id, n, pred if n else None, actual if n else None]
                for bin_id, n, pred, actual in stack.reliability(y, p)]}
            for name, p in predictions.items()
        }
    tests = [result["years"][year]["four-input"] for year in (2025, 2026)]
    result["verdict"] = ("WIN" if all(r["t"] > 2 and r["ece"] <= r["elo_ece"] for r in tests)
                         else "NOT PROVEN" if all(r["t"] > 0 for r in tests) else "REJECTED")
    return result


def load() -> pd.DataFrame:
    components = stack.load_components()
    con = db.connect(read_only=True)
    try:
        matches = match_sequence(con).reset_index(drop=True)
    finally:
        con.close()
    return align(components, replay(matches))


def main() -> None:
    print(json.dumps(evaluate(load()), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
