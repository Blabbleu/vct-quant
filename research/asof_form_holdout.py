"""Offline scorer for the frozen, post-2026-10-15 Elo plus as-of form holdout."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "src"))
import asof_form_stack as form_stack
import stack_ensemble as stack
from vct_quant import db

FROZEN_PATH = Path(__file__).with_name("asof_form_holdout_frozen.json")
DESIGN_PATH = Path(__file__).with_name("asof_form_holdout_design.json")
FREEZE_TIME = "2026-10-15T07:00:00Z"
DOCUMENTED_WEIGHTS = np.array([0.87296870, 0.07737623])
DOCUMENTED_SCALE = 0.09254274


def freeze(frame: pd.DataFrame, path: Path = FROZEN_PATH) -> dict:
    """Make the one-time artifact, refusing drift from the published refit."""
    fit = form_stack.fit_frozen(frame)
    weights = np.asarray(fit["diagnostic_weights"], dtype=float)
    scale = float(fit["scales"][0])
    if (weights.shape != (2,) or not np.isfinite(weights).all()
            or not np.all(np.abs(weights - DOCUMENTED_WEIGHTS) <= 1e-6)
            or not np.isfinite(scale) or abs(scale - DOCUMENTED_SCALE) > 1e-6):
        raise ValueError("diagnostic weights or form scale drifted from documented freeze")
    fit_rows = frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.isin((2023, 2024))
    artifact = {
        "freeze_time": FREEZE_TIME,
        "fit_years": [2023, 2024],
        "fit_row_count": int(fit_rows.sum()),
        "git_commit": "2d5fbea",
        "weights": weights.tolist(),
        "form_difference_scale": scale,
    }
    path.write_text(json.dumps(artifact, indent=2) + "\n")
    return artifact


def _events(frame: pd.DataFrame) -> pd.DataFrame:
    if "event_id" in frame:
        return frame
    con = db.connect(read_only=True)
    try:
        ids = con.execute("SELECT match_id, event_id FROM match").df()
    finally:
        con.close()
    return frame.merge(ids, on="match_id", how="left", validate="one_to_one", sort=False)


def _score(part: pd.DataFrame, weights: np.ndarray, scale: float) -> dict | None:
    if part.empty:
        return None
    y = part.y.to_numpy(float)
    elo = part.p_elo.to_numpy(float)
    form = part.player_form_diff.fillna(0).to_numpy(float)
    x = np.column_stack((stack.logits(elo), form / scale))
    candidate = stack.predict(x, weights)
    scored = stack.metrics(y, candidate, elo)
    scored = {key: (None if isinstance(value, (float, np.floating)) and not np.isfinite(value)
                    else value) for key, value in scored.items()}
    scored["distinct_events"] = int(part.event_id.nunique())
    scored["candidate_reliability"] = [
        [bin_id, n, p if n else None, actual if n else None]
        for bin_id, n, p, actual in stack.reliability(y, candidate)]
    scored["elo_reliability"] = [
        [bin_id, n, p if n else None, actual if n else None]
        for bin_id, n, p, actual in stack.reliability(y, elo)]
    return scored


def verdict(primary: dict | None, total: int) -> str:
    if total < 150:
        return "PENDING"
    assert primary is not None
    if primary["t"] is not None and primary["t"] > 2 and primary["ece"] <= primary["elo_ece"]:
        return "WIN"
    return "NOT PROVEN" if primary["t"] is None or primary["t"] > 0 else "REJECTED"


def sequential_verdict(part: pd.DataFrame, weights: np.ndarray, scale: float,
                       design: dict) -> tuple[int | None, dict | None, str]:
    looks = design["looks"]
    limits = design["boundaries"]
    if looks != [150, 300, 450, 600] or len(limits) != 4:
        raise ValueError("invalid registered holdout looks")
    reached = None
    current = None
    for index, (look, boundary) in enumerate(zip(looks, limits)):
        if len(part) < look:
            break
        reached = look
        current = _score(part.iloc[:look], weights, scale)
        t = current["t"]
        if t is not None and t > boundary and current["ece"] <= current["elo_ece"]:
            return reached, current, "WIN"
        if index >= 1 and t is not None and t <= 0:
            return reached, current, "REJECTED"
    if reached == looks[-1]:
        return reached, current, "NOT PROVEN"
    return reached, current, "PENDING"


def evaluate(frame: pd.DataFrame, frozen: dict, design: dict | None = None) -> dict:
    """Score only post-freeze decisive Tier-1 rows; no fitting happens here."""
    cutoff = pd.Timestamp(frozen["freeze_time"])
    completed = pd.to_datetime(frame.completed_at, utc=True)
    eligible = frame.tier.eq(1) & frame.y.isin((0, 1)) & completed.gt(cutoff)
    part = frame.loc[eligible].copy()
    part["_completed_utc"] = completed.loc[eligible]
    part = part.sort_values(["_completed_utc", "match_id"], kind="stable")
    if not part.empty:
        part = _events(part)
        if part.event_id.isna().any():
            raise ValueError("eligible match has no event_id")
    weights = np.asarray(frozen["weights"], dtype=float)
    scale = float(frozen["form_difference_scale"])
    if weights.shape != (2,) or not np.isfinite(weights).all() or not np.isfinite(scale) or scale <= 0:
        raise ValueError("invalid frozen parameters")
    first = part.iloc[:150]
    later = part.iloc[150:]
    primary = _score(first, weights, scale)
    if design is None:
        design = json.loads(DESIGN_PATH.read_text())
    look_reached, look_stats, decision = sequential_verdict(part, weights, scale, design)
    return {
        "eligible_rows": len(part),
        "primary": primary,
        "later_rows": _score(later, weights, scale),
        "look_reached": look_reached,
        "look_stats": look_stats,
        "verdict": decision,
    }


def main() -> None:
    frozen = json.loads(FROZEN_PATH.read_text())
    print(json.dumps(evaluate(form_stack.load(), frozen), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
