"""Shadow Newton boosting of a fixed production Elo logit."""
from __future__ import annotations

from collections import defaultdict, deque
from itertools import product
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "src"))
import round_share_series as rs
from stack_ensemble import logits, metrics, reliability, sigmoid
from vct_quant import db
from vct_quant.features.build import build_features, elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo

FEATURES = ("elo_p", "log_prior_a", "log_prior_b", "days_a", "days_b",
            "days_missing_a", "days_missing_b", "form_a", "form_b",
            "map_share_a", "map_share_b", "churn_a", "churn_b",
            "player_form_diff", "best_of")
SWAP = np.array([0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 13, 14])
ROUNDS = (0, 25, 50, 100, 200)
GRID = tuple(product((1, 2), (50, 150)))
LR = .05


def build_matrix(matches: pd.DataFrame, maps: dict[int, list[tuple[int, int]]],
                 extras: pd.DataFrame) -> pd.DataFrame:
    """Record both teams' state before consuming the current match."""
    if matches.match_id.duplicated().any() or not matches.match_id.is_monotonic_increasing:
        raise ValueError("matches must have unique, increasing match IDs")
    extra = extras.set_index("match_id")
    if not extra.index.is_unique:
        raise ValueError("duplicate extra match IDs")
    counts: dict[str, int] = defaultdict(int)
    dates: dict[str, pd.Timestamp] = {}
    forms: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=5))
    map_form: dict[str, deque[int]] = defaultdict(lambda: deque(maxlen=10))
    rows = []
    for row in matches.itertuples(index=False):
        mid, a, b = int(row.match_id), row.team_a, row.team_b
        date = pd.to_datetime(row.completed_at, utc=True)
        current = extra.loc[mid]
        values = {"match_id": mid, "year": int(row.year), "tier": int(row.tier),
                  "y": float(row.score_a), "p_elo": float(row.p_elo),
                  "elo_p": float(row.p_elo), "best_of": int(row.best_of) if row.best_of in (1, 3, 5) else 0,
                  "churn_a": float(current.churn_a) if pd.notna(current.churn_a) else -1.,
                  "churn_b": float(current.churn_b) if pd.notna(current.churn_b) else -1.,
                  "player_form_diff": float(current.player_form_diff) if pd.notna(current.player_form_diff) else 0.}
        for team, side in ((a, "a"), (b, "b")):
            previous = dates.get(team)
            missing = pd.isna(date) or previous is None or pd.isna(previous)
            values[f"log_prior_{side}"] = float(np.log1p(counts[team]))
            values[f"days_{side}"] = -1. if missing else max(0., float((date - previous).total_seconds() / 86400))
            values[f"days_missing_{side}"] = float(missing)
            values[f"form_{side}"] = float(np.mean(forms[team])) if forms[team] else 0.
            values[f"map_share_{side}"] = float(np.mean(map_form[team])) if map_form[team] else -1.
        rows.append(values)
        # The two sides are updated only after their pre-match row is complete.
        for team, score, p in ((a, row.score_a, row.p_elo), (b, 1-row.score_a, 1-row.p_elo)):
            counts[team] += 1
            dates[team] = date
            forms[team].append(float(score-p))
        for score_a, score_b in maps.get(mid, []):
            if score_a + score_b > 0:
                map_form[a].append(int(score_a > score_b))
                map_form[b].append(int(score_b > score_a))
    return pd.DataFrame(rows)


def mirror(x: np.ndarray) -> np.ndarray:
    result = np.asarray(x, float)[:, SWAP].copy()
    result[:, 0] = 1 - result[:, 0]
    result[:, 13] *= -1
    return result


def fit_path(x: np.ndarray, y: np.ndarray, depth: int, leaf: int,
             rounds: int = 200) -> list[DecisionTreeRegressor]:
    paired_x = np.concatenate((x, mirror(x)))
    paired_y = np.concatenate((y, 1-y))
    z = logits(paired_x[:, 0])
    trees = []
    for _ in range(rounds):
        p = sigmoid(z)
        h = np.maximum(p * (1-p), 1e-8)
        tree = DecisionTreeRegressor(max_depth=depth, min_samples_leaf=leaf,
                                     random_state=0)
        tree.fit(paired_x, (paired_y-p)/h, sample_weight=h)
        z += LR * tree.predict(paired_x)
        trees.append(tree)
    return trees


