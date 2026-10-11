"""Shadow state-space Bradley–Terry experiment; no production integration."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "src"))
import round_share_series as rs  # noqa: E402
import stack_ensemble as stack  # noqa: E402
from vct_quant import db  # noqa: E402
from vct_quant.features.build import elo_k, margin_signal, match_sequence  # noqa: E402
from vct_quant.features.ratings import compute_elo  # noqa: E402

GRID = tuple(product((0.0005, 0.001, 0.002, 0.004), (0.5, 1.0), (0.0, 0.1, 0.3)))


@dataclass(frozen=True)
class Observation:
    match_id: int
    team_a: str
    team_b: str
    day: float | None
    year: int | None
    best_of: int | None
    tier: int
    outcome: float
    maps: tuple[int, ...]
    p_elo: float = math.nan


@dataclass
class Team:
    mu: float
    variance: float
    day: float | None
    year: int | None


def sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def advance(state: dict[str, Team], key: str, day: float | None, year: int | None,
            q: float, s0: float, v_season: float) -> Team:
    if key not in state:
        state[key] = Team(0.0, s0 * s0, day, year)
        return state[key]
    team = state[key]
    if day is not None and team.day is not None:
        team.variance += q * max(0.0, day - team.day)
    if year is not None and team.year is not None:
        team.variance += v_season * max(0, year - team.year)
    if day is not None:
        team.day = day
    if year is not None:
        team.year = year
    return team


def map_probability(a: Team, b: Team, scale: float = 1.0) -> float:
    corrected = scale / math.sqrt(1 + math.pi * scale * scale * (a.variance + b.variance) / 8)
    return sigmoid(corrected * (a.mu - b.mu))


def ekf_update(a: Team, b: Team, winner_a: int, scale: float = 1.0) -> None:
    """One Bernoulli EKF moment step using the corrected predictive link."""
    va, vb = a.variance, b.variance
    effective_scale = scale / math.sqrt(1 + math.pi * scale * scale * (va + vb) / 8)
    p = sigmoid(effective_scale * (a.mu - b.mu))
    slope = effective_scale * p * (1 - p)
    noise = max(p * (1 - p), 1e-12)
    innovation = noise + slope * slope * (va + vb)
    gain_a, gain_b = va * slope / innovation, -vb * slope / innovation
    residual = winner_a - p
    a.mu += gain_a * residual
    b.mu += gain_b * residual
    a.variance = max(1e-12, va - gain_a * slope * va)
    b.variance = max(1e-12, vb + gain_b * slope * vb)


def series_forecast(p_map: float, best_of: int | None) -> float:
    return rs.series_probability(p_map, best_of) if best_of in (1, 3, 5) else p_map


def replay(observations: list[Observation], cell: tuple[float, float, float],
           *, map_training: bool = False) -> tuple[np.ndarray, float, int]:
    q, s0, v_season = cell
    state: dict[str, Team] = {}
    forecasts = np.empty(len(observations))
    loss_sum = 0.0
    n_maps = 0
    for i, match in enumerate(observations):
        a = advance(state, match.team_a, match.day, match.year, q, s0, v_season)
        b = advance(state, match.team_b, match.day, match.year, q, s0, v_season)
        forecasts[i] = series_forecast(map_probability(a, b), match.best_of)
        # The series forecast is fixed before any observation from this match.
        for winner in match.maps:
            p = map_probability(a, b)
            if map_training and match.year in (2023, 2024):
                loss_sum -= math.log(max(p if winner else 1 - p, 1e-12))
                n_maps += 1
            ekf_update(a, b, winner)
        if not match.maps and match.outcome in (0.0, 1.0):
            ekf_update(a, b, int(match.outcome))
    return forecasts, loss_sum, n_maps


def load_data() -> list[Observation]:
    con = db.connect(read_only=True)
    try:
        matches = match_sequence(con).reset_index(drop=True)
        formats = dict(con.execute("SELECT match_id, best_of FROM match").fetchall())
        expected = {int(r.match_id): (r.team_a, r.team_b) for r in matches.itertuples(index=False)}
        maps, availability = rs.load_maps(con, expected)
    finally:
        con.close()
    print("Map availability:", availability, flush=True)
    elo_rows = compute_elo(zip(matches.match_id, matches.team_a, matches.team_b,
                               margin_signal(matches)), k=elo_k(matches.tier))[0]
    p_elo = {int(r["match_id"]): float(r["p_a_win"]) for r in elo_rows}
    dates = pd.to_datetime(matches.completed_at, utc=True, errors="coerce")
    result = []
    for row, date in zip(matches.itertuples(index=False), dates):
        day = None if pd.isna(date) else date.timestamp() / 86400
        year = int(date.year) if not pd.isna(date) else (int(row.year) if not pd.isna(row.year) else None)
        decisive = tuple(int(a > b) for a, b in maps.get(int(row.match_id), ()) if a != b)
        fmt = formats.get(int(row.match_id))
        best_of = int(fmt) if fmt is not None and not pd.isna(fmt) else None
        result.append(Observation(int(row.match_id), row.team_a, row.team_b, day, year,
                                  best_of, int(row.tier), float(row.score_a), decisive,
                                  p_elo[int(row.match_id)]))
    return result


def score_year(observations: list[Observation], forecasts: np.ndarray, year: int,
               weights: np.ndarray) -> tuple[dict[str, dict], np.ndarray, np.ndarray, np.ndarray]:
    indices = [i for i, o in enumerate(observations)
               if o.tier == 1 and o.year == year and o.outcome in (0.0, 1.0)]
    y = np.array([observations[i].outcome for i in indices])
    elo = np.array([observations[i].p_elo for i in indices])
    primary = forecasts[indices]
    blend = stack.sigmoid(0.5 * (stack.logits(elo) + stack.logits(primary)))
    fitted = stack.predict(np.column_stack((stack.logits(elo), stack.logits(primary))), weights)
    rows = {name: stack.metrics(y, p, elo) for name, p in
            (("Elo", elo), ("state-space", primary), ("blend", blend), ("stack", fitted))}
    return rows, y, primary, elo


def run() -> tuple[list[tuple[tuple[float, float, float], float]], tuple, dict, np.ndarray]:
    observations = load_data()
    tuning = []
    print("q s0 v_season train_map_n train_map_log_loss", flush=True)
    for cell in GRID:
        _, loss_sum, n_maps = replay(observations, cell, map_training=True)
        if not n_maps:
            raise RuntimeError("No 2023-24 valid map observations")
        loss = loss_sum / n_maps
        tuning.append((cell, loss))
        print(f"{cell[0]:.4f} {cell[1]:.1f} {cell[2]:.1f} {n_maps} {loss:.6f}", flush=True)
    chosen, best_loss = min(tuning, key=lambda item: item[1])
    edges = tuple(chosen[i] in (min(c[i] for c in GRID), max(c[i] for c in GRID)) for i in range(3))
    print(f"Chosen: q={chosen[0]:.4f} s0={chosen[1]:.1f} v_season={chosen[2]:.1f} "
          f"map_loss={best_loss:.6f}; grid edges q/s0/v_season={edges}", flush=True)
    forecasts, _, _ = replay(observations, chosen)
    train = [i for i, o in enumerate(observations)
             if o.tier == 1 and o.year in (2023, 2024) and o.outcome in (0.0, 1.0)]
    x = np.column_stack((stack.logits(np.array([observations[i].p_elo for i in train])),
                         stack.logits(forecasts[train])))
    y = np.array([observations[i].outcome for i in train])
    weights = stack.fit(x, y, anchor=np.array([1.0, 0.0]))
    print("Frozen stack weights (Elo, state-space):", np.array2string(weights, precision=6), flush=True)
    results = {}
    print("year model n loss elo_loss brier elo_brier accuracy elo_accuracy paired_t ece elo_ece", flush=True)
    for year in (2025, 2026):
        rows, labels, primary, elo = score_year(observations, forecasts, year, weights)
        results[year] = rows
        for name, metrics in rows.items():
            print(year, name, metrics["n"], *(f"{metrics[k]:.6f}" for k in
                  ("loss", "elo_loss", "brier", "elo_brier", "accuracy",
                   "elo_accuracy", "t", "ece", "elo_ece")), flush=True)
        for name, probabilities in (("state-space", primary), ("Elo", elo)):
            print(year, name, "reliability (bin,n,p,observed):", stack.reliability(labels, probabilities), flush=True)
    primary_rows = [results[year]["state-space"] for year in (2025, 2026)]
    verdict = ("WIN" if all(r["t"] > 2 and r["ece"] <= r["elo_ece"] for r in primary_rows)
               else "NOT PROVEN" if all(r["t"] > 0 for r in primary_rows) else "REJECTED")
    print("Verdict:", verdict, flush=True)
    return tuning, chosen, results, weights


if __name__ == "__main__":
    run()
