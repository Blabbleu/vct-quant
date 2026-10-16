"""As-of Kaggle map veto profile and coverage audit; no model scoring."""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from research import asof_economy_kaggle as kaggle  # noqa: E402
from vct_quant import db  # noqa: E402
from vct_quant.features.build import match_sequence  # noqa: E402

KEY = kaggle.KEY
RAW = kaggle.RAW
WINDOW = 20
FAIL_COLUMNS = ["year", *KEY, "match_id", "team_name", "reason"]


def load_raw(raw: Path = RAW) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Follow the economy audit's year-folder load and ID bridge convention."""
    drafts, scores, ids = [], [], []
    for year in range(2021, 2027):
        base = raw / f"vct_{year}"
        for target, name in ((drafts, "draft_phase"), (scores, "maps_scores")):
            frame = pd.read_csv(base / f"matches/{name}.csv")
            frame["year"] = year
            target.append(frame)
        bridge = pd.read_csv(base / "ids/tournaments_stages_matches_games_ids.csv")
        bridge["year"] = year
        ids.append(bridge)
    return tuple(pd.concat(frames, ignore_index=True) for frames in (drafts, scores, ids))


def build_series(matches: pd.DataFrame, drafts: pd.DataFrame, scores: pd.DataFrame,
                 ids: pd.DataFrame) -> tuple[dict, dict, pd.DataFrame]:
    """Resolve raw draft sides and played map results through the shared ID bridge."""
    drafts = drafts.drop_duplicates().copy()
    scores = scores.drop_duplicates().copy()
    bridge = kaggle.match_id_bridge(ids, ["year", *KEY])
    pairs = kaggle.sequence_pairs(matches)
    failures = []

    def fail(row, reason, team_name=None, match_id=None):
        failures.append({"year": int(row["year"]), **{k: row[k] for k in KEY},
                         "match_id": match_id, "team_name": team_name, "reason": reason})

    def resolve(row, name=None):
        key = (row["year"], *(row[k] for k in KEY))
        mids = bridge.get(key, ())
        if not mids:
            fail(row, "no_id_bridge")
            return None
        if len(mids) != 1:
            fail(row, "ambiguous_id_bridge")
            return None
        mid = mids[0]
        pair = pairs.get(mid)
        if pair is None:
            fail(row, "outside_match_sequence", match_id=mid)
            return None
        if name is None:
            return mid, None
        side, reason = kaggle.matched_side(pair, name)
        if reason is not None:
            fail(row, reason,
                 team_name=name, match_id=mid)
            return None
        return mid, side

    pools = {name: frozenset(group.Map.dropna())
             for name, group in drafts.groupby("Tournament", dropna=False)}
    series = defaultdict(lambda: defaultdict(lambda: {"bans": set(), "draft": False,
                                                   "results": []}))
    valid = set()
    for _, row in drafts.iterrows():
        result = resolve(row, row["Team"])
        if result is None:
            continue
        mid, side = result
        action = kaggle._norm(row["Action"])
        if action not in ("ban", "pick"):
            fail(row, "unknown_action", team_name=row["Team"], match_id=mid)
            continue
        item = series[mid][side]
        item["draft"] = True
        if action == "ban":
            item["bans"].add(row["Map"])
        valid.add(mid)

    seen_maps = set()
    for _, row in scores.iterrows():
        result = resolve(row)
        if result is None:
            continue
        mid, _ = result
        if mid not in valid:
            continue
        # Year folders can overlap. One played map must contribute only once.
        map_key = (mid, row["Map"])
        if map_key in seen_maps:
            continue
        a = resolve(row, row["Team A"])
        b = resolve(row, row["Team B"])
        if a is None or b is None:
            continue
        if a[1] == b[1]:
            fail(row, "ambiguous_team", match_id=mid)
            continue
        sa = pd.to_numeric(row["Team A Score"], errors="coerce")
        sb = pd.to_numeric(row["Team B Score"], errors="coerce")
        if pd.isna(sa) or pd.isna(sb) or sa == sb:
            fail(row, "unresolved_map_result", match_id=mid)
            continue
        seen_maps.add(map_key)
        # A score row contributes once to each team's map profile.
        for side, win in ((a[1], sa > sb), (b[1], sb > sa)):
            series[mid][side]["results"].append((row["Map"], int(win)))

    tournament = {}
    for _, row in drafts.iterrows():
        result = resolve(row)
        if result is not None:
            tournament[result[0]] = row["Tournament"]
    frame = pd.DataFrame(failures, columns=FAIL_COLUMNS).drop_duplicates()
    return dict(series), {mid: pools[name] for mid, name in tournament.items()}, frame


