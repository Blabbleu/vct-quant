"""Model lab: four untried Elo extensions under one honest protocol.

    python scripts/model_lab.py            # full run, writes data/processed/model_lab.json

Candidates (each a strict superset of production Elo, so every knob at zero
reproduces it exactly -- asserted below):

  bo_aware   Ratings are *map* strength. P(series) = P(win best-of-n | p_map),
             so a Bo1 is closer to a coin flip than a Bo5 between the same
             teams, and the update counts maps won against maps expected.
  inactive   Rating regresses toward 1500 by elapsed calendar days since the
             team's last official match (dates exist for every Tier-1 match
             since late 2022; undated rows count as zero days).
  players    Each player carries an Elo that moves with his team's results.
             A team's strength blends team Elo with its lineup's mean player
             Elo, so a roster that swaps in proven players moves at once and
             a player keeps his rating when he changes org.
  calib      p' = sigmoid(a * logit(p)), `a` refit online on the trailing N
             scored Tier-1 matches that finished before this one.

Protocol (same as the other benchmarks): tune on 2023-24 Tier-1, then score
2025 and 2026 untouched, paired per-match t against production. Every year up
to 2026 has already been consulted by earlier experiments, so a pass here is
necessary, not sufficient -- the live prediction log is the final judge.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
import time
from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd

from vct_quant import db
from vct_quant.config import PROCESSED_DIR
from vct_quant.features.build import BEST_K, elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo

BASE = 1500.0
VALIDATION = (2023, 2024)
PERIODS = {"validation 2023-24": VALIDATION, "test 2025": (2025,), "confirm 2026": (2026,)}


@dataclass(frozen=True)
class Config:
    k: float = BEST_K
    bo_aware: bool = False
    map_scale: float = 400.0      # logistic scale of the per-map probability
    half_life_days: float = 0.0   # 0 = no inactivity decay
    player_weight: float = 0.0    # share of strength from lineup player Elo
    player_k: float = 0.0
    calib_window: int = 0         # 0 = no online calibration

    def label(self) -> str:
        parts = [f"K={self.k:g}"]
        if self.bo_aware:
            parts.append(f"bo-aware scale={self.map_scale:g}")
        if self.half_life_days:
            parts.append(f"half-life={self.half_life_days:g}d")
        if self.player_weight:
            parts.append(f"players w={self.player_weight:g} K_p={self.player_k:g}")
        if self.calib_window:
            parts.append(f"calib N={self.calib_window}")
        return ", ".join(parts)


def p_series(p_map: float, best_of: int) -> float:
    if best_of <= 1:
        return p_map
    wins = best_of // 2 + 1
    q = 1.0 - p_map
    return sum(math.comb(wins - 1 + l, l) * p_map**wins * q**l for l in range(wins))


def load() -> dict:
    con = db.connect(read_only=True)
    try:
        df = match_sequence(con).reset_index(drop=True)
        extra = con.execute(
            "SELECT match_id, best_of, completed_at FROM match"
        ).df()
        lineups = con.execute("""
            SELECT mm.match_id, s.team_number,
                   list(DISTINCT coalesce(CAST(s.player_id AS VARCHAR),
                                          'h:' || lower(trim(s.player_handle)))) AS roster
            FROM match_map_player_stat s JOIN match_map mm USING (match_map_id)
            GROUP BY 1, 2
        """).df()
    finally:
        con.close()
    df = df.merge(extra, on="match_id", how="left")
    rosters = {(int(m), int(t)): list(r) for m, t, r in lineups.itertuples(index=False)}

    total = (df.maps_a + df.maps_b).fillna(0)
    inferred = (2 * np.maximum(df.maps_a.fillna(0), df.maps_b.fillna(0)) - 1).clip(1, 5)
    best_of = df.best_of.fillna(inferred).astype(int)
    best_of = best_of.where(best_of.isin([1, 3, 5]), 3)  # Bo2 draws: scored as Bo3, never graded

    epoch = pd.Timestamp("2020-01-01", tz="UTC")
    days = ((df.completed_at - epoch).dt.total_seconds() / 86400).to_numpy()

    return {
        "df": df,
        "match_id": df.match_id.to_numpy(),
        "tier": df.tier.to_numpy(),
        "year": df.year.to_numpy(),
        "team_a": df.team_a.to_numpy(),
        "team_b": df.team_b.to_numpy(),
        "maps_a": df.maps_a.fillna(0).to_numpy(float),
        "maps_b": df.maps_b.fillna(0).to_numpy(float),
        "total": total.to_numpy(float),
        "signal": margin_signal(df).to_numpy(float),
        "y": df.score_a.to_numpy(float),
        "best_of": best_of.to_numpy(),
        "days": days,
        "lineup_a": [rosters.get((int(m), 1), []) for m in df.match_id],
        "lineup_b": [rosters.get((int(m), 2), []) for m in df.match_id],
    }


def run(d: dict, c: Config) -> np.ndarray:
    """One chronological replay; returns pre-match P(team A wins) for every row."""
    team: dict = {}
    player: dict = {}
    last_day: dict = {}
    out = np.empty(len(d["y"]))
    scale = c.map_scale if c.bo_aware else 400.0
    decay = math.log(2) / c.half_life_days if c.half_life_days else 0.0
    calib_hist: list[tuple[float, float]] = []   # (logit p_raw, y) for finished scored T1
    a_cache, a_every = 1.0, 25

    for i in range(len(out)):
        ta, tb, tier = d["team_a"][i], d["team_b"][i], d["tier"][i]
        k = c.k if tier == 1 else 0.0
        ra, rb = team.get(ta, BASE), team.get(tb, BASE)

        day = d["days"][i]
        if decay and k and day == day:
            for key in (ta, tb):
                prev = last_day.get(key)
                if prev is not None and day > prev:
                    f = math.exp(-decay * (day - prev))
                    team[key] = BASE + (team.get(key, BASE) - BASE) * f
            ra, rb = team.get(ta, BASE), team.get(tb, BASE)

        la, lb = d["lineup_a"][i], d["lineup_b"][i]
        sa, sb = ra, rb
        if c.player_weight and la and lb:
            pa = np.mean([player.setdefault(p, ra) for p in la])
            pb = np.mean([player.setdefault(p, rb) for p in lb])
            w = c.player_weight
            sa, sb = (1 - w) * ra + w * pa, (1 - w) * rb + w * pb

        p_map = 1.0 / (1.0 + 10.0 ** ((sb - sa) / scale))
        p = p_series(p_map, d["best_of"][i]) if c.bo_aware else p_map

        if c.calib_window:
            if len(calib_hist) >= 50 and i % a_every == 0:
                a_cache = _fit_a(calib_hist[-c.calib_window:])
            z = math.log(p / (1 - p))
            out[i] = 1 / (1 + math.exp(-a_cache * z))
        else:
            out[i] = p

        if k:
            if c.bo_aware and d["total"][i] > 0:
                delta = k * (d["maps_a"][i] - p_map * d["total"][i]) / d["total"][i]
            else:
                delta = k * (d["signal"][i] - p)
            team[ta], team[tb] = ra + delta, rb - delta
            if c.player_k and la and lb:
                dp = c.player_k * delta / k
                for pl in la:
                    player[pl] = player.get(pl, ra) + dp
                for pl in lb:
                    player[pl] = player.get(pl, rb) - dp
            if day == day:
                last_day[ta] = last_day[tb] = day
            if tier == 1 and d["y"][i] != 0.5 and c.calib_window:
                calib_hist.append((math.log(p / (1 - p)), d["y"][i]))
    return out


_GRID_A = np.linspace(0.4, 1.6, 61)


def _fit_a(hist: list[tuple[float, float]]) -> float:
    z = np.array([h[0] for h in hist])
    y = np.array([h[1] for h in hist])
    best, best_loss = 1.0, np.inf
    for a in _GRID_A:
        p = np.clip(1 / (1 + np.exp(-a * z)), 1e-12, 1 - 1e-12)
        loss = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
        if loss < best_loss:
            best, best_loss = a, loss
    return float(best)


def losses(d: dict, p: np.ndarray, years: tuple[int, ...]) -> np.ndarray:
    y = d["y"]
    m = (d["tier"] == 1) & (y != 0.5) & np.isin(d["year"], years)
    pp = np.clip(p[m], 1e-12, 1 - 1e-12)
    return -(y[m] * np.log(pp) + (1 - y[m]) * np.log(1 - pp))


def compare(d: dict, base: np.ndarray, cand: np.ndarray) -> dict:
    res = {}
    for name, years in PERIODS.items():
        lb, lc = losses(d, base, years), losses(d, cand, years)
        diff = lb - lc
        sd = diff.std(ddof=1)
        y = d["y"][(d["tier"] == 1) & (d["y"] != 0.5) & np.isin(d["year"], years)]
        pc = cand[(d["tier"] == 1) & (d["y"] != 0.5) & np.isin(d["year"], years)]
        res[name] = {
            "n": int(len(diff)),
            "baseline": float(lb.mean()),
            "candidate": float(lc.mean()),
            "brier": float(np.mean((pc - y) ** 2)),
            "t": float(diff.mean() / (sd / math.sqrt(len(diff)))) if sd else 0.0,
        }
    held = np.concatenate([losses(d, base, (2025, 2026)) - losses(d, cand, (2025, 2026))])
    res["held-out 2025+26"] = {
        "n": int(len(held)),
        "gain": float(held.mean()),
        "t": float(held.mean() / (held.std(ddof=1) / math.sqrt(len(held)))) if held.std() else 0.0,
    }
    return res


def tune(d: dict, grid: list[Config], name: str) -> tuple[Config, np.ndarray, float]:
    best = None
    t0 = time.time()
    for c in grid:
        p = run(d, c)
        v = losses(d, p, VALIDATION).mean()
        if best is None or v < best[2]:
            best = (c, p, v)
    print(f"  {name}: {len(grid)} configs in {time.time() - t0:.0f}s -> {best[0].label()}"
          f"  (val {best[2]:.4f})", flush=True)
    return best


def main() -> int:
    d = load()
    base_cfg = Config()
    base = run(d, base_cfg)
    ref = np.array([r["p_a_win"] for r in compute_elo(
        zip(d["match_id"], d["team_a"], d["team_b"], d["signal"]), k=elo_k(d["df"].tier)
    )[0]])
    assert np.allclose(base, ref), "harness does not reproduce production Elo"
    print("harness reproduces production Elo exactly\n")

    base_val = losses(d, base, VALIDATION).mean()
    print(f"baseline validation 2023-24: {base_val:.4f}\n\nTuning on 2023-24:")
    K = (40.0, 48.0, 56.0)
    families = {
        "bo_aware": [Config(k=k, bo_aware=True, map_scale=s)
                     for k in K for s in (250.0, 300.0, 350.0, 400.0, 500.0)],
        "inactive": [Config(half_life_days=h) for h in (60, 90, 120, 180, 270, 365, 540, 730)],
        "players": [Config(player_weight=w, player_k=pk)
                    for w in (0.25, 0.5, 0.75, 1.0) for pk in (24.0, 48.0, 72.0)],
        "calib": [Config(calib_window=n) for n in (150, 300, 500, 800)],
    }
    tuned = {name: tune(d, grid, name) for name, grid in families.items()}

    # Combine every family that beat baseline on validation, tuned jointly on a
    # small neighbourhood so interactions are not assumed away.
    winners = {n: c for n, (c, _, v) in tuned.items() if v < base_val}
    combo = None
    if len(winners) > 1:
        seed = Config()
        for c in winners.values():
            seed = replace(seed, **{f: getattr(c, f) for f in asdict(c)
                                    if getattr(c, f) != getattr(Config(), f)})
        neigh = [seed]
        if seed.bo_aware:
            neigh += [replace(seed, map_scale=s) for s in (seed.map_scale - 50, seed.map_scale + 50)]
        if seed.player_weight:
            neigh += [replace(seed, player_weight=w) for w in (0.25, 0.5, 0.75) if w != seed.player_weight]
        if seed.half_life_days:
            neigh += [replace(seed, half_life_days=h) for h in (seed.half_life_days / 1.5, seed.half_life_days * 1.5)]
        combo = tune(d, neigh, "combined")

    results = {"baseline": {"config": asdict(base_cfg), "validation": float(base_val)}}
    print("\n" + "=" * 96)
    rows = [(n, c, p) for n, (c, p, _) in tuned.items()]
    if combo:
        rows.append(("combined", combo[0], combo[1]))
    for name, c, p in rows:
        r = compare(d, base, p)
        results[name] = {"config": asdict(c), "label": c.label(), **r}
        print(f"\n{name}: {c.label()}")
        print(f"  {'period':20} {'n':>5} {'baseline':>9} {'model':>9} {'brier':>7} {'paired t':>9}")
        for period in PERIODS:
            x = r[period]
            print(f"  {period:20} {x['n']:5d} {x['baseline']:9.4f} {x['candidate']:9.4f}"
                  f" {x['brier']:7.4f} {x['t']:+9.2f}")
        h = r["held-out 2025+26"]
        print(f"  {'held-out 2025+26':20} {h['n']:5d}  gain {h['gain']:+.4f} log loss/match, t={h['t']:+.2f}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / "model_lab.json"
    path.write_text(json.dumps(results, indent=2))
    print(f"\n-> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
