"""Tuning-year exact-score diagnostics; never scores 2025+ outcomes.

Run: python research/exact_score_dependence.py
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from vct_quant import db
from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import (
    DEFAULT_BASE, compute_elo, expected_score, series_score_probabilities, update,
)

POOLS = ("Tier 1", "Tier 2", "GC")
SCORES = {
    3: ("2-0", "2-1", "1-2", "0-2"),
    5: ("3-0", "3-1", "3-2", "2-3", "1-3", "0-3"),
}
BIN_EDGES = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def replay_probabilities(sequence: pd.DataFrame) -> np.ndarray:
    """Independent pre-match replay on the complete, ordered production sequence."""
    ratings: dict[str, float] = {}
    probabilities = []
    for row, k in zip(sequence.itertuples(index=False), elo_k(sequence.tier)):
        a, b = ratings.get(row.team_a, DEFAULT_BASE), ratings.get(row.team_b, DEFAULT_BASE)
        probabilities.append(expected_score(a, b))
        ratings[row.team_a], ratings[row.team_b] = update(a, b, row.signal, float(k))
    return np.asarray(probabilities, dtype=float)


def assert_elo_equality(sequence: pd.DataFrame) -> np.ndarray:
    """Compare *every* full-pool row, then permit later tuning-year selection."""
    required = {"match_id", "team_a", "team_b", "tier", "signal"}
    if not required <= set(sequence):
        raise ValueError(f"missing Elo columns: {required - set(sequence)}")
    if sequence.match_id.duplicated().any() or not sequence.match_id.is_monotonic_increasing:
        raise ValueError("Elo sequence must be the full ordered pool")
    own = replay_probabilities(sequence)
    reference = compute_elo(
        zip(sequence.match_id, sequence.team_a, sequence.team_b, sequence.signal),
        k=elo_k(sequence.tier),
    )[0]
    ref_ids = [row["match_id"] for row in reference]
    ref = np.asarray([row["p_a_win"] for row in reference])
    if ref_ids != sequence.match_id.tolist() or not np.allclose(own, ref, atol=1e-12, rtol=0):
        raise AssertionError("full-pool Elo replay disagrees with production compute_elo")
    return own


def inferred_best_of(frame: pd.DataFrame) -> pd.Series:
    """Same fallback as model_lab.load, retaining explicit Bo2 for filtering."""
    inferred = (2 * np.maximum(frame.maps_a.fillna(0), frame.maps_b.fillna(0)) - 1).clip(1, 5)
    return frame.best_of.fillna(inferred).astype(int)


def filter_legal_scores(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Filter on score legality; 2025+ may be counted but never diagnosed."""
    data = frame.copy()
    data["best_of"] = inferred_best_of(data)
    reasons = np.full(len(data), "eligible", dtype=object)
    format_bad = ~data.best_of.isin((3, 5))
    reasons[format_bad.to_numpy()] = "other_format"
    missing = data.maps_a.isna() | data.maps_b.isna()
    reasons[(reasons == "eligible") & missing.to_numpy()] = "forfeit_missing_score"
    draw = data.score_a.isna() | data.score_a.eq(0.5)
    reasons[(reasons == "eligible") & draw.to_numpy()] = "draw_or_no_winner"
    scores = data.maps_a.astype("Int64").astype(str) + "-" + data.maps_b.astype("Int64").astype(str)
    legal = ((data.best_of.eq(3) & scores.isin(SCORES[3])) |
             (data.best_of.eq(5) & scores.isin(SCORES[5])))
    # Score legality alone determines eligibility; no 2025+ winner is derived.
    reasons[(reasons == "eligible") & (~legal).to_numpy()] = "impossible_score"
    data["score"] = scores
    data["filter_reason"] = reasons
    if "pool" not in data:
        data["pool"] = data.tier.map({1: "Tier 1", 2: "Tier 2", 3: "GC"})
    drops = (data.groupby(["pool", "year", "filter_reason"], dropna=False)
             .size().rename("n").reset_index())
    return data.loc[data.filter_reason.eq("eligible")].drop(columns="filter_reason"), drops


def independent(p_series: float, best_of: int) -> dict[str, float]:
    return series_score_probabilities(float(p_series), int(best_of))


