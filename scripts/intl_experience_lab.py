"""International-experience lab (protocol: docs/intl-experience.md, frozen first).

    python scripts/intl_experience_lab.py     # writes data/processed/intl_experience_lab.json

Feature: per side, mean over the match's lineup of log1p(international maps
the player played in strictly earlier matches). Gap x = exp_a - exp_b.
Candidate: p' = sigmoid(logit(p_elo) + beta * x); A = all Tier-1 matches,
B = only matches at international events. beta tuned on 2023-24, scored once
on 2025 and 2026 against production Elo (paired per-match log-loss t).
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict

import numpy as np
import pandas as pd

from vct_quant import db
from vct_quant.config import PROCESSED_DIR
from vct_quant.features.build import build_features

VALIDATION = (2023, 2024)
TEST_YEARS = (2025, 2026)
GRID = [round(b, 2) for b in np.arange(-0.60, 0.6001, 0.02)]

_INTL = re.compile(r"(^valorant champions \d{4}$)|(masters [a-zà-ÿ]+)|(lock//in)", re.I)
_REGIONAL_MASTERS = re.compile(r": masters$", re.I)


def is_international(name: str | None) -> bool:
    """Champions <year>, Masters <City>, LOCK//IN; not 2021 regional 'Stage 1: Masters'."""
    if not name:
        return False
    name = name.strip()
    return bool(_INTL.search(name)) and not _REGIONAL_MASTERS.search(name)


_STATS_SQL = """
SELECT mm.match_id, s.team_number,
       coalesce(CAST(s.player_id AS VARCHAR), 'h:' || lower(trim(s.player_handle))) AS player_key,
       count(*) AS maps
FROM match_map_player_stat s
JOIN match_map mm USING (match_map_id)
JOIN match m USING (match_id)
JOIN event e USING (event_id)
WHERE e.tier IN (1, 2)
GROUP BY 1, 2, 3
ORDER BY 1
"""

_EVENTS_SQL = """
SELECT m.match_id, e.name AS event_name
FROM match m JOIN event e USING (event_id)
WHERE e.tier IN (1, 2)
"""


def experience_gap(matches: pd.DataFrame, stats: pd.DataFrame, intl_ids: set[int]) -> pd.DataFrame:
    """Point-in-time lineup experience per side; history updates after both sides are read."""
    by_match = {int(k): g for k, g in stats.groupby("match_id", sort=False)}
    maps_played: dict[str, int] = defaultdict(int)
    rows = []
    for match_id in matches.match_id:
        mid = int(match_id)
        cur = by_match.get(mid)
        exp = {}
        for side in (1, 2):
            if cur is None:
                exp[side] = None
                continue
            lineup = cur.loc[cur.team_number.eq(side), "player_key"].drop_duplicates().tolist()
            exp[side] = (sum(math.log1p(maps_played[p]) for p in lineup) / len(lineup)) if lineup else None
        gap = 0.0 if exp[1] is None or exp[2] is None else exp[1] - exp[2]
        rows.append({"match_id": mid, "exp_a": exp[1], "exp_b": exp[2], "gap": gap,
                     "intl_match": mid in intl_ids})
        if cur is not None and mid in intl_ids:  # update only after the pre-match row exists
            for player, n in zip(cur.player_key, cur.maps):
                maps_played[player] += int(n)
    return pd.DataFrame(rows)


def _ll(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def adjust(p: np.ndarray, gap: np.ndarray, beta: float, mask: np.ndarray) -> np.ndarray:
    logit = np.log(np.clip(p, 1e-15, 1 - 1e-15) / np.clip(1 - p, 1e-15, 1))
    return 1 / (1 + np.exp(-(logit + beta * gap * mask)))


def paired_t(a: np.ndarray, b: np.ndarray) -> float:
    """t of mean(b - a) where a is production loss and b candidate: positive = candidate better."""
    d = a - b
    if len(d) < 3 or d.std(ddof=1) == 0:
        return float("nan")
    return float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d))))


def main() -> None:
    con = db.connect(read_only=True)
    try:
        feats = build_features(con)
        stats = con.execute(_STATS_SQL).df()
        events = con.execute(_EVENTS_SQL).df()
    finally:
        con.close()
    intl_ids = {int(m) for m, n in zip(events.match_id, events.event_name) if is_international(n)}
    order = feats.sort_values("match_id").reset_index(drop=True)
    gap = experience_gap(order[["match_id"]], stats, intl_ids)
    df = order.merge(gap, on="match_id", how="left")
    df = df[df.tier.eq(1) & df.year.notna()].copy()
    y = df.label.to_numpy(float)
    p = df.elo_p_a_win.to_numpy(float)
    x = df.gap.fillna(0).to_numpy(float)
    intl = df.intl_match.fillna(False).to_numpy(bool)
    year = df.year.astype(int).to_numpy()

    out = {"protocol": "docs/intl-experience.md", "n_intl_matches_all_years": int(len(intl_ids)),
           "coverage": {}, "candidates": {}}
    for yr in sorted(set(year)):
        m = year == yr
        out["coverage"][str(yr)] = {"tier1": int(m.sum()), "intl": int((m & intl).sum()),
                                    "gap_nonzero": int((m & (x != 0)).sum())}

    base_ll = _ll(y, p)
    for name, mask in (("A_all", np.ones_like(intl, dtype=float)), ("B_intl_only", intl.astype(float))):
        val = np.isin(year, VALIDATION) & (mask > 0)
        scores = {b: float(_ll(y[val], adjust(p[val], x[val], b, mask[val])).mean()) for b in GRID}
        beta = min(scores, key=lambda b: (scores[b], abs(b)))
        cand = _ll(y, adjust(p, x, beta, mask))
        res = {"beta": beta, "validation_ll": scores[beta], "validation_elo": float(base_ll[val].mean()),
               "validation_n": int(val.sum()), "test": {}}
        pooled = np.isin(year, TEST_YEARS) & (mask > 0)
        for label, sel in [(str(t), (year == t) & (mask > 0)) for t in TEST_YEARS] + [("2025+26", pooled)]:
            res["test"][label] = {"n": int(sel.sum()), "elo": float(base_ll[sel].mean()),
                                  "candidate": float(cand[sel].mean()),
                                  "paired_t": paired_t(base_ll[sel], cand[sel])}
        out["candidates"][name] = res

    # Descriptive: the motivating match, reported but not evidence.
    ge = df[df.match_id.eq(753449)]
    if not ge.empty:
        out["ge_vs_vit"] = ge[["exp_a", "exp_b", "gap", "elo_p_a_win"]].iloc[0].to_dict()

    path = PROCESSED_DIR / "intl_experience_lab.json"
    path.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
