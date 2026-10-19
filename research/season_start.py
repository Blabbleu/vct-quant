"""Read-only season-start Elo diagnostics; no shrink candidate is scored."""
from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from model_lab import Config, load, run  # noqa: E402
from vct_quant.features.build import elo_k  # noqa: E402
from vct_quant.features.ratings import compute_elo  # noqa: E402

YEARS = (2023, 2024, 2025, 2026)
BINS = ("0", "(0,0.4]", ">0.4", "missing")


def production_probabilities(d: dict) -> np.ndarray:
    """Guard the model-lab replay against the production Elo implementation."""
    p = run(d, Config())
    ref = np.array([row["p_a_win"] for row in compute_elo(
        zip(d["match_id"], d["team_a"], d["team_b"], d["signal"]),
        k=elo_k(d["df"].tier))[0]])
    np.testing.assert_allclose(p[d["tier"] == 1], ref[d["tier"] == 1],
                               rtol=0, atol=1e-12)
    return p


def churn(previous: frozenset | None, current: frozenset | None) -> float | None:
    if previous is None or len(previous) != 5 or not current:
        return None
    return (5 - len(previous & current)) / 5


def churn_bin(value: float | None) -> str:
    if value is None:
        return "missing"
    if value == 0:
        return "0"
    return "(0,0.4]" if value <= 0.4 else ">0.4"


def side_windows(d: dict) -> list[dict]:
    """Classify scored sides before consuming each row's lineup and outcome."""
    ids = np.asarray(d["match_id"])
    if len(ids) > 1 and not np.all(ids[1:] > ids[:-1]):
        raise ValueError("match IDs must be strictly increasing")
    seen_tier1: set[tuple[int, object]] = set()
    decisive_counts: Counter = Counter()
    latest_lineup: dict[tuple[int, object], frozenset] = {}
    sides = []
    for i, match_id in enumerate(ids):
        year = int(d["year"][i])
        teams = ((d["team_a"][i], d["lineup_a"][i]),
                 (d["team_b"][i], d["lineup_b"][i]))
        scored = d["tier"][i] == 1 and d["y"][i] in (0.0, 1.0)
        if scored:
            for position, (team, own_lineup) in enumerate(teams):
                if (year - 1, team) in seen_tier1:
                    rank = decisive_counts[(year, team)] + 1
                    if rank <= 3:
                        previous = latest_lineup.get((year - 1, team))
                        prior = latest_lineup.get((year, team))
                        sides.append({"index": i, "match_id": int(match_id), "year": year,
                                      "position": position, "team": team, "rank": rank,
                                      "asof": churn(previous, prior),
                                      "oracle": churn(previous, frozenset(own_lineup))})
                decisive_counts[(year, team)] += 1
        if d["tier"][i] == 1:
            for team, _ in teams:
                seen_tier1.add((year, team))
        # Consume observations only after classification. Missing rosters leave
        # the last observation intact, including across intervening tiers.
        for team, lineup in teams:
            if lineup:
                latest_lineup[(year, team)] = frozenset(lineup)
    return sides


