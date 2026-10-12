"""Read-only, match-ID walk-forward availability audit of frozen carry-over.

Run ``python research/asof_carryover.py``. The preregistered protocol is in
docs/research/2026-10-12-asof-carryover.md.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from model_lab import load  # noqa: E402
from open_era import run as oracle_run  # noqa: E402

from vct_quant.features.build import BEST_K, TIER_2_WEIGHT, elo_k  # noqa: E402
from vct_quant.features.ratings import compute_elo, expected_score  # noqa: E402

BASE = 1500.0
MIN_SHARED = 3
PERIODS = ("2022 H1", "2022 H2", "2023", "2024", "2025", "2026")
MODELS = ("Elo", "oracle", "as-of")


def replay(d: dict) -> tuple[np.ndarray, list[dict]]:
    """Predict before consuming this row's outcome or lineup; return debut sides."""
    assert TIER_2_WEIGHT == 0.0
    ids = np.asarray(d["match_id"])
    if len(ids) > 1 and not np.all(ids[1:] > ids[:-1]):
        raise ValueError("match IDs must be strictly increasing")
    n = len(ids)
    out = np.full(n, np.nan)
    rating: dict = {}
    last_lineup: dict = {}
    # Only a rated Tier-1 source establishes player provenance. An unrated
    # team's Tier-2 lineup provides target availability without erasing the
    # players' last rated source.
    player_rated_team: dict = {}
    debuts: list[dict] = []

    for i in range(n):
        tier = d["tier"][i]
        a, b = d["team_a"][i], d["team_b"][i]
        if tier == 1:
            for team in (a, b):
                if team in rating:
                    continue
                prior = last_lineup.get(team, frozenset())
                counts: dict = {}
                for player in prior:
                    source = player_rated_team.get(player)
                    if source is not None and source != team:
                        counts[source] = counts.get(source, 0) + 1
                source = None
                if counts:
                    candidate, count = max(counts.items(), key=lambda item: item[1])
                    if (count >= MIN_SHARED and candidate in rating
                            and len(prior & last_lineup.get(candidate, frozenset())) >= MIN_SHARED):
                        source = candidate
                rating[team] = rating[source] if source is not None else BASE
                debuts.append({"index": i, "match_id": int(ids[i]),
                               "year": int(d["year"][i]), "team": team,
                               "prior_size": len(prior), "source": source})

            ra, rb = rating[a], rating[b]
            p = expected_score(ra, rb)
            out[i] = p
            # The only current-match performance read is after prediction.
            delta = BEST_K * (d["signal"][i] - p)
            rating[a], rating[b] = ra + delta, rb - delta

        # The only current-match lineup reads are after prediction. A missing
        # roster does not destroy an earlier observed lineup.
        for team, key in ((a, "lineup_a"), (b, "lineup_b")):
            lineup = frozenset(d[key][i])
            if not lineup:
                continue
            last_lineup[team] = lineup
            if team in rating:
                for player in lineup:
                    player_rated_team[player] = team
    return out, debuts