def predict(x: np.ndarray, trees: list[DecisionTreeRegressor]) -> np.ndarray:
    x = np.asarray(x, float)
    if not trees:
        return x[:, 0].copy()
    opposite = mirror(x)
    za, zb = logits(x[:, 0]), logits(opposite[:, 0])
    for tree in trees:
        za += LR * tree.predict(x)
        zb += LR * tree.predict(opposite)
    return .5 * (sigmoid(za) + 1-sigmoid(zb))


def load_data() -> pd.DataFrame:
    con = db.connect(read_only=True)
    try:
        matches = match_sequence(con).reset_index(drop=True)
        formats = con.execute("SELECT match_id, best_of FROM match").df()
        expected = {int(r.match_id): (r.team_a, r.team_b) for r in matches.itertuples(index=False)}
        maps, availability = rs.load_maps(con, expected)
        extras = build_features(con)[["match_id", "churn_a", "churn_b", "player_form_diff"]]
    finally:
        con.close()
    elo_rows = compute_elo(zip(matches.match_id, matches.team_a, matches.team_b,
                               margin_signal(matches)), k=elo_k(matches.tier))[0]
    elo = pd.DataFrame(elo_rows)[["match_id", "p_a_win"]].rename(columns={"p_a_win": "p_elo"})
    matches = matches.merge(elo, on="match_id", validate="one_to_one", sort=False)
    matches = matches.merge(formats, on="match_id", validate="one_to_one", sort=False)
    # build_features excludes drawn series; their side context is unused because
    # these rows are never fitted or scored. Rolling histories still consume them.
    extras = matches[["match_id"]].merge(extras, on="match_id", how="left", validate="one_to_one")
    print("Map availability:", availability, flush=True)
    return build_matrix(matches, maps, extras)


def run(frame: pd.DataFrame) -> tuple[tuple[int, int, int], dict[int, dict], np.ndarray]:
    frame = frame.loc[frame.tier.eq(1) & frame.y.isin((0, 1))].copy()
    x, y = frame[list(FEATURES)].to_numpy(float), frame.y.to_numpy(float)
    years = frame.year.to_numpy(int)
    train, valid = years <= 2023, years == 2024
    if not train.any() or not valid.any():
        raise ValueError("training and 2024 validation rows are required")
    table = []
    print("depth leaf rounds validation_n validation_log_loss")
    for depth, leaf in GRID:
        trees = fit_path(x[train], y[train], depth, leaf)
        for rounds in ROUNDS:
            p = predict(x[valid], trees[:rounds])
            loss = float(np.mean(np.logaddexp(0, logits(p))-y[valid]*logits(p)))
            table.append((loss, depth, leaf, rounds))
            print(depth, leaf, rounds, int(valid.sum()), f"{loss:.8f}", flush=True)
    _, depth, leaf, rounds = min(table)
    edge = {"depth": depth in (1, 2), "leaf": leaf in (50, 150),
            "rounds": rounds in (0, 200)}
    print("Chosen cell:", (depth, leaf, rounds), "grid edges:", edge, flush=True)
    trees = fit_path(x[years <= 2024], y[years <= 2024], depth, leaf, rounds)
    results = {}
    print("year n loss elo_loss brier elo_brier accuracy elo_accuracy paired_t ece elo_ece")
    for year in (2025, 2026):
        mask = years == year
        if not mask.any():
            raise ValueError(f"no binary Tier-1 matches in {year}")
        p = predict(x[mask], trees)
        elo = x[mask, 0]
        result = metrics(y[mask], p, elo)
        results[year] = result
        print(year, result["n"], *(f"{result[k]:.8f}" for k in
              ("loss", "elo_loss", "brier", "elo_brier", "accuracy",
               "elo_accuracy", "t", "ece", "elo_ece")), flush=True)
        for name, values in (("model", p), ("Elo", elo)):
            print(year, name, "reliability (bin,n,p,observed):", reliability(y[mask], values), flush=True)
    importance = sum((tree.feature_importances_ for tree in trees), np.zeros(len(FEATURES)))
    print("Summed feature importances:")
    for name, value in zip(FEATURES, importance):
        print(name, f"{value:.8f}")
    tests = list(results.values())
    verdict = ("REJECTED" if rounds == 0 else
               "WIN" if all(r["t"] > 2 and r["ece"] <= r["elo_ece"] for r in tests) else
               "NOT PROVEN" if all(r["t"] > 0 for r in tests) else "REJECTED")
    print("Verdict:", verdict)
    return (depth, leaf, rounds), results, importance


if __name__ == "__main__":
    run(load_data())