def candidate_c(p_series: float, best_of: int, theta: float) -> dict[str, float]:
    """Shift shortest-score log-odds conditional on each winner."""
    base = independent(p_series, best_of)
    wins = best_of // 2 + 1
    out: dict[str, float] = {}
    for mass, prefix in ((p_series, True), (1 - p_series, False)):
        keys = [f"{wins}-{losses}" if prefix else f"{losses}-{wins}"
                for losses in range(wins)]
        shortest = base[keys[0]] / mass
        shifted = 1 / (1 + math.exp(-(math.log(shortest / (1 - shortest)) + theta)))
        out[keys[0]] = mass * shifted
        rest = 1 - shifted
        old_rest = sum(base[key] for key in keys[1:])
        for key in keys[1:]:
            out[key] = mass * rest * base[key] / old_rest
    return out


def conditional_loss(score: str, p_series: float, distribution: dict[str, float]) -> float:
    a_won = int(score.split("-")[0]) > int(score.split("-")[1])
    winner_mass = p_series if a_won else 1 - p_series
    return -math.log(distribution[score] / winner_mass)


def series_loss(score: str, p_series: float) -> float:
    a_won = int(score.split("-")[0]) > int(score.split("-")[1])
    return -math.log(p_series if a_won else 1 - p_series)


def paired_t(baseline: np.ndarray, candidate: np.ndarray) -> float:
    difference = baseline - candidate
    if len(difference) < 2 or difference.std(ddof=1) == 0:
        return float("nan")
    return float(difference.mean() / (difference.std(ddof=1) / math.sqrt(len(difference))))


def fit_theta(tuning: pd.DataFrame) -> float:
    if tuning.empty:
        return float("nan")
    shortest = []
    swept = []
    for row in tuning.itertuples(index=False):
        dist = independent(row.p_a_win, row.best_of)
        winner_a = row.score_a == 1
        key = (f"{row.best_of//2+1}-0" if winner_a
               else f"0-{row.best_of//2+1}")
        mass = row.p_a_win if winner_a else 1 - row.p_a_win
        shortest.append(dist[key] / mass)
        swept.append(row.score == key)
    q = np.clip(shortest, 1e-15, 1 - 1e-15)
    logits = np.log(q / (1 - q))
    y = np.asarray(swept, dtype=float)
    def objective(theta: float) -> float:
        z = logits + theta
        return float(np.logaddexp(0, z).sum() - np.dot(y, z))
    result = minimize_scalar(objective, bounds=(-2, 2), method="bounded",
                             options={"xatol": 1e-8})
    if not result.success:
        raise RuntimeError("theta fit failed")
    return float(min(((-2.0, objective(-2.0)), (float(result.x), result.fun),
                      (2.0, objective(2.0))), key=lambda item: item[1])[0])


