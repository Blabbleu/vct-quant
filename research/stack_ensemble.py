"""Frozen, no-intercept stack of three pre-match Tier-1 series models."""
from __future__ import annotations

import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "src"))
import lineup_skill
import round_share_series as rs
from vct_quant import db
from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo

PENALTY = 1e-3
NULL = np.array([1.0, 0.0, 0.0])


def logits(probabilities: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-12, 1 - 1e-12)
    return np.log(p) - np.log1p(-p)


def sigmoid(z: np.ndarray) -> np.ndarray:
    z = np.asarray(z, dtype=float)
    return np.exp(-np.logaddexp(0, -z))


def predict(x: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """No intercept: negating all component logits complements the forecast."""
    return sigmoid(np.asarray(x) @ np.asarray(weights))


def fit(x: np.ndarray, y: np.ndarray, anchor: np.ndarray | None = None) -> np.ndarray:
    x, y = np.asarray(x, float), np.asarray(y, float)
    anchor = NULL[:x.shape[1]] if anchor is None else np.asarray(anchor, float)
    if x.ndim != 2 or len(x) != len(y) or not len(y) or len(anchor) != x.shape[1]:
        raise ValueError("invalid training matrix")
    if not np.isfinite(x).all() or not np.isin(y, (0, 1)).all():
        raise ValueError("training data must be finite with binary outcomes")
    if np.array_equal(x, np.broadcast_to(x[:, :1], x.shape)):
        return anchor.copy()

    def objective(w: np.ndarray) -> tuple[float, np.ndarray]:
        z = x @ w
        p = sigmoid(z)
        value = float(np.mean(np.logaddexp(0, z) - y * z) + PENALTY / 2 * np.sum((w-anchor)**2))
        gradient = x.T @ (p-y) / len(y) + PENALTY * (w-anchor)
        return value, gradient

    try:
        from scipy.optimize import minimize
    except ImportError:
        w = anchor.copy()
        for _ in range(100):
            _, gradient = objective(w)
            p = predict(x, w)
            hessian = (x.T * (p * (1-p))) @ x / len(y) + PENALTY * np.eye(x.shape[1])
            step = np.linalg.solve(hessian, gradient)
            scale = 1.0
            current = objective(w)[0]
            while objective(w-scale*step)[0] > current and scale > 1e-8:
                scale /= 2
            w -= scale*step
            if np.max(np.abs(scale*step)) < 1e-9:
                break
        return w
    result = minimize(objective, anchor, jac=True, method="BFGS", options={"gtol": 1e-10, "maxiter": 1000})
    if not np.isfinite(result.x).all() or np.max(np.abs(objective(result.x)[1])) > 1e-6:
        raise RuntimeError(f"stack optimization failed: {result.message}")
    return np.asarray(result.x)


def align(elo: pd.DataFrame, round_share: pd.DataFrame, lineup: pd.DataFrame) -> pd.DataFrame:
    """Require one-to-one IDs and the same outcomes before joining components."""
    frames = (elo, round_share, lineup)
    sets = []
    for frame in frames:
        if frame.match_id.isna().any() or frame.match_id.duplicated().any():
            raise ValueError("null or duplicate match_id")
        sets.append(set(frame.match_id))
    if sets[0] != sets[1] or sets[0] != sets[2]:
        raise ValueError("misaligned match_id sets")
    out = elo.merge(round_share, on="match_id", validate="one_to_one", suffixes=("", "_rs"))
    out = out.merge(lineup, on="match_id", validate="one_to_one", suffixes=("", "_ls"))
    for suffix in ("_rs", "_ls"):
        a = out.y.to_numpy(float)
        b = out[f"y{suffix}"].to_numpy(float)
        if not np.array_equal(a, b, equal_nan=True):
            raise ValueError("component outcomes disagree")
        out = out.drop(columns=f"y{suffix}")
    return out


def reliability(y: np.ndarray, p: np.ndarray) -> list[tuple[int, int, float, float]]:
    buckets = np.minimum((p * 10).astype(int), 9)
    return [(i, int(np.sum(buckets == i)),
             float(p[buckets == i].mean()) if np.any(buckets == i) else math.nan,
             float(y[buckets == i].mean()) if np.any(buckets == i) else math.nan)
            for i in range(10)]


def metrics(y: np.ndarray, p: np.ndarray, elo: np.ndarray) -> dict:
    p, elo = np.clip(p, 1e-12, 1-1e-12), np.clip(elo, 1e-12, 1-1e-12)
    loss = np.logaddexp(0, logits(p)) - y * logits(p)
    base = np.logaddexp(0, logits(elo)) - y * logits(elo)
    delta = base-loss
    sd = float(delta.std(ddof=1)) if len(y) > 1 else 0.0
    return dict(n=len(y), loss=float(loss.mean()), elo_loss=float(base.mean()),
                brier=float(np.mean((p-y)**2)), elo_brier=float(np.mean((elo-y)**2)),
                accuracy=float(np.mean((p >= .5) == y)),
                elo_accuracy=float(np.mean((elo >= .5) == y)),
                t=float(delta.mean()*math.sqrt(len(y))/sd) if sd else 0.0,
                ece=sum(n*abs(pred-actual) for _, n, pred, actual in reliability(y,p) if n)/len(y),
                elo_ece=sum(n*abs(pred-actual) for _, n, pred, actual in reliability(y,elo) if n)/len(y))


def load_components() -> pd.DataFrame:
    con = db.connect(read_only=True)
    try:
        matches = match_sequence(con).reset_index(drop=True)
        formats = con.execute("SELECT match_id, best_of FROM match").df()
        expected = {int(r.match_id): (r.team_a, r.team_b) for r in matches.itertuples(index=False)}
        maps, availability = rs.load_maps(con, expected)
    finally:
        con.close()
    print("Map availability:", availability, flush=True)
    elo_rows = compute_elo(zip(matches.match_id, matches.team_a, matches.team_b,
                               margin_signal(matches)), k=elo_k(matches.tier))[0]
    elo = pd.DataFrame(elo_rows)[["match_id", "p_a_win"]].rename(columns={"p_a_win": "p_elo"})
    matches = matches.merge(elo, on="match_id", validate="one_to_one").merge(formats, on="match_id", validate="one_to_one")
    matches["year"] = pd.to_datetime(matches.completed_at, utc=True).dt.year
    round_predictions = rs.predict_sequence(matches, maps, (100, 500, 1.0))
    d = lineup_skill.load_data()
    lineup_elo = np.array([r["p_a_win"] for r in compute_elo(
        zip(d["match_id"], d["team_a"], d["team_b"], d["signal"]),
        k=elo_k(d["df"].tier))[0]])
    lineup_frame = pd.DataFrame({"match_id": d["match_id"], "p_check": lineup_elo})
    checked = elo.merge(lineup_frame, on="match_id", validate="one_to_one")
    if len(checked) != len(elo) or len(checked) != len(lineup_frame) or not np.allclose(checked.p_elo, checked.p_check, rtol=0, atol=1e-12):
        raise AssertionError("the two production Elo builds disagree")
    lineup_predictions = lineup_skill.replay(d, lineup_skill.Config(12, 4, .25, True), lineup_elo)
    e = matches[["match_id", "score_a", "tier", "year", "p_elo"]].rename(columns={"score_a":"y"})
    r = round_predictions[["match_id", "p_model"]].rename(columns={"p_model":"p_rs"}).merge(matches[["match_id", "score_a"]].rename(columns={"score_a":"y"}), on="match_id", validate="one_to_one")
    l = pd.DataFrame({"match_id":d["match_id"], "p_ls":lineup_predictions, "y":d["y"]})
    return align(e, r, l)


def evaluate(frame: pd.DataFrame) -> tuple[dict, dict, dict]:
    eligible = frame.tier.eq(1) & frame.y.isin((0, 1)) & frame.year.between(2023, 2026)
    frame = frame.loc[eligible].copy()
    x = logits(frame[["p_elo", "p_rs", "p_ls"]].to_numpy(float))
    y = frame.y.to_numpy(float)
    years = frame.year.to_numpy(int)
    primary = fit(x[np.isin(years, (2023, 2024))], y[np.isin(years, (2023, 2024))])
    expanding = {2025: primary, 2026: fit(x[years <= 2025], y[years <= 2025])}
    diagnostic = {"Elo+RS": fit(x[np.isin(years,(2023,2024))][:,[0,1]], y[np.isin(years,(2023,2024))]),
                  "Elo+LS": fit(x[np.isin(years,(2023,2024))][:,[0,2]], y[np.isin(years,(2023,2024))])}
    rows = {}
    print("year sample       n loss elo_loss brier elo_brier acc elo_acc paired_t ece elo_ece weights")
    for year in (2023, 2024, 2025, 2026):
        mask = years == year
        if not mask.any():
            print(year, "no completed binary Tier-1 matches")
            continue
        choices = {"primary":(primary, x[mask])}
        if year >= 2025:
            choices["expanding"] = (expanding[year], x[mask])
            choices.update({name:(w, x[mask][:,cols]) for name,w,cols in
                            (("Elo+RS", diagnostic["Elo+RS"], [0,1]),
                             ("Elo+LS", diagnostic["Elo+LS"], [0,2]))})
        for name,(weights,matrix) in choices.items():
            p = predict(matrix, weights)
            row = metrics(y[mask],p,frame.p_elo.to_numpy(float)[mask])
            rows[(year,name)] = row
            print(year, name, row["n"], *(f"{row[k]:.5f}" for k in
                  ("loss","elo_loss","brier","elo_brier","accuracy","elo_accuracy","t","ece","elo_ece")),
                  np.array2string(weights, precision=5), flush=True)
            if name == "primary":
                for label, values in (("stack",p),("Elo",frame.p_elo.to_numpy(float)[mask])):
                    print(year, label, "reliability (bin,n,p,observed):", reliability(y[mask],values), flush=True)
    if all((year,"primary") in rows for year in (2025,2026)):
        tests = [rows[(year,"primary")] for year in (2025,2026)]
        verdict = ("WIN" if all(r["t"] > 2 and r["ece"] <= r["elo_ece"] for r in tests)
                   else "NOT PROVEN" if all(r["t"] > 0 for r in tests) else "REJECTED")
    else:
        verdict = "INCOMPLETE"
    print("Primary verdict:",verdict)
    return rows, {"primary":primary, "expanding":expanding, "diagnostic":diagnostic}, {"verdict":verdict}


def main() -> None:
    evaluate(load_components())


if __name__ == "__main__":
    main()
