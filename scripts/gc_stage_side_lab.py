"""Retrospective GC stage-specific side-h advantage lab.

Protocol frozen in docs/gc-stage-side-lab.md before test scoring. Read-only;
never changes production Elo or the live prediction log.
"""
from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd

K = 192.0
H_GRID = tuple(float(x) for x in range(0, 61, 10))
REFERENCE = (30.0, 30.0, 30.0)  # upper, lower, other
TUNE_THROUGH = 2024


def stage_bucket(value) -> str:
    text = str(value or "").casefold()
    if "upper" in text:
        return "upper"
    if "lower" in text:
        return "lower"
    return "other"


def replay(df: pd.DataFrame, hs: tuple[float, float, float]) -> np.ndarray:
    """Continuous chronological Elo; stage h affects both p and rating update."""
    from vct_quant.features.build import margin_signal

    signal = margin_signal(df).to_numpy(dtype=float)
    buckets = df.stage_bucket.to_numpy()
    positions = {"upper": 0, "lower": 1, "other": 2}
    ratings = {}
    probs = np.empty(len(df), dtype=float)
    for i, (a, b, score) in enumerate(zip(df.team_a, df.team_b, signal)):
        h = hs[positions[buckets[i]]]
        ra, rb = ratings.get(a, 1500.0), ratings.get(b, 1500.0)
        p = 1.0 / (1.0 + 10.0 ** ((rb - ra - h) / 400.0))
        probs[i] = p
        ratings[a] = ra + K * (score - p)
        ratings[b] = rb - K * (score - p)
    return probs


def loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-15, 1 - 1e-15)
    y = np.asarray(y, dtype=float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def paired_t(base: np.ndarray, candidate: np.ndarray) -> float:
    diff = np.asarray(base) - np.asarray(candidate)
    if len(diff) < 2 or diff.std(ddof=1) == 0:
        return float("nan")
    return float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff))))


def select(tune_losses: dict[tuple[float, ...], float]) -> tuple[float, ...]:
    return min(tune_losses, key=lambda hs: (tune_losses[hs], sum(abs(h - 30) for h in hs), hs))


def prepare() -> pd.DataFrame:
    from vct_quant import db
    from vct_quant.features.build import match_sequence

    df = match_sequence(tiers=(3,))
    con = db.connect(read_only=True)
    try:
        stages = con.execute("SELECT match_id, event_series FROM match").df()
    finally:
        con.close()
    df = df.merge(stages, on="match_id", how="left", validate="one_to_one")
    df["stage_bucket"] = df.event_series.map(stage_bucket)
    return df


def run(df: pd.DataFrame) -> dict:
    y = df.score_a.to_numpy(dtype=float)
    years = df.year.to_numpy(dtype=int)
    valid = y != 0.5
    tune_mask = valid & (years <= TUNE_THROUGH)
    test_mask = valid & (years > TUNE_THROUGH)
    configs = list(itertools.product(H_GRID, repeat=3))
    tune_losses = {}
    for hs in configs:
        tune_losses[hs] = float(loss(y[tune_mask], replay(df, hs)[tune_mask]).mean())
    selected = select(tune_losses)
    if selected == REFERENCE:
        return {"tune_n": int(tune_mask.sum()), "selected": selected,
                "tune_reference_loss": tune_losses[REFERENCE],
                "tune_selected_loss": tune_losses[selected], "scored": False,
                "reason": "selected reference; frozen protocol says do not score"}

    p_ref, p_new = replay(df, REFERENCE), replay(df, selected)
    l_ref, l_new = loss(y[test_mask], p_ref[test_mask]), loss(y[test_mask], p_new[test_mask])
    years_test = years[test_mask]
    by_year = {}
    year_improvements = {}
    for yr in sorted(set(years_test.tolist())):
        m = years_test == yr
        improvement = float(l_ref[m].mean() - l_new[m].mean())
        year_improvements[int(yr)] = improvement
        by_year[int(yr)] = {"n": int(m.sum()), "reference_logloss": float(l_ref[m].mean()),
                            "candidate_logloss": float(l_new[m].mean()),
                            "paired_t": paired_t(l_ref[m], l_new[m])}
    by_stage_year = {}
    buckets = df.stage_bucket.to_numpy()[test_mask]
    for stage in ("upper", "lower", "other"):
        sm = buckets == stage
        by_stage_year[stage] = {"n": int(sm.sum())}
        for yr in sorted(set(years_test.tolist())):
            m = sm & (years_test == yr)
            by_stage_year[stage][str(yr)] = int(m.sum())
    propose = paired_t(l_ref, l_new) >= 2.0 and bool(year_improvements) and all(v > 0 for v in year_improvements.values())
    return {"tune_n": int(tune_mask.sum()), "selected": selected,
            "tune_reference_loss": tune_losses[REFERENCE],
            "tune_selected_loss": tune_losses[selected], "scored": True,
            "test_n": int(test_mask.sum()), "reference_logloss": float(l_ref.mean()),
            "candidate_logloss": float(l_new.mean()), "paired_t": paired_t(l_ref, l_new),
            "reference_brier": float(((p_ref[test_mask] - y[test_mask]) ** 2).mean()),
            "candidate_brier": float(((p_new[test_mask] - y[test_mask]) ** 2).mean()),
            "by_year": by_year, "by_stage_year": by_stage_year,
            "propose_shadow": propose}


def main() -> None:
    df = prepare()
    print(f"GC matches={len(df):,}; event_series missing={int(df.event_series.isna().sum()):,}")
    print(json.dumps(run(df), indent=2))


if __name__ == "__main__":
    main()
