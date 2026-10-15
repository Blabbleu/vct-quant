"""Offline, match-ID-ordered audit of genuinely prior lineup player form."""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from vct_quant import db  # noqa: E402
from vct_quant.features.build import (  # noqa: E402
    _player_form_from_stats, match_sequence,
)

IDENTITY_SQL = """
SELECT mm.match_id, mm.match_map_id AS map_id, s.team_number,
       s.team_id AS score_team_id, mt.team_id AS match_team_id,
       mt.team_name AS match_team_name
FROM match_map mm
LEFT JOIN match_map_team_score s ON s.match_map_id = mm.match_map_id
LEFT JOIN match_team mt ON mt.match_id = mm.match_id
                            AND mt.team_number = s.team_number
ORDER BY mm.match_id, mm.match_map_id, s.team_number
"""
STATS_SQL = """
SELECT mm.match_id, mm.match_map_id AS map_id, s.team_number, s.player_slot,
       coalesce(CAST(s.player_id AS VARCHAR),
                'h:' || lower(trim(s.player_handle))) AS player_key,
       CAST(s.rating AS DOUBLE) AS rating
FROM match_map_player_stat s
JOIN match_map mm ON mm.match_map_id = s.match_map_id
ORDER BY mm.match_id, mm.match_map_id, s.team_number, s.player_slot
"""


def _key(team_id, name):
    if pd.notna(team_id):
        return str(int(team_id))
    return "name:" + str(name).strip().lower()


def replay(matches: pd.DataFrame, identities: pd.DataFrame,
           stats: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Emit both sides before ingesting each match; never inspect its result."""
    if window < 1:
        raise ValueError("window must be positive")
    mids = [int(x) for x in matches.match_id]
    if any(b <= a for a, b in zip(mids, mids[1:])) or len(set(mids)) != len(mids):
        raise ValueError("match IDs must increase strictly")
    if (matches.team_a == matches.team_b).any():
        raise ValueError("identical side keys")
    maps_by_match = {int(k): g for k, g in identities.groupby("match_id", sort=False)}
    stats_by_map = {k: g for k, g in stats.groupby("map_id", sort=False)}
    history = defaultdict(lambda: deque(maxlen=window))
    last = {}
    records = []
    for match in matches.itertuples(index=False):
        mid = int(match.match_id)
        record = {"match_id": mid}
        for key, suffix in ((match.team_a, "a"), (match.team_b, "b")):
            lineup = last.get(key)
            complete = lineup is not None
            player_means = [sum(history[p]) / len(history[p]) for p in lineup if history[p]] if complete else []
            lacking = 5 - len(player_means) if complete else 0
            record[f"prior_lineup_{suffix}"] = complete
            record[f"player_form_{suffix}"] = sum(player_means) / len(player_means) if player_means else float("nan")
            record[f"players_lacking_ratings_{suffix}"] = lacking
            record[f"rating_coverage_{suffix}"] = len(player_means) / 5 if complete else 0.0
            record[f"player_form_missing_{suffix}"] = not bool(player_means)
        record["player_form_diff"] = record["player_form_a"] - record["player_form_b"]
        records.append(record)

        # All current-match inspection occurs after the record is complete.
        map_rows = maps_by_match.get(mid)
        if map_rows is None:
            continue
        side_lineups = {1: [], 2: []}
        side_valid = {1: True, 2: True}
        map_ids = list(dict.fromkeys(map_rows.map_id))
        for map_id in map_ids:
            identity = map_rows.loc[map_rows.map_id.eq(map_id)]
            current_stats = stats_by_map.get(map_id)
            valid_map = len(identity) == 2 and set(identity.team_number) == {1, 2}
            if valid_map:
                for side, key in ((1, match.team_a), (2, match.team_b)):
                    row = identity.loc[identity.team_number.eq(side)].iloc[0]
                    if (_key(row.match_team_id, row.match_team_name) != key
                            or (pd.notna(row.score_team_id) and
                                (pd.isna(row.match_team_id) or
                                 int(row.score_team_id) != int(row.match_team_id)))):
                        valid_map = False
            if current_stats is not None and not current_stats.team_number.isin([1, 2]).all():
                valid_map = False
            if not valid_map:
                side_valid[1] = side_valid[2] = False
                continue
            for side in (1, 2):
                side_stats = (current_stats.loc[current_stats.team_number.eq(side)]
                              if current_stats is not None else stats.iloc[:0])
                players = side_stats.player_key
                slots = side_stats.player_slot
                if (len(side_stats) != 5 or players.isna().any() or
                        players.nunique() != 5 or slots.isna().any() or slots.nunique() != 5):
                    side_valid[side] = False
                    continue
                lineup = frozenset(players)
                side_lineups[side].append(lineup)
                # Deliberate: every individually validated side-map is genuine
                # player history, even if another map blocks the lineup update.
                for row in side_stats.itertuples(index=False):
                    if pd.notna(row.rating):
                        history[row.player_key].append(float(row.rating))
        for side, key in ((1, match.team_a), (2, match.team_b)):
            lineups = side_lineups[side]
            if side_valid[side] and len(lineups) == len(map_ids) and len(set(lineups)) == 1:
                last[key] = lineups[0]
    return pd.DataFrame.from_records(records, index=matches.index)


def coverage(matches: pd.DataFrame, features: pd.DataFrame,
             current_form: pd.DataFrame | None = None,
             current_complete: pd.Series | None = None) -> pd.DataFrame:
    """Yearly Tier-1 coverage; missing sides and ratings count sides/players."""
    rows = []
    for year in (2023, 2024, 2025, 2026):
        mask = matches.tier.eq(1) & matches.year.eq(year)
        f = features.loc[mask]
        prior = f.prior_lineup_a.astype(bool).sum() + f.prior_lineup_b.astype(bool).sum()
        both = f.prior_lineup_a & f.prior_lineup_b
        available = f.player_form_a.notna() & f.player_form_b.notna()
        row = {"year": year, "rows": int(mask.sum()),
               "complete_prior_sides": int(prior), "both_prior_lineups": int(both.sum()),
               "missing_prior_sides": int(2 * mask.sum() - prior),
               "missing_ratings_in_complete_prior_lineups": int((f.players_lacking_ratings_a + f.players_lacking_ratings_b).sum()),
               "both_asof_form": int(available.sum())}
        if current_form is not None:
            c = current_form.loc[mask]
            row["both_current_roster_form"] = int((c.player_form_a.notna() & c.player_form_b.notna()).sum())
        if current_complete is not None:
            row["both_complete_current_rosters"] = int(current_complete.loc[mask].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def load_snapshot():
    con = db.connect(read_only=True)
    try:
        matches = match_sequence(con).reset_index(drop=True)
        identities = con.execute(IDENTITY_SQL).df()
        stats = con.execute(STATS_SQL).df()
    finally:
        con.close()
    return matches, identities, stats


def audit() -> pd.DataFrame:
    matches, identities, stats = load_snapshot()
    features = replay(matches, identities, stats)
    comparator = _player_form_from_stats(
        matches, stats[["match_id", "team_number", "player_key", "rating"]].assign(tier=1))
    by_side = stats.groupby(["match_id", "team_number"]).player_key.nunique()
    current_complete = pd.Series([
        by_side.get((mid, 1), 0) == 5 and by_side.get((mid, 2), 0) == 5
        for mid in matches.match_id], index=matches.index)
    return coverage(matches, features, comparator, current_complete)


if __name__ == "__main__":
    print(audit().to_string(index=False))
