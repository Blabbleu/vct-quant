"""Event-cluster uncertainty audit for the frozen four-input fast-slow stack."""
from __future__ import annotations

import json
from contextlib import redirect_stdout
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "src"))
import stack_fastslow as frozen
import stack_ensemble as stack
from vct_quant import db

SEED = 20261013
RESAMPLES = 10_000


def align_events(frame: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Join exactly one event record to every component match, in component order."""
    for source in (frame, events):
        if source.match_id.isna().any() or source.match_id.duplicated().any():
            raise ValueError("null or duplicate match_id")
    if set(frame.match_id) != set(events.match_id):
        raise ValueError("missing or extra match_id in event alignment")
    return frame.merge(events[["match_id", "event_id"]], on="match_id",
                       how="left", validate="one_to_one", sort=False)


def load() -> pd.DataFrame:
    # The imported loader prints map coverage; reserve stdout for result JSON.
    with redirect_stdout(sys.stderr):
        frame = frozen.load()
    con = db.connect(read_only=True)
    try:
        # The canonical match table also contains rows outside the rating sequence.
        all_events = con.execute("SELECT match_id, event_id FROM match").df()
    finally:
        con.close()
    events = all_events.loc[all_events.match_id.isin(frame.match_id)]
    return align_events(frame, events)


def cluster_keys(part: pd.DataFrame) -> list[str]:
    """Give every unknown event a distinct, stable singleton identity."""
    return [f"match:{int(mid)}" if pd.isna(eid) else f"event:{int(eid)}"
            for mid, eid in zip(part.match_id, part.event_id, strict=True)]


def cluster_bootstrap(delta: np.ndarray, keys: list[str], *,
                      seed: int = SEED, resamples: int = RESAMPLES) -> tuple[float, float]:
    """Percentile interval for fixture-weighted mean, sampling complete events."""
    delta = np.asarray(delta, dtype=float)
    if not len(delta) or len(delta) != len(keys) or not np.isfinite(delta).all():
        raise ValueError("invalid paired losses or cluster keys")
    if resamples < 1:
        raise ValueError("resamples must be positive")
    groups: dict[str, list[float]] = {}
    for key, value in zip(keys, delta, strict=True):
        groups.setdefault(key, []).append(float(value))
    totals = np.array([sum(v) for v in groups.values()])
    sizes = np.array([len(v) for v in groups.values()])
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    # Chunk draws to avoid a large allocation if the number of events grows.
    for start in range(0, resamples, 1000):
        stop = min(start + 1000, resamples)
        draw = rng.integers(len(groups), size=(stop-start, len(groups)))
        means[start:stop] = totals[draw].sum(axis=1) / sizes[draw].sum(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def leave_one_event_out(delta: np.ndarray, keys: list[str]) -> dict:
    groups: dict[str, list[int]] = {}
    for i, key in enumerate(keys):
        groups.setdefault(key, []).append(i)
    if len(groups) < 2:
        raise ValueError("leave-one-event-out needs at least two events")
    total = float(np.sum(delta))
    candidates = ((float((total - np.sum(delta[indices])) / (len(delta) - len(indices))), key)
                  for key, indices in groups.items())
    advantage, key = min(candidates, key=lambda item: (item[0], item[1]))
    return {"advantage": advantage, "removed_event": key}


def _loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    z = stack.logits(p)
    return np.logaddexp(0, z) - y*z


def _reliability(y: np.ndarray, p: np.ndarray) -> list[list]:
    return [[i, n, pred if n else None, actual if n else None]
            for i, n, pred, actual in stack.reliability(y, p)]


def evaluate(frame: pd.DataFrame) -> dict:
    # This call sees the full frame; the imported fitting rule selects 2023-24 only.
    _, weights = frozen.fit_frozen(frame)
    result = {"weights_four": weights.tolist(), "seed": SEED,
              "resamples": RESAMPLES, "years": {}}
    for year in (2025, 2026):
        part = frame.loc[frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.eq(year)]
        if part.empty:
            raise ValueError(f"no decisive Tier-1 rows for {year}")
        y = part.y.to_numpy(float)
        elo = part.p_elo.to_numpy(float)
        x = stack.logits(part[["p_elo", "p_rs", "p_ls", "p_fs"]].to_numpy(float))
        prediction = stack.predict(x, weights)
        delta = _loss(y, elo) - _loss(y, prediction)
        keys = cluster_keys(part)
        counts = pd.Series(keys).value_counts()
        metrics = stack.metrics(y, prediction, elo)
        result["years"][year] = {
            "n": len(part), "events": len(counts),
            "null_events": int(part.event_id.isna().sum()),
            "largest_event_fixtures": int(counts.max()),
            "largest_event_share": float(counts.max()/len(part)),
            "advantage": float(delta.mean()), "paired_t": metrics["t"],
            "cluster_interval": cluster_bootstrap(delta, keys),
            "leave_one_out_min": leave_one_event_out(delta, keys),
            "elo": {"loss": metrics["elo_loss"], "brier": metrics["elo_brier"],
                    "accuracy": metrics["elo_accuracy"], "ece": metrics["elo_ece"],
                    "reliability": _reliability(y, elo)},
            "stack": {"loss": metrics["loss"], "brier": metrics["brier"],
                      "accuracy": metrics["accuracy"], "ece": metrics["ece"],
                      "reliability": _reliability(y, prediction)},
        }
    rows = list(result["years"].values())
    passes = all(r["cluster_interval"][0] > 0 and r["stack"]["ece"] <= r["elo"]["ece"]
                 for r in rows)
    result["verdict"] = "WIN" if passes else "TIE" if all(r["advantage"] > 0 for r in rows) else "LOSS"
    result["promotion"] = False  # Previously consulted test years are not independent evidence.
    return result


def main() -> None:
    print(json.dumps(evaluate(load()), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
