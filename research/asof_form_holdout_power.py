"""Reproducible resampling study for the frozen as-of form holdout design."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from research import asof_form_holdout as holdout

LOOKS = (150, 300, 450, 600)
SEED = 20261015
SIMULATIONS = 50_000


def paired_differences(frame, frozen: dict) -> dict[int, np.ndarray]:
    """Previously consulted 2025/26 Tier-1 log loss differences, Elo minus frozen model."""
    weights = np.asarray(frozen["weights"], float)
    scale = float(frozen["form_difference_scale"])
    result = {}
    for year in (2025, 2026):
        part = frame.loc[frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.eq(year)]
        y = part.y.to_numpy(float)
        elo = part.p_elo.to_numpy(float)
        x = np.column_stack((holdout.stack.logits(elo),
                             part.player_form_diff.fillna(0).to_numpy(float) / scale))
        candidate = holdout.stack.predict(x, weights)
        def loss(p):
            z = holdout.stack.logits(p)
            return np.logaddexp(0, z) - y * z
        result[year] = loss(elo) - loss(candidate)
    return result


def summary(values: np.ndarray) -> dict:
    return {"n": len(values), "mean": float(values.mean()),
            "sd": float(values.std(ddof=1)),
            "standardized_effect": float(values.mean() / values.std(ddof=1))}


def t_stat(samples: np.ndarray) -> np.ndarray:
    """Paired t for each simulated sequence (one sequence per row)."""
    mean = samples.mean(axis=1)
    sd = samples.std(axis=1, ddof=1)
    return np.divide(mean * math.sqrt(samples.shape[1]), sd,
                     out=np.zeros_like(mean), where=sd > 0)


def simulate_t(values: np.ndarray, n: int, *, simulations: int = SIMULATIONS,
               seed: int = SEED, shift: float = 0.0) -> np.ndarray:
    """IID bootstrap of the empirical differences, shifted by a fixed mean discount."""
    rng = np.random.default_rng(seed)
    out = np.empty(simulations)
    for start in range(0, simulations, 1000):
        count = min(1000, simulations - start)
        sample = values[rng.integers(len(values), size=(count, n))] + shift
        out[start:start + count] = t_stat(sample)
    return out


def sequential_max(values: np.ndarray, *, simulations: int = SIMULATIONS,
                   seed: int = SEED, shift: float = 0.0) -> np.ndarray:
    """Maximum O'Brien-Fleming scaled t over the four cumulative looks."""
    rng = np.random.default_rng(seed)
    out = np.empty(simulations)
    for start in range(0, simulations, 1000):
        count = min(1000, simulations - start)
        sample = values[rng.integers(len(values), size=(count, LOOKS[-1]))] + shift
        maxima = np.full(count, -np.inf)
        active = np.ones(count, dtype=bool)
        for k, n in enumerate(LOOKS, start=1):
            t = t_stat(sample[:, :n])
            maxima = np.maximum(maxima, np.where(active, t / math.sqrt(4 / k), -np.inf))
            if k >= 2:
                active &= t > 0
        out[start:start + count] = maxima
    return out


def boundaries(constant: float) -> list[float]:
    return [constant * math.sqrt(4 / k) for k in range(1, 5)]


def calibrate(null_max: np.ndarray, target: float = 0.023) -> float:
    """Choose a conservative empirical cut, strictly exceeding the tail threshold."""
    ordered = np.sort(null_max)
    allowed = math.floor(target * len(ordered))
    return float(np.nextafter(ordered[-allowed - 1], np.inf))


def rows_for_power(values: np.ndarray, shift: float, *, target: float = 0.8) -> tuple[int, float]:
    """Smallest row count with >= target bootstrap power on a fixed-seed grid search."""
    def power(n):
        return float(np.mean(simulate_t(values, n, shift=shift, seed=SEED + n) > 2))
    low, high = 1, 150
    while power(high) < target:
        low, high = high, high * 2
        if high > 10000:
            raise RuntimeError("80% power requires more than 10000 rows")
    while high - low > 1:
        middle = (high + low) // 2
        if power(middle) >= target:
            high = middle
        else:
            low = middle
    return high, power(high)


def study(frame, frozen: dict) -> dict:
    by_year = paired_differences(frame, frozen)
    all_values = np.concatenate([by_year[2025], by_year[2026]])
    mean = all_values.mean()
    null = all_values - mean
    single = {name: float(np.mean(simulate_t(all_values, 150, shift=shift) > 2))
              for name, shift in (("full", 0.0), ("half", -mean / 2))}
    single["zero"] = float(np.mean(simulate_t(null, 150) > 2))
    null_max = sequential_max(null)
    constant = calibrate(null_max, target=min(single["zero"], 0.023))
    rate = float(np.mean(sequential_max(null, seed=SEED + 1) > constant))
    power = {name: float(np.mean(sequential_max(all_values, shift=shift,
                                                seed=SEED + 1) > constant))
             for name, shift in (("full", 0.0), ("half", -mean / 2))}
    return {"seed": SEED, "simulations": SIMULATIONS,
            "previously_consulted": {str(y): summary(v) for y, v in by_year.items()},
            "pooled": summary(all_values), "single_150": single,
            "rows_for_80_percent": {name: rows_for_power(all_values, shift)[0]
                                    for name, shift in (("full", 0.0), ("half", -mean / 2))},
            "sequential": {"looks": list(LOOKS), "constant": constant,
                           "boundaries": boundaries(constant),
                           "zero_false_win_rate_ignoring_ece": rate,
                           "power_ignoring_ece": power}}


def main() -> None:
    frozen = json.loads(holdout.FROZEN_PATH.read_text())
    frame = holdout.form_stack.load()
    print(json.dumps(study(frame, frozen), indent=2))


if __name__ == "__main__":
    main()
