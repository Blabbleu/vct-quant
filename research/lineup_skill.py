"""Walk-forward Gaussian ADF lineup experiment; no production state is changed."""
from __future__ import annotations

import itertools
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.special import ndtr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import model_lab  # noqa: E402  -- use its loader, baseline, and series probability
from vct_quant import db  # noqa: E402
from vct_quant.features.build import elo_k  # noqa: E402
from vct_quant.features.ratings import compute_elo  # noqa: E402


@dataclass(frozen=True)
class Config:
    beta: float
    sigma0: float
    tau: float
    per_map: bool


GRID = [Config(*values) for values in itertools.product(
    (4.0, 8.0, 12.0), (4.0, 8.0, 16.0), (0.0, 0.25, 0.75), (False, True)
)]


def load_data() -> dict:
    """Call model_lab.load, adapting a duplicate completed_at in this snapshot."""
    original = model_lab.match_sequence

    def without_duplicate(con):
        frame = original(con)
        return frame.drop(columns=["completed_at"]) if "completed_at" in frame else frame

    model_lab.match_sequence = without_duplicate
    try:
        d = model_lab.load()
    finally:
        model_lab.match_sequence = original

    con = db.connect(read_only=True)
    try:
        # team_number is shared by match_team, map scores, and player stats.
        # Compare independently stored map and series team IDs before trusting it.
        matched, wrong = con.execute("""
            SELECT count(*), count(*) FILTER (WHERE ms.team_id <> mt.team_id)
            FROM (SELECT * FROM match_map_team_score WHERE team_id IS NOT NULL
                  ORDER BY match_map_id LIMIT 1000) ms
            JOIN match_map mm USING (match_map_id)
            JOIN match_team mt ON mt.match_id = mm.match_id
                              AND mt.team_number = ms.team_number
            WHERE mt.team_id IS NOT NULL
        """).fetchone()
        assert matched >= 100 and wrong == 0, (matched, wrong)
        appearances = con.execute("""
            SELECT mm.match_id, s.team_number,
                   coalesce(CAST(s.player_id AS VARCHAR),
                            'h:' || lower(trim(s.player_handle))) AS player,
                   count(*) AS maps
            FROM match_map_player_stat s JOIN match_map mm USING (match_map_id)
            GROUP BY 1, 2, 3
        """).fetchall()
    finally:
        con.close()
    counts = {}
    for match, side, player, maps in appearances:
        counts.setdefault((int(match), int(side)), {})[player] = int(maps)
    for side in ("a", "b"):
        for i, lineup in enumerate(d[f"lineup_{side}"]):
            if len(lineup) > 5:
                by_maps = counts[(int(d["match_id"][i]), 1 if side == "a" else 2)]
                d[f"lineup_{side}"][i] = sorted(lineup, key=lambda p: (-by_maps[p], p))[:5]
    return d


def predict_map(a: list[str], b: list[str], state: dict, cfg: Config) -> float:
    va = [state[p][1] if p in state else cfg.sigma0**2 for p in a]
    vb = [state[p][1] if p in state else cfg.sigma0**2 for p in b]
    mean = sum(state[p][0] if p in state else 0.0 for p in a) - sum(
        state[p][0] if p in state else 0.0 for p in b)
    c = math.sqrt(10 * cfg.beta**2 + sum(va) + sum(vb))
    return float(ndtr(mean / c))


def advance_idle(state: dict, players: list[str], day: float, cfg: Config) -> None:
    for p in players:
        mu, var, last = state.get(p, (0.0, cfg.sigma0**2, math.nan))
        if math.isfinite(day) and math.isfinite(last) and day > last:
            var += cfg.tau**2 * (day - last)
        state[p] = (mu, var, day if math.isfinite(day) else last)


def adf_update(state: dict, a: list[str], b: list[str], winner_a: bool, cfg: Config) -> None:
    """Moment match independent player marginals after one binary observation."""
    sign = 1 if winner_a else -1
    delta = sum(state[p][0] for p in a) - sum(state[p][0] for p in b)
    c2 = 10 * cfg.beta**2 + sum(state[p][1] for p in a + b)
    c = math.sqrt(c2)
    t = sign * delta / c
    v = math.exp(-0.5 * t * t) / math.sqrt(2 * math.pi) / max(float(ndtr(t)), 1e-300)
    w = v * (v + t)
    for p, direction in [(p, sign) for p in a] + [(p, -sign) for p in b]:
        mu, var, last = state[p]
        state[p] = (mu + direction * var / c * v,
                    max(var * (1 - var / c2 * w), 1e-12), last)


def map_results(maps_a: int, maps_b: int) -> list[bool]:
    """Fixed alternating order from counts, without claiming observed map order."""
    results = []
    while maps_a or maps_b:
        if maps_a:
            results.append(True)
            maps_a -= 1
        if maps_b:
            results.append(False)
            maps_b -= 1
    return results