def replay(matches: pd.DataFrame, series: dict, pools: dict,
           window: int = WINDOW) -> pd.DataFrame:
    """Emit each match's prior profile before ingesting its completed draft."""
    if window < 1:
        raise ValueError("window must be positive")
    mids = [int(x) for x in matches.match_id]
    if any(b <= a for a, b in zip(mids, mids[1:])):
        raise ValueError("match IDs must increase strictly")
    if (matches.team_a == matches.team_b).any():
        raise ValueError("identical side keys")
    history = defaultdict(lambda: deque(maxlen=window))
    records = []
    for row in matches.itertuples(index=False):
        mid = int(row.match_id)
        prior = [history[row.team_a], history[row.team_b]]
        record = {"match_id": mid, "prior_draft_series_a": len(prior[0]),
                  "prior_draft_series_b": len(prior[1]), "veto_edge": np.nan}
        pool = pools.get(mid, ())
        if pool:
            edge, total = 0.0, 0.0
            for map_name in pool:
                values = []
                for side_history in prior:
                    n = len(side_history)
                    bans = sum(map_name in item["bans"] for item in side_history)
                    played = [(name, win) for item in side_history
                              for name, win in item["results"] if name == map_name]
                    values.append((bans / n if n else 0.0,
                                   (sum(win for _, win in played) + 2.5) / (len(played) + 5)))
                weight = (1 - values[0][0]) * (1 - values[1][0])
                edge += weight * (values[0][1] - values[1][1])
                total += weight
            if total > 0:
                record["veto_edge"] = edge / total
        records.append(record)
        if pd.isna(row.maps_a) or pd.isna(row.maps_b):
            continue
        for side, key in enumerate((row.team_a, row.team_b)):
            item = series.get(mid, {}).get(side)
            if item is not None and item["draft"]:
                history[key].append(item)
    return pd.DataFrame.from_records(records, index=matches.index)


def coverage(matches: pd.DataFrame, features: pd.DataFrame,
             failures: pd.DataFrame) -> pd.DataFrame:
    records = []
    for year in range(2023, 2027):
        mask = matches.year.eq(year) & matches.tier.eq(1) & matches.score_a.isin((0.0, 1.0))
        f = features.loc[mask]
        ready = (f.prior_draft_series_a.ge(3) & f.prior_draft_series_b.ge(3)
                 & np.isfinite(f.veto_edge))
        bad = failures.loc[failures.year.eq(year)]
        records.append({"year": year, "decisive_tier1": int(mask.sum()),
                        "eligible": int(ready.sum()),
                        "failed_series": len(bad.loc[bad.team_name.isna(), ["year", *KEY]].drop_duplicates()),
                        "unmapped_team_names": int(bad.loc[bad.team_name.notna(), "team_name"].map(kaggle._norm).nunique())})
    return pd.DataFrame(records)


def audit(raw: Path = RAW):
    con = db.connect(read_only=True)
    try:
        matches = match_sequence(con).reset_index(drop=True)
    finally:
        con.close()
    drafts, scores, ids = load_raw(raw)
    series, pools, failures = build_series(matches, drafts, scores, ids)
    features = replay(matches, series, pools)
    return coverage(matches, features, failures), failures, features


if __name__ == "__main__":
    yearly, failures, _ = audit()
    print(yearly.to_string(index=False))
    print("join failures by reason:")
    print(failures.groupby(["year", "reason"]).size().to_string() if not failures.empty else "none")
    print("unmapped team names:")
    print(failures.loc[failures.reason.eq("team_name_mismatch"), ["year", "team_name"]].drop_duplicates().to_string(index=False))
