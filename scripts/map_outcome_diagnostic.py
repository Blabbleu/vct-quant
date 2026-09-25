"""Read-only played-map conditional outcome diagnostic; NOT a pre-veto series test.

Protocol frozen in docs/map-outcome-protocol-2026-09-25.md.
Run: python scripts/map_outcome_diagnostic.py
"""
from __future__ import annotations

from math import log10, sqrt

import numpy as np
import pandas as pd

from vct_quant import db
from vct_quant.eval.metrics import brier_score, log_loss
from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.maps import MAP_K, MAP_PRIOR, map_sequence
from vct_quant.features.ratings import (
    DEFAULT_BASE, compute_elo, expected_score, implied_map_probability, update,
)


def replay_maps(
    matches: pd.DataFrame, maps: pd.DataFrame,
    k: float = MAP_K, prior: float = MAP_PRIOR,
) -> pd.DataFrame:
    """Predict all played maps from prior *matches*, update the pool afterward.

    The map's name is used only for this conditional outcome diagnostic. Map
    rows are never taken to imply a timestamped, complete pre-series veto.
    """
    if not matches.match_id.is_monotonic_increasing or maps.match_id.isna().any():
        raise ValueError("matches must be in match-ID order and maps need match IDs")
    by_match = {int(mid): group for mid, group in maps.groupby("match_id", sort=False)}
    ratings: dict[tuple[str, str], float] = {}
    counts: dict[tuple[str, str], int] = {}
    results: list[dict] = []
    for match in matches.itertuples(index=False):
        group = by_match.get(int(match.match_id))
        if group is None:
            continue
        eligible = match.best_of in (3, 5) and pd.notna(match.p_global)
        p_base = implied_map_probability(float(match.p_global), int(match.best_of)) if eligible else None
        global_diff = 400 * log10(p_base / (1 - p_base)) if eligible else None
        pending: list[tuple[tuple[str, str], tuple[str, str], float]] = []
        for row in group.itertuples(index=False):
            key_a = (str(row.map_name).strip().lower(), str(row.team_a))
            key_b = (str(row.map_name).strip().lower(), str(row.team_b))
            if not key_a[0] or key_a[0] in ("nan", "none") or key_a == key_b:
                continue
            if row.score_a not in (0.0, 1.0):
                continue
            if eligible:
                evidence = min(counts.get(key_a, 0), counts.get(key_b, 0))
                weight = evidence / (evidence + prior) if evidence + prior else 0.0
                difference = (1 - weight) * global_diff + weight * (
                    ratings.get(key_a, DEFAULT_BASE) - ratings.get(key_b, DEFAULT_BASE)
                )
                results.append({
                    "match_id": int(match.match_id), "year": match.year,
                    "map_name": key_a[0], "map_number": row.map_number,
                    "label": float(row.score_a), "p_base": p_base,
                    "p_candidate": expected_score(DEFAULT_BASE + difference / 2,
                                                   DEFAULT_BASE - difference / 2),
                    "prior_min": evidence,
                })
            pending.append((key_a, key_b, float(row.score_a)))
        # Do not update even the first map until all maps are forecast.
        for key_a, key_b, score_a in pending:
            ratings[key_a], ratings[key_b] = update(
                ratings.get(key_a, DEFAULT_BASE), ratings.get(key_b, DEFAULT_BASE),
                score_a, k,
            )
            counts[key_a] = counts.get(key_a, 0) + 1
            counts[key_b] = counts.get(key_b, 0) + 1
    return pd.DataFrame(results)


def paired_t(differences: np.ndarray) -> float:
    return float(np.mean(differences) / (np.std(differences, ddof=1) / sqrt(len(differences)))) if len(differences) >= 2 and np.std(differences, ddof=1) else float("nan")


def report(rows: pd.DataFrame, name: str) -> None:
    if rows.empty:
        print(f"{name}: no scored maps")
        return
    y = rows.label.to_numpy()
    a, b = rows.p_base.to_numpy(), rows.p_candidate.to_numpy()
    losses = lambda p: -(y * np.log(np.clip(p, 1e-15, 1 - 1e-15)) +
                         (1 - y) * np.log(np.clip(1 - p, 1e-15, 1 - 1e-15)))
    delta = losses(a) - losses(b)
    clustered = pd.DataFrame({"match_id": rows.match_id, "delta": delta}).groupby("match_id").delta.mean()
    print(f"{name}: maps={len(rows)}, series={rows.match_id.nunique()}, "
          f"base loss={log_loss(y, a):.5f}, map loss={log_loss(y, b):.5f}, "
          f"base Brier={brier_score(y, a):.5f}, map Brier={brier_score(y, b):.5f}, "
          f"paired map t={paired_t(delta):+.2f}, series-mean t={paired_t(clustered.to_numpy()):+.2f}, "
          f"history>0={int(rows.prior_min.gt(0).sum())}")


def main() -> None:
    with db.connect(read_only=True) as con:
        matches = match_sequence(con)
        extra = con.execute("SELECT match_id, best_of, year(completed_at) AS completion_year FROM match").df()
        maps = map_sequence(con)
    elo = compute_elo(zip(matches.match_id, matches.team_a, matches.team_b,
                          margin_signal(matches)), k=elo_k(matches.tier))[0]
    matches = matches.assign(p_global=[row["p_a_win"] for row in elo]).merge(
        extra, on="match_id", validate="one_to_one", sort=False,
    )
    matches["year"] = matches.completion_year
    tier_one = matches.loc[matches.tier.eq(1)].sort_values("match_id")
    scored = replay_maps(tier_one, maps)
    # Tier-1 history from all years is retained in the replay; filter only scoring.
    for name, years in (("2023-24 validation", (2023, 2024)),
                        ("2025 retrospective", (2025,)),
                        ("2026 retrospective", (2026,)),
                        ("2025-26 retrospective", (2025, 2026))):
        report(scored.loc[scored.year.isin(years)], name)
    print("Conditional played-map outcome only; no historical pre-series veto timestamp.")


if __name__ == "__main__":
    main()
