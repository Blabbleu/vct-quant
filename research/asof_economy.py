"""Offline, match-ID-ordered audit of prior team economy percentages; no scoring."""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from vct_quant import db  # noqa: E402
from vct_quant.features.build import match_sequence  # noqa: E402

WINDOW = 20
ECONOMY_SQL = """
SELECT match_id, team_id, team_name, CAST(full_buy_win_pct AS DOUBLE) AS full_buy_win_pct,
       CAST(pistol_win_pct AS DOUBLE) AS pistol_win_pct, raw_stats
FROM match_team_economy ORDER BY match_id, team_name
"""


def _name(value):
    return str(value).strip().lower()


def _side(key, name):
    return (key, _name(name))


def resolve(matches: pd.DataFrame, economy: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Map economy rows to sequence sides and report every failure or duplicate."""
    sides = {}
    for row in matches.itertuples(index=False):
        sides[int(row.match_id)] = (_side(row.team_a, row.team_a_name),
                                     _side(row.team_b, row.team_b_name))
    candidates = defaultdict(list)
    failures = defaultdict(int)
    for row in economy.itertuples(index=False):
        mid = int(row.match_id)
        pair = sides.get(mid)
        if pair is None:
            failures[(mid, "outside_match_sequence")] += 1
            continue
        if pd.notna(row.team_id):
            key = str(int(row.team_id))
            hits = [n for n, (side_key, _) in enumerate(pair) if side_key == key]
            reason = "team_id_mismatch"
            # Sequence sides can be name-keyed when their canonical ID is absent.
            # A stale economy ID must not prevent an otherwise exact name join.
            if not hits:
                name = _name(row.team_name)
                hits = [n for n, (side_key, side_name) in enumerate(pair)
                        if side_key.startswith("name:") and side_name == name]
        else:
            name = _name(row.team_name)
            hits = [n for n, (_, side_name) in enumerate(pair) if side_name == name]
            reason = "team_name_mismatch"
        if len(hits) != 1:
            failures[(mid, "ambiguous_side" if hits else reason)] += 1
            continue
        values = (float(row.full_buy_win_pct) if pd.notna(row.full_buy_win_pct) else None,
                  float(row.pistol_win_pct) if pd.notna(row.pistol_win_pct) else None)
        candidates[(mid, hits[0])].append(values)
    resolved = {}
    for key, values in candidates.items():
        if len(values) > 1:
            failures[(key[0], "duplicate_rows")] += len(values) - 1
        if len(set(values)) > 1:
            failures[(key[0], "conflicting_duplicates_excluded")] += len(values)
            continue
        resolved[key] = values[0]
    report = pd.DataFrame([{"match_id": mid, "reason": reason, "rows": n}
                           for (mid, reason), n in sorted(failures.items())],
                          columns=["match_id", "reason", "rows"])
    return resolved, report


def replay(matches: pd.DataFrame, economy: pd.DataFrame, window: int = WINDOW):
    """Emit pre-series means, then ingest only that completed series's economy."""
    if window < 1:
        raise ValueError("window must be positive")
    mids = [int(x) for x in matches.match_id]
    if any(b <= a for a, b in zip(mids, mids[1:])) or len(set(mids)) != len(mids):
        raise ValueError("match IDs must increase strictly")
    if (matches.team_a == matches.team_b).any():
        raise ValueError("identical side keys")
    resolved, failures = resolve(matches, economy)
    history = defaultdict(lambda: deque(maxlen=window))
    records = []
    for row in matches.itertuples(index=False):
        mid = int(row.match_id)
        record = {"match_id": mid}
        for suffix, key in (("a", row.team_a), ("b", row.team_b)):
            prior = history[key]
            record[f"prior_economy_rows_{suffix}"] = len(prior)
            for metric in ("full_buy", "pistol"):
                pos = 0 if metric == "full_buy" else 1
                values = [value[pos] for value in prior if value[pos] is not None]
                record[f"{metric}_win_pct_{suffix}"] = sum(values) / len(values) if values else float("nan")
                record[f"prior_{metric}_rows_{suffix}"] = len(values)
        record["full_buy_diff"] = record["full_buy_win_pct_a"] - record["full_buy_win_pct_b"]
        record["pistol_diff"] = record["pistol_win_pct_a"] - record["pistol_win_pct_b"]
        records.append(record)
        # Both stored series scores are required before the result may update history.
        if pd.isna(row.maps_a) or pd.isna(row.maps_b):
            continue
        for side, key in enumerate((row.team_a, row.team_b)):
            values = resolved.get((mid, side))
            if values is not None and any(value is not None for value in values):
                history[key].append(values)
    return pd.DataFrame.from_records(records, index=matches.index), failures


def coverage(matches: pd.DataFrame, features: pd.DataFrame,
             failures: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year in (2023, 2024, 2025, 2026):
        mask = matches.tier.eq(1) & matches.year.eq(year) & matches.score_a.isin((0.0, 1.0))
        f = features.loc[mask]
        both = f.prior_economy_rows_a.ge(3) & f.prior_economy_rows_b.ge(3)
        ids = set(int(x) for x in matches.loc[mask, "match_id"])
        failed = failures.loc[failures.match_id.isin(ids) & failures.reason.isin(("team_id_mismatch", "team_name_mismatch", "ambiguous_side")), "rows"].sum() if not failures.empty else 0
        rows.append({"year": year, "rows": int(mask.sum()),
                     "both_sides_3_prior_rows": int(both.sum()),
                     "join_failures": int(failed)})
    return pd.DataFrame(rows)


def audit():
    con = db.connect(read_only=True)
    try:
        matches = match_sequence(con).reset_index(drop=True)
        economy = con.execute(ECONOMY_SQL).df()
    finally:
        con.close()
    features, failures = replay(matches, economy)
    return coverage(matches, features, failures), failures, economy


if __name__ == "__main__":
    yearly, failures, economy = audit()
    print(yearly.to_string(index=False))
    print("economy rows:", len(economy))
    print("join/duplicate failures by reason:")
    print(failures.groupby("reason").rows.sum().to_string() if not failures.empty else "none")