def log_losses(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    q = np.clip(p, 1e-12, 1 - 1e-12)
    return -(y * np.log(q) + (1 - y) * np.log(1 - q))


def paired_t(delta: np.ndarray) -> float:
    if len(delta) < 2:
        return 0.0
    sd = delta.std(ddof=1)
    return float(delta.mean() / (sd / math.sqrt(len(delta)))) if sd else 0.0


def calibration(y: np.ndarray, p: np.ndarray) -> tuple[float, list[tuple[int, float, float]]]:
    bins = []
    ece = 0.0
    for j in range(10):
        mask = (p >= j / 10) & ((p < (j + 1) / 10) if j < 9 else (p <= 1))
        count = int(mask.sum())
        forecast = float(p[mask].mean()) if count else float("nan")
        observed = float(y[mask].mean()) if count else float("nan")
        bins.append((count, forecast, observed))
        if count:
            ece += count / len(y) * abs(forecast - observed)
    return ece, bins


def period_masks(d: dict) -> dict[str, np.ndarray]:
    scored = (d["tier"] == 1) & np.isin(d["y"], [0.0, 1.0])
    y22 = scored & (d["year"] == 2022)
    cut = np.median(d["match_id"][y22])
    return {"2022 H1": y22 & (d["match_id"] <= cut),
            "2022 H2": y22 & (d["match_id"] > cut),
            "2023": scored & (d["year"] == 2023),
            "2024": scored & (d["year"] == 2024),
            "2025": scored & (d["year"] == 2025),
            "2026": scored & (d["year"] == 2026)}


def evaluate(d: dict) -> dict:
    asof, debuts = replay(d)
    elo, _, _ = oracle_run(d)
    oracle, _, _ = oracle_run(d, inherit=3, shrink=1.0, en_bloc=True)
    ref = np.array([row["p_a_win"] for row in compute_elo(
        zip(d["match_id"], d["team_a"], d["team_b"], d["signal"]),
        k=elo_k(d["df"].tier))[0]])
    tier1 = d["tier"] == 1
    np.testing.assert_allclose(elo[tier1], ref[tier1], rtol=0, atol=1e-12)
    masks = period_masks(d)
    probabilities = {"Elo": elo, "oracle": oracle, "as-of": asof}
    result = {"years": {}, "coverage": {}, "cut": float(np.median(
        d["match_id"][(d["tier"] == 1) & np.isin(d["y"], [0.0, 1.0]) & (d["year"] == 2022)]))}
    for period, mask in masks.items():
        y = d["y"][mask]
        base_loss = log_losses(y, elo[mask])
        result["years"][period] = {}
        for name, probs in probabilities.items():
            p = probs[mask]
            losses = log_losses(y, p)
            ece, bins = calibration(y, p)
            result["years"][period][name] = {
                "n": len(y), "log_loss": float(losses.mean()),
                "brier": float(np.mean((p - y) ** 2)),
                "accuracy": float(np.mean((p >= 0.5) == y)),
                "t": paired_t(base_loss - losses), "ece": ece, "bins": bins,
            }
        sides = [row for row in debuts if mask[row["index"]]]
        result["coverage"][period] = {
            "debut_sides": len(sides),
            "none": sum(row["prior_size"] == 0 for row in sides),
            "one_two": sum(1 <= row["prior_size"] <= 2 for row in sides),
            "three_four": sum(3 <= row["prior_size"] <= 4 for row in sides),
            "five_plus": sum(row["prior_size"] >= 5 for row in sides),
            "inherited": sum(row["source"] is not None for row in sides),
        }
    recent = (result["years"][year] for year in ("2025", "2026"))
    recent = list(recent)
    inherited = sum(result["coverage"][year]["inherited"] for year in ("2025", "2026"))
    passes = (inherited > 0 and all(
        item["as-of"]["t"] > 2 and item["as-of"]["ece"] <= item["Elo"]["ece"]
        for item in recent))
    no_gain_both = all(item["as-of"]["log_loss"] >= item["Elo"]["log_loss"] for item in recent)
    result["verdict"] = ("PROSPECTIVE CANDIDATE" if passes else
                         "NOT VIABLE" if inherited == 0 or no_gain_both else "NOT PROVEN")
    result["descriptive"] = "WIN" if all(item["as-of"]["t"] > 2 for item in recent) else "TIE/LOSS"
    return result


def main() -> int:
    result = evaluate(load())
    print(f"2022 median match-ID cut: {result['cut']:g}")
    for period in PERIODS:
        print(f"\n{period} | model | n | log loss | Brier | accuracy | paired t vs Elo | ECE")
        for name in MODELS:
            row = result["years"][period][name]
            print(f"{period} | {name} | {row['n']} | {row['log_loss']:.5f} | "
                  f"{row['brier']:.5f} | {row['accuracy']:.5f} | {row['t']:+.2f} | {row['ece']:.5f}")
            print("  bin | n | mean p | observed")
            for j, (count, forecast, observed) in enumerate(row["bins"]):
                hi = "]" if j == 9 else ")"
                print(f"  [{j/10:.1f},{(j+1)/10:.1f}{hi} | {count} | {forecast:.5f} | {observed:.5f}")
        print(f"coverage: {result['coverage'][period]}")
    print(f"\nVerdict: {result['verdict']} ({result['descriptive']} vs Elo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
