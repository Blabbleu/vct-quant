"""Frozen batch BT as a fourth input to the retrospective Tier-1 stack."""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import batch_bt
import lineup_skill
import stack_ensemble as stack

INPUTS = ("p_elo", "p_rs", "p_ls", "p_bt")


def align_bt(stack_frame: pd.DataFrame, bt_matches: pd.DataFrame,
             bt_probabilities: dict[int, float], stack_sides: pd.DataFrame) -> pd.DataFrame:
    """Require full, uniquely keyed, same-side BT coverage before any filtering."""
    for name, frame in (("stack", stack_frame), ("BT", bt_matches), ("sides", stack_sides)):
        if frame.match_id.isna().any() or frame.match_id.duplicated().any():
            raise ValueError(f"{name} has null or duplicate match IDs")
    ids = set(stack_frame.match_id.astype(int))
    if (ids != set(bt_matches.match_id.astype(int)) or
            ids != set(stack_sides.match_id.astype(int)) or
            ids != set(bt_probabilities)):
        raise ValueError("missing or extra BT match IDs; exact one-to-one coverage required")
    source = bt_matches[["match_id", "team_a", "team_b", "score_a", "p_elo"]].rename(
        columns={"score_a": "y_bt", "p_elo": "p_elo_bt"})
    out = stack_frame.merge(source, on="match_id", validate="one_to_one")
    out = out.merge(stack_sides[["match_id", "team_a", "team_b", "y"]],
                    on="match_id", validate="one_to_one", suffixes=("", "_side"))
    if not (out.team_a.eq(out.team_a_side).all() and out.team_b.eq(out.team_b_side).all()):
        raise ValueError("BT and stack team-side orientation disagree")
    if not (np.array_equal(out.y.to_numpy(float), out.y_bt.to_numpy(float), equal_nan=True) and
            np.array_equal(out.y.to_numpy(float), out.y_side.to_numpy(float), equal_nan=True)):
        raise ValueError("BT and stack labels disagree")
    if not np.allclose(out.p_elo, out.p_elo_bt, rtol=0, atol=1e-12, equal_nan=False):
        raise ValueError("original production Elo probabilities disagree")
    out["p_bt"] = out.match_id.map(bt_probabilities)
    probabilities = out[list(INPUTS)].to_numpy(float)
    if not np.isfinite(probabilities).all() or np.any((probabilities <= 0) | (probabilities >= 1)):
        raise ValueError("component pre-match probabilities must be finite and inside (0, 1)")
    return out.drop(columns=["team_a", "team_b", "team_a_side", "team_b_side",
                             "y_bt", "y_side", "p_elo_bt"])


def load_components() -> pd.DataFrame:
    prior = stack.load_components()
    bt_matches = batch_bt.load_matches()
    sides_data = lineup_skill.load_data()
    sides = pd.DataFrame({"match_id": sides_data["match_id"],
                          "team_a": sides_data["team_a"], "team_b": sides_data["team_b"],
                          "y": sides_data["y"]})
    if bt_matches.match_id.isna().any() or bt_matches.match_id.duplicated().any():
        raise ValueError("BT source has null or duplicate match IDs")
    probabilities = batch_bt.frozen_probabilities(bt_matches)
    return align_bt(prior, bt_matches, probabilities, sides)


def fit_frozen(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    train = frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.isin((2023, 2024))
    x = stack.logits(frame.loc[train, list(INPUTS)].to_numpy(float))
    y = frame.loc[train, "y"].to_numpy(float)
    return (stack.fit(x[:, :3], y),
            stack.fit(x, y, anchor=np.array([1., 0., 0., 0.])))


def evaluate(frame: pd.DataFrame) -> tuple[dict, dict, str]:
    prior_weights, weights = fit_frozen(frame)
    print("fit years 2023-24; weights [Elo, round-share, lineup, BT]")
    print("prior", np.array2string(prior_weights, precision=8))
    print("four", np.array2string(weights, precision=8))
    rows = {}
    for year in (2025, 2026):
        test = frame.loc[frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.eq(year)]
        if test.empty:
            raise ValueError(f"no binary Tier-1 rows for {year}")
        y = test.y.to_numpy(float)
        p_elo = test.p_elo.to_numpy(float)
        x = stack.logits(test[list(INPUTS)].to_numpy(float))
        predictions = {"Elo": p_elo, "prior stack": stack.predict(x[:, :3], prior_weights),
                       "four-input stack": stack.predict(x, weights)}
        for model, p in predictions.items():
            result = stack.metrics(y, p, p_elo)
            rows[(year, model)] = result
            print(year, model, "n", result["n"], "log_loss", f'{result["loss"]:.6f}',
                  "brier", f'{result["brier"]:.6f}', "accuracy", f'{result["accuracy"]:.6f}',
                  "paired_t_vs_Elo", f'{result["t"]:+.3f}', "ece", f'{result["ece"]:.6f}')
            print(year, model, "ten-bin calibration (bin,n,mean_p,win_rate):",
                  stack.reliability(y, p))
    tests = [rows[(year, "four-input stack")] for year in (2025, 2026)]
    verdict = ("WIN" if all(r["t"] > 2 and r["ece"] <= r["elo_ece"] for r in tests)
               else "NOT PROVEN" if all(r["t"] > 0 for r in tests) else "REJECTED")
    print("preregistered verdict:", verdict)
    return rows, {"prior": prior_weights, "four": weights}, verdict


def main() -> None:
    evaluate(load_components())


if __name__ == "__main__":
    main()
