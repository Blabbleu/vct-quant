"""Game Changers signal / newcomer lab (protocol: docs/gc-signal-lab.md).

    python scripts/gc_signal_lab.py tune    # years <= 2024 only; prints the selection
    python scripts/gc_signal_lab.py test    # scores 2025-26 once, only if the
                                            # selection differs from margin K=192

Read-only: opens the DB read_only through `match_sequence`. Changes nothing in
production; any proposal needs the owner's approval.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

TUNE_THROUGH = 2024
BASE = 1500.0
PROVISIONAL_GAMES = 10
SHIP_T = 2.0
REFERENCE = ("M", 192.0, 0.0, 1.0)  # A73 candidate
PRODUCTION = ("M", 48.0, 0.0, 1.0)

K_WIDE = [16.0, 24.0, 32.0, 48.0, 64.0, 96.0, 128.0, 192.0, 256.0, 384.0, 512.0]
K_NARROW = [64.0, 96.0, 128.0, 192.0, 256.0]
# Amendment 1: newcomer seed = current pool mean + delta (a fixed r0 for every
# team is a pure translation, which Elo ignores).
DELTAS = [-50.0, -100.0, -150.0, -200.0, -250.0, -300.0]
MULTS = [1.5, 2.0, 3.0]


def configs() -> list[tuple[str, float, float, float]]:
    """(family, K, newcomer seed offset from the pool mean, provisional K mult)."""
    out = [("M", k, 0.0, 1.0) for k in K_WIDE]
    out += [("B", k, 0.0, 1.0) for k in K_WIDE]
    out += [("N", k, d, 1.0) for d in DELTAS for k in K_NARROW]
    out += [("P", k, 0.0, m) for m in MULTS for k in K_NARROW]
    return out


def signal(df: pd.DataFrame, family: str) -> np.ndarray:
    from vct_quant.features.build import margin_signal

    if family == "B":
        return df.score_a.to_numpy(dtype=float)
    return margin_signal(df).to_numpy(dtype=float)


def replay(team_a, team_b, s, k: float, delta: float = 0.0, mult: float = 1.0,
           provisional: int = PROVISIONAL_GAMES) -> np.ndarray:
    """Pre-match P(A wins).

    A team entering the pool is seeded at the current mean rating of already
    rated teams + `delta` (BASE while the pool is empty; both sides of a match
    are seeded from the mean before that match). Per-side K: K*mult while a
    side has < `provisional` prior matches. With delta=0 and mult=1 this is
    exactly `compute_elo` (zero-sum updates keep the mean at BASE).
    """
    ratings: dict = {}
    games: dict = {}
    total = 0.0
    p = np.empty(len(s))
    for i, (a, b, sa) in enumerate(zip(team_a, team_b, s)):
        seed = (total / len(ratings) + delta) if ratings else BASE
        for t in (a, b):
            if t not in ratings:
                ratings[t] = seed
                total += seed
        ra = ratings[a]
        rb = ratings[b]
        e = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))
        p[i] = e
        ga = games.get(a, 0)
        gb = games.get(b, 0)
        ka = k * mult if ga < provisional else k
        kb = k * mult if gb < provisional else k
        ratings[a] = ra + ka * (sa - e)
        ratings[b] = rb - kb * (sa - e)
        total += (ka - kb) * (sa - e)
        games[a] = ga + 1
        games[b] = gb + 1
    return p


def per_match_loss(y, p) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-15, 1 - 1e-15)
    y = np.asarray(y, dtype=float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def paired_t(loss_base, loss_new) -> float:
    """Positive = new is better."""
    diff = np.asarray(loss_base) - np.asarray(loss_new)
    if len(diff) < 2:
        return float("nan")
    sd = diff.std(ddof=1)
    if sd == 0:
        return float("nan")
    return float(diff.mean() / (sd / np.sqrt(len(diff))))


def predict(df: pd.DataFrame, cfg) -> np.ndarray:
    family, k, delta, mult = cfg
    return replay(df.team_a.to_numpy(), df.team_b.to_numpy(), signal(df, family),
                  k, delta, mult)


def select(losses: dict) -> tuple:
    """Lowest tune loss; ties go to the reference, then to the earlier config."""
    order = configs()
    return min(order, key=lambda c: (losses[c], c != REFERENCE, order.index(c)))


def tune(df: pd.DataFrame) -> dict:
    y = df.score_a.to_numpy(dtype=float)
    mask = (y != 0.5) & df.year.le(TUNE_THROUGH).to_numpy()
    losses = {c: float(per_match_loss(y[mask], predict(df, c)[mask]).mean())
              for c in configs()}
    return {"n": int(mask.sum()), "losses": losses, "selected": select(losses)}


def test(df: pd.DataFrame, cfg) -> dict:
    from vct_quant.eval import metrics

    if tuple(cfg) == REFERENCE:
        raise ValueError("selection is the A73 reference: protocol says do not score")
    y = df.score_a.to_numpy(dtype=float)
    mask = (y != 0.5) & df.year.gt(TUNE_THROUGH).to_numpy()
    pr, pp, pc = (predict(df, c)[mask] for c in (REFERENCE, PRODUCTION, cfg))
    ym = y[mask]
    lr, lp, lc = (per_match_loss(ym, p) for p in (pr, pp, pc))
    out = {"n": int(mask.sum()), "cfg": list(cfg),
           "loss_ref": float(lr.mean()), "loss_prod": float(lp.mean()),
           "loss_cfg": float(lc.mean()),
           "t_vs_ref": paired_t(lr, lc), "t_vs_prod": paired_t(lp, lc),
           "brier_ref": float(((pr - ym) ** 2).mean()),
           "brier_cfg": float(((pc - ym) ** 2).mean()), "by_year": {}}
    years = df.year.to_numpy()[mask]
    for yr in sorted(set(years.tolist())):
        m = years == yr
        out["by_year"][int(yr)] = {"n": int(m.sum()), "loss_ref": float(lr[m].mean()),
                                   "loss_cfg": float(lc[m].mean()),
                                   "t": paired_t(lr[m], lc[m])}
    out["calibration_cfg"] = metrics.calibration_table(ym, pc).to_dict("records")
    out["propose"] = bool(out["t_vs_ref"] >= SHIP_T)
    return out


def fmt(cfg) -> str:
    family, k, delta, mult = cfg
    return f"{family} K={k:g} delta={delta:g} mult={mult:g}"


def main() -> None:
    from vct_quant.features.build import match_sequence

    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["tune", "test"])
    args = ap.parse_args()
    df = match_sequence(tiers=(3,))
    print(f"GC matches {len(df):,}")
    res = tune(df)
    best_by_family: dict = {}
    for c, loss in res["losses"].items():
        if c[0] not in best_by_family or loss < res["losses"][best_by_family[c[0]]]:
            best_by_family[c[0]] = c
    if args.stage == "tune":
        for c in configs():
            print(f"{fmt(c):32s} tune log loss {res['losses'][c]:.6f}")
        print("\nbest per family:")
        for fam, c in best_by_family.items():
            print(f"  {fmt(c):32s} {res['losses'][c]:.6f}")
        sel = res["selected"]
        print(json.dumps({"tune_n": res["n"], "selected": fmt(sel),
                          "is_reference": sel == REFERENCE,
                          "ref_loss": res["losses"][REFERENCE],
                          "sel_loss": res["losses"][sel]}))
        return
    out = test(df, res["selected"])
    print(json.dumps({k: v for k, v in out.items() if k != "calibration_cfg"}, indent=1))
    for row in out["calibration_cfg"]:
        print(f"  {str(row['bucket']):>14}  n={row['n']:5d}  pred {row['predicted']:.3f}  "
              f"actual {row['actual']:.3f}")
    print(f"\ndecision (frozen rule t >= {SHIP_T} vs margin K=192): "
          f"{'PROPOSE ' + fmt(res['selected']) if out['propose'] else 'A73 stands'}")


if __name__ == "__main__":
    main()