def tuning_diagnostics(frame: pd.DataFrame) -> dict:
    """Reject any future row before reading its score or probability."""
    if frame.year.isna().any() or frame.year.ge(2025).any():
        raise ValueError("tuning_diagnostics accepts only years through 2024")
    if frame.empty:
        return {"n": 0, "bins": [], "theta": float("nan")}
    formats = frame.best_of.unique()
    if len(formats) != 1 or int(formats[0]) not in SCORES:
        raise ValueError("diagnostics require a single Bo3 or Bo5 cell")
    best_of = int(formats[0])
    model = [independent(row.p_a_win, best_of) for row in frame.itertuples(index=False)]
    scores = frame.score.tolist()
    sweep_keys = (SCORES[best_of][0], SCORES[best_of][-1])
    predicted = np.asarray([d[sweep_keys[0]] + d[sweep_keys[1]] for d in model])
    observed = np.asarray([s in sweep_keys for s in scores], dtype=float)
    favorite = np.maximum(frame.p_a_win.to_numpy(float), 1 - frame.p_a_win.to_numpy(float))
    bin_rows = []
    for i, (low, high) in enumerate(zip(BIN_EDGES[:-1], BIN_EDGES[1:])):
        mask = (favorite >= low) & ((favorite <= high) if i == 4 else (favorite < high))
        bin_rows.append({"bin": f"[{low:.1f}, {high:.1f}{']' if i == 4 else ')'}",
                         "n": int(mask.sum()),
                         "predicted": float(predicted[mask].mean()) if mask.any() else float("nan"),
                         "observed": float(observed[mask].mean()) if mask.any() else float("nan")})
    # One pooled conditional sweep frequency, used regardless of winner.
    pooled_sweep = float(observed.mean())
    naive = []
    independent_losses = []
    for row, dist in zip(frame.itertuples(index=False), model):
        independent_losses.append(conditional_loss(row.score, row.p_a_win, dist))
        winner_a = row.score.split("-")[0] > row.score.split("-")[1]
        keys = [f"{best_of//2+1}-{i}" if winner_a else f"{i}-{best_of//2+1}"
                for i in range(best_of//2+1)]
        if row.score == keys[0]:
            conditional = pooled_sweep
        elif best_of == 3:
            conditional = 1 - pooled_sweep
        else:
            conditional = (1 - pooled_sweep) * dist[row.score] / sum(dist[k] for k in keys[1:])
        naive.append(-math.log(max(conditional, 1e-15)))
    ind_loss = np.asarray(independent_losses)
    naive_loss = np.asarray(naive)
    winner_detail = []
    for label, mask in (("favourite", (frame.p_a_win.to_numpy(float) >= 0.5) == frame.score_a.to_numpy(float).astype(bool)),
                        ("underdog", (frame.p_a_win.to_numpy(float) >= 0.5) != frame.score_a.to_numpy(float).astype(bool))):
        idx = np.flatnonzero(mask)
        detail = {"winner": label, "n": len(idx)}
        for kind in (("shortest", 0), ("full_length", 2)) if best_of == 5 else (("shortest", 0),):
            name, offset = kind
            target = []
            actual = []
            for j in idx:
                row = frame.iloc[j]
                winner_a = row.score_a == 1
                key = (f"{best_of//2+1}-{offset}" if winner_a
                       else f"{offset}-{best_of//2+1}")
                mass = row.p_a_win if winner_a else 1 - row.p_a_win
                target.append(model[j][key] / mass)
                actual.append(row.score == key)
            detail[name + "_predicted"] = float(np.mean(target)) if target else float("nan")
            detail[name + "_observed"] = float(np.mean(actual)) if actual else float("nan")
        winner_detail.append(detail)
    return {"n": len(frame), "predicted": float(predicted.mean()),
            "observed": float(observed.mean()), "bins": bin_rows,
            "winner_detail": winner_detail,
            "independent_loss": float(ind_loss.mean()), "naive_loss": float(naive_loss.mean()),
            "paired_t_naive_minus_independent": paired_t(naive_loss, ind_loss),
            "theta": fit_theta(frame)}


def load_snapshot() -> tuple[pd.DataFrame, pd.DataFrame]:
    con = db.connect(read_only=True)
    try:
        formats = con.execute("SELECT match_id, best_of FROM match").df()
        parts = []
        for tiers in ((1, 2), (3,)):
            sequence = match_sequence(con, tiers=tiers).reset_index(drop=True)
            sequence["signal"] = margin_signal(sequence)
            # This equality is on all rows, including 2025+; their results are used
            # solely to advance the production rating replay.
            sequence["p_a_win"] = assert_elo_equality(sequence)
            parts.append(sequence)
    finally:
        con.close()
    frame = pd.concat(parts, ignore_index=True).merge(formats, on="match_id", validate="one_to_one")
    return filter_legal_scores(frame)


def main() -> None:
    eligible, drops = load_snapshot()
    print("Filter counts by pool, year, reason (eligible included):")
    print(drops.to_string(index=False))
    counts = (eligible.loc[eligible.year.isin((2025, 2026))]
              .groupby(["pool", "best_of", "year"]).size())
    print("\nExpected test n (eligibility counts only; zero shown explicitly):")
    for pool in POOLS:
        for best_of in (3, 5):
            print(f"{pool} Bo{best_of}: 2025={counts.get((pool, best_of, 2025), 0)}, "
                  f"2026={counts.get((pool, best_of, 2026), 0)}")
    tuning = eligible.loc[eligible.year.le(2024)].copy()
    for pool in POOLS:
        for best_of in (3, 5):
            cell = tuning.loc[tuning.pool.eq(pool) & tuning.best_of.eq(best_of)]
            d = tuning_diagnostics(cell)
            print(f"\n{pool} Bo{best_of}: n={d['n']}")
            if not d["n"]:
                continue
            print(f"sweep predicted={d['predicted']:.4f} observed={d['observed']:.4f}; "
                  f"conditional loss independent={d['independent_loss']:.4f} "
                  f"naive={d['naive_loss']:.4f} "
                  f"paired t(naive-independent)={d['paired_t_naive_minus_independent']:.2f}; "
                  f"theta={d['theta']:.5f}")
            print(pd.DataFrame(d["bins"]).to_string(index=False, float_format=lambda x: f"{x:.4f}"))
            print(pd.DataFrame(d["winner_detail"]).to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
