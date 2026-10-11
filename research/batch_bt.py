"""Shadow, walk-forward batch Bradley–Terry research experiment."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sys

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "src"))
from stack_ensemble import logits, metrics, reliability, sigmoid
from vct_quant import db
from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo

HALF_LIVES = (90, 180, 365, 730)
LAMBDAS = (0.1, 1.0, 10.0)
MODES = ("series", "maps")


@dataclass(frozen=True)
class Cell:
    half_life: int
    penalty: float
    mode: str


# Selected by the 2023–24 Tier-1 log-loss grid below.
FROZEN_CELL = Cell(365, 1.0, "maps")


def assigned_days(matches: pd.DataFrame) -> np.ndarray:
    dates = pd.to_datetime(matches.completed_at, utc=True).dt.floor("D")
    # The rare undated leading tail uses the first known day; all other nulls forward fill.
    dates = dates.ffill().bfill()
    if dates.isna().any():
        raise ValueError("no completion date in match sequence")
    return dates.to_numpy(dtype="datetime64[D]").astype(np.int64)


def observations(matches: pd.DataFrame, mode: str) -> tuple[np.ndarray, np.ndarray]:
    y = matches.score_a.to_numpy(float)
    successes = y.copy()
    trials = np.ones(len(y), dtype=float)
    if mode == "maps":
        a = matches.maps_a.to_numpy(float)
        b = matches.maps_b.to_numpy(float)
        valid = np.isfinite(a) & np.isfinite(b) & ((a + b) > 0)
        successes[valid] = a[valid]
        trials[valid] = a[valid] + b[valid]
    elif mode != "series":
        raise ValueError(mode)
    valid = np.isfinite(successes) & np.isfinite(trials) & (trials > 0)
    if mode == "series":
        valid &= np.isin(y, (0, 1))
    else:
        # A scoreless drawn series has no binary fallback.
        valid &= ~((trials == 1) & (y == .5))
    successes[~valid] = 0
    trials[~valid] = 0
    return successes, trials


def fit_strengths(a: np.ndarray, b: np.ndarray, success: np.ndarray,
                  trials: np.ndarray, age: np.ndarray, half_life: int,
                  penalty: float, nteams: int, start: np.ndarray | None = None) -> np.ndarray:
    """Weighted binomial MAP fit; gradient uses a sparse two-team incidence design."""
    if nteams == 0:
        return np.empty(0)
    weights = np.exp2(-np.asarray(age, float) / half_life)
    sw = weights * success
    tw = weights * trials
    initial = np.zeros(nteams) if start is None else np.asarray(start, float).copy()
    if not len(a) or not np.any(tw):
        return np.zeros(nteams)

    def objective(s: np.ndarray) -> tuple[float, np.ndarray]:
        z = s[a] - s[b]
        value = float(np.sum(tw * np.logaddexp(0, z) - sw * z) + penalty * np.dot(s, s))
        residual = tw * sigmoid(z) - sw
        grad = np.bincount(a, weights=residual, minlength=nteams) - np.bincount(
            b, weights=residual, minlength=nteams) + 2 * penalty * s
        return value, grad

    result = minimize(objective, initial, jac=True, method="L-BFGS-B",
                      options={"maxiter": 20, "ftol": 1e-7, "gtol": 1e-4})
    if not np.isfinite(result.x).all():
        raise RuntimeError("BT optimizer produced nonfinite strengths")
    return result.x


def replay(matches: pd.DataFrame, cell: Cell,
           forecast_years: tuple[int, ...] | None = None,
           forecast_tier: int | None = None) -> np.ndarray:
    """One probability per match in ID order, using no result from its bucket."""
    frame = matches.sort_values("match_id", kind="stable").reset_index(drop=True)
    day = assigned_days(frame)
    bucket = day // 3
    teams = pd.Index(pd.unique(pd.concat([frame.team_a, frame.team_b], ignore_index=True)))
    a = teams.get_indexer(frame.team_a)
    b = teams.get_indexer(frame.team_b)
    success, trials = observations(frame, cell.mode)
    out = np.full(len(frame), np.nan)
    years = pd.to_datetime(frame.completed_at, utc=True).dt.year.to_numpy()
    strengths = np.zeros(len(teams))
    prior_bucket = None
    for i in range(len(frame)):
        if (forecast_years is not None and years[i] not in forecast_years) or (
            forecast_tier is not None and frame.tier.iat[i] != forecast_tier
        ):
            continue
        if bucket[i] != prior_bucket:
            # Exclude all same-bucket observations and any earlier ID whose date
            # is not strictly before the first day of the current bucket.
            cutoff = int(bucket[i] * 3)
            eligible = np.flatnonzero((day[:i] < cutoff) & (trials[:i] > 0))
            start = strengths if prior_bucket is None or bucket[i] > prior_bucket else None
            strengths = fit_strengths(a[eligible], b[eligible], success[eligible],
                                      trials[eligible], cutoff - day[eligible],
                                      cell.half_life, cell.penalty, len(teams), start)
            seen = np.zeros(len(teams), dtype=bool)
            seen[a[eligible]] = True
            seen[b[eligible]] = True
            strengths[~seen] = 0
            prior_bucket = bucket[i]
        out[i] = sigmoid(strengths[a[i]] - strengths[b[i]])
    return out


def load_matches() -> pd.DataFrame:
    con = db.connect(read_only=True)
    try:
        matches = match_sequence(con).reset_index(drop=True)
    finally:
        con.close()
    rows = compute_elo(zip(matches.match_id, matches.team_a, matches.team_b,
                           margin_signal(matches)), k=elo_k(matches.tier))[0]
    matches["p_elo"] = [row["p_a_win"] for row in rows]
    matches["year"] = pd.to_datetime(matches.completed_at, utc=True).dt.year
    return matches


def frozen_probabilities(matches: pd.DataFrame | None = None) -> dict[int, float]:
    """Return the frozen-cell BT forecast keyed by match ID for later stack work."""
    frame = load_matches() if matches is None else matches.sort_values("match_id", kind="stable")
    return dict(zip(frame.match_id.astype(int), replay(frame, FROZEN_CELL), strict=True))


def select_and_score(matches: pd.DataFrame) -> tuple[Cell, list[dict], dict]:
    frame = matches.sort_values("match_id", kind="stable").reset_index(drop=True)
    y = frame.score_a.to_numpy(float)
    year = frame.year.to_numpy()
    elo = frame.p_elo.to_numpy(float)
    tune = (frame.tier.to_numpy() == 1) & np.isin(y, (0, 1)) & np.isin(year, (2023, 2024))
    grid = []
    best = None
    best_loss = np.inf
    for mode in MODES:
        for half_life in HALF_LIVES:
            for penalty in LAMBDAS:
                cell = Cell(half_life, penalty, mode)
                p = replay(frame, cell, (2023, 2024), 1)
                z = logits(p[tune])
                loss = float(np.mean(np.logaddexp(0, z) - y[tune] * z))
                grid.append({"cell": cell, "n": int(tune.sum()), "loss": loss})
                print(f"{mode:6} {half_life:3} {penalty:4g} {int(tune.sum()):5} {loss:.6f}", flush=True)
                if loss < best_loss:
                    best, best_loss = cell, loss
                    best_p = p
    best_p = replay(frame, best)
    result = {}
    for test_year in (2025, 2026):
        mask = (frame.tier.to_numpy() == 1) & np.isin(y, (0, 1)) & (year == test_year)
        result[test_year] = {}
        for label, p in (("BT", best_p), ("blend", sigmoid((logits(elo) + logits(best_p)) / 2))):
            row = metrics(y[mask], p[mask], elo[mask])
            row["reliability"] = reliability(y[mask], p[mask])
            row["elo_reliability"] = reliability(y[mask], elo[mask])
            result[test_year][label] = row
            print(test_year, label, row, flush=True)
    print("chosen", best, "grid_edge", best.half_life in (HALF_LIVES[0], HALF_LIVES[-1]) or best.penalty in (LAMBDAS[0], LAMBDAS[-1]), flush=True)
    for label in ("BT", "blend"):
        rows = [result[year][label] for year in (2025, 2026)]
        verdict = "WIN" if all(r["t"] > 2 and r["ece"] <= r["elo_ece"] for r in rows) else "NOT PROVEN" if all(r["t"] > 0 for r in rows) else "REJECTED"
        print("verdict", label, verdict, flush=True)
    return best, grid, result


def main() -> None:
    print("mode half_life lambda n tuning_log_loss", flush=True)
    select_and_score(load_matches())


if __name__ == "__main__":
    main()