def replay(d: dict, cfg: Config, baseline: np.ndarray, stop_year: int | None = None) -> np.ndarray:
    state: dict[str, tuple[float, float, float]] = {}
    out = np.empty(len(d["y"]), dtype=float)
    out.fill(np.nan)
    for i in range(len(out)):
        if stop_year is not None and d["year"][i] > stop_year:
            break
        if d["tier"][i] != 1:
            out[i] = baseline[i]
            continue
        a, b = d["lineup_a"][i], d["lineup_b"][i]
        if len(a) != 5 or len(b) != 5 or len(set(a + b)) != 10:
            out[i] = baseline[i]
            continue
        day = float(d["days"][i])
        advance_idle(state, a + b, day, cfg)
        out[i] = model_lab.p_series(predict_map(a, b, state, cfg), int(d["best_of"][i]))
        # The prediction above is stored before any outcome-dependent update.
        if d["y"][i] == 0.5:
            continue
        if cfg.per_map and d["maps_a"][i] + d["maps_b"][i] > 0:
            for winner in map_results(int(d["maps_a"][i]), int(d["maps_b"][i])):
                adf_update(state, a, b, winner, cfg)
        else:
            adf_update(state, a, b, bool(d["y"][i]), cfg)
    return out


def mask(d: dict, years: tuple[int, ...]) -> np.ndarray:
    return (d["tier"] == 1) & (d["y"] != 0.5) & np.isin(d["year"], years)


def log_losses(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def logit_blend(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = np.clip(a, 1e-12, 1 - 1e-12), np.clip(b, 1e-12, 1 - 1e-12)
    z = 0.5 * (np.log(a / (1 - a)) + np.log(b / (1 - b)))
    return 1 / (1 + np.exp(-z))


def metrics(y: np.ndarray, p: np.ndarray, base: np.ndarray) -> dict:
    loss, base_loss = log_losses(y, p), log_losses(y, base)
    diff = base_loss - loss
    sd = float(diff.std(ddof=1)) if len(diff) > 1 else 0.0
    return {"n": len(y), "loss": float(loss.mean()), "brier": float(np.mean((p-y)**2)),
            "accuracy": float(np.mean((p >= .5) == y)),
            "t": float(diff.mean() * math.sqrt(len(diff)) / sd) if sd else 0.0,
            "ece": ece(y, p)}


def reliability(y: np.ndarray, p: np.ndarray) -> list[tuple[int, float, float]]:
    bins = np.minimum((p * 10).astype(int), 9)
    return [(int(np.sum(bins == k)), float(p[bins == k].mean()) if np.any(bins == k) else math.nan,
             float(y[bins == k].mean()) if np.any(bins == k) else math.nan) for k in range(10)]


def ece(y: np.ndarray, p: np.ndarray) -> float:
    return sum(n * abs(pred - actual) for n, pred, actual in reliability(y, p) if n) / len(y)


def verdict(rows: dict, baseline_rows: dict, candidate: str) -> str:
    years = (2025, 2026)
    if all(rows[(year, candidate)]["t"] > 2 and rows[(year, candidate)]["ece"] <= baseline_rows[year]["ece"] for year in years):
        return "WIN"
    if all(rows[(year, candidate)]["t"] > 0 for year in years):
        return "not proven"
    return "rejected"


def main() -> None:
    d = load_data()
    base = model_lab.run(d, model_lab.Config())
    reference = np.array([r["p_a_win"] for r in compute_elo(
        zip(d["match_id"], d["team_a"], d["team_b"], d["signal"]),
        k=elo_k(d["df"].tier))[0]])
    assert np.allclose(base, reference), "Elo baseline differs from production replay"
    validation = mask(d, (2023, 2024))
    best, best_loss = None, math.inf
    for cfg in GRID:
        p = replay(d, cfg, base, stop_year=2024)
        loss = float(log_losses(d["y"][validation], p[validation]).mean())
        if loss < best_loss:
            best, best_loss = cfg, loss
    assert best is not None
    print(f"Tuned on 2023-24 only: {best}; log loss {best_loss:.4f}", flush=True)
    pure = replay(d, best, base)
    blend = logit_blend(pure, base)
    rows, base_rows = {}, {}
    print("year model         n  log loss   Brier accuracy paired t    ECE")
    for year in (2023, 2024, 2025, 2026):
        m = mask(d, (year,))
        y, bp = d["y"][m], base[m]
        full = sum(len(d["lineup_a"][i]) == len(d["lineup_b"][i]) == 5
                   for i in np.flatnonzero(m))
        print(f"coverage {year}: {full}/{len(y)} full lineups")
        base_rows[year] = metrics(y, bp, bp)
        for name, p in (("Elo", base), ("pure", pure), ("blend", blend)):
            r = metrics(y, p[m], bp)
            rows[(year, name)] = r
            print(f"{year} {name:7} {r['n']:5d} {r['loss']:9.4f} {r['brier']:7.4f} "
                  f"{r['accuracy']:8.3f} {r['t']:8.2f} {r['ece']:7.4f}")
    for year in (2025, 2026):
        m = mask(d, (year,))
        print(f"\n{year} reliability: bin | Elo n/p/observed | pure n/p/observed | blend n/p/observed")
        tables = [reliability(d["y"][m], p[m]) for p in (base, pure, blend)]
        for k in range(10):
            def cell(v):
                n, pred, obs = v
                return f"{n:3d}/{pred:.3f}/{obs:.3f}" if n else "  0/  -  /  -  "
            print(f"{k/10:.1f}-{(k+1)/10:.1f} | " + " | ".join(cell(t[k]) for t in tables))
    for name in ("pure", "blend"):
        print(f"{name} verdict: {verdict(rows, base_rows, name)}")


if __name__ == "__main__":
    main()