def losses(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    q = np.clip(p, 1e-12, 1 - 1e-12)
    return -(y * np.log(q) + (1 - y) * np.log(1 - q))


def ece(y: np.ndarray, p: np.ndarray) -> float:
    if not len(y):
        return float("nan")
    total = 0.0
    for j in range(10):
        mask = (p >= j / 10) & (p < (j + 1) / 10 if j < 9 else p <= 1)
        if mask.any():
            total += mask.mean() * abs(p[mask].mean() - y[mask].mean())
    return float(total)


def welch_t(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return float((a.mean() - b.mean()) / se) if se else float("nan")


def summarize(d: dict, p: np.ndarray) -> dict:
    sides = side_windows(d)
    result = {}
    tier = np.asarray(d["tier"])
    years = np.asarray(d["year"])
    y = np.asarray(d["y"])
    eligible = (tier == 1) & np.isin(y, (0.0, 1.0))
    ll = losses(y[eligible], p[eligible])
    full_loss = np.full(len(y), np.nan)
    full_loss[eligible] = ll
    for year in YEARS:
        base = np.flatnonzero(eligible & (years == year))
        result[year] = {}
        for window, cap in (("first", 1), ("first-three", 3)):
            selected = [s for s in sides if s["year"] == year and s["rank"] <= cap]
            by_index: dict[int, list[dict]] = {}
            for s in selected:
                by_index.setdefault(s["index"], []).append(s)
            start = np.array(sorted(by_index), dtype=int)
            rest = np.setdiff1d(base, start)
            start_l, rest_l = full_loss[start], full_loss[rest]
            start_b = (p[start] - y[start]) ** 2
            rest_b = (p[rest] - y[rest]) ** 2
            oracle_bins = {}
            availability = {}
            for label in BINS:
                rows = [i for i, ss in by_index.items() if churn_bin(max(
                    (s["oracle"] for s in ss if s["oracle"] is not None), default=None)) == label]
                oracle_bins[label] = (len(rows), float(np.mean(full_loss[rows])) if rows else None)
            for label, predicate in (("known", True), ("missing", False)):
                rows = [i for i, ss in by_index.items() if any(s["asof"] is not None for s in ss) == predicate]
                availability[label] = (len(rows), float(np.mean(full_loss[rows])) if rows else None)
            result[year][window] = {
                "start_n": len(start), "both_n": sum(len(ss) == 2 for ss in by_index.values()),
                "rest_n": len(rest), "start_ll": float(start_l.mean()) if len(start) else None,
                "rest_ll": float(rest_l.mean()) if len(rest) else None,
                "delta_ll": float(start_l.mean() - rest_l.mean()) if len(start) and len(rest) else None,
                "welch_t": welch_t(start_l, rest_l),
                "start_brier": float(start_b.mean()) if len(start) else None,
                "rest_brier": float(rest_b.mean()) if len(rest) else None,
                "delta_brier": float(start_b.mean() - rest_b.mean()) if len(start) and len(rest) else None,
                "start_ece": ece(y[start], p[start]),
                "start_accuracy": float(np.mean((p[start] >= 0.5) == y[start])) if len(start) else None,
                "coverage": {"known": sum(s["asof"] is not None for s in selected),
                             "missing": sum(s["asof"] is None for s in selected)},
                "asof_bins": dict(Counter(churn_bin(s["asof"]) for s in selected)),
                "oracle_bins": dict(Counter(churn_bin(s["oracle"]) for s in selected)),
                "oracle_loss": oracle_bins, "availability_loss": availability,
            }
    return result


def fmt(value: float | None) -> str:
    return "NA" if value is None or not np.isfinite(value) else f"{value:.5f}"


def main() -> int:
    d = load()
    p = production_probabilities(d)
    result = summarize(d, p)
    print("year | window | start n | both n | rest n | start LL | rest LL | ΔLL | Welch t | start Brier | rest Brier | ΔBrier | start ECE | start accuracy")
    for year in YEARS:
        for window, row in result[year].items():
            print(f"{year} | {window} | {row['start_n']} | {row['both_n']} | {row['rest_n']} | "
                  + " | ".join(fmt(row[key]) for key in ("start_ll", "rest_ll", "delta_ll", "welch_t", "start_brier", "rest_brier", "delta_brier", "start_ece", "start_accuracy")))
    print("\nyear | window | as-of known sides | missing sides | as-of bins [0, (0,.4], >.4, missing] | oracle bins [same]")
    for year in YEARS:
        for window, row in result[year].items():
            counts = lambda name: ",".join(str(row[name].get(label, 0)) for label in BINS)
            print(f"{year} | {window} | {row['coverage']['known']} | {row['coverage']['missing']} | {counts('asof_bins')} | {counts('oracle_bins')}")
    print("\nyear | window | oracle bin | row n | mean Elo LL | as-of availability | row n | mean Elo LL")
    for year in YEARS:
        for window, row in result[year].items():
            for label in BINS:
                n, mean = row["oracle_loss"][label]
                print(f"{year} | {window} | {label} | {n} | {fmt(mean)} |  |  | ")
            for label, (n, mean) in row["availability_loss"].items():
                print(f"{year} | {window} |  |  |  | {label} | {n} | {fmt(mean)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
