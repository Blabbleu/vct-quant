"""Point-in-time Kaggle economy coverage audit; deliberately does no scoring."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.asof_economy import replay
from vct_quant import db
from vct_quant.features.build import match_sequence

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/kaggle"
KEY = ["Tournament", "Stage", "Match Type", "Match Name"]
MAP_KEY = KEY + ["Map"]
FAIL_COLUMNS = ["year", *KEY, "match_id", "team_name", "reason"]


def _norm(value: object) -> str:
    return str(value).strip().lower()


def match_id_bridge(ids: pd.DataFrame, key: list[str]) -> pd.Series:
    """Unique candidate Match IDs for each Kaggle name key, retaining ambiguity."""
    return ids[key + ["Match ID"]].drop_duplicates().groupby(key, dropna=False)["Match ID"].agg(
        lambda s: tuple(sorted(set(s.dropna().astype(int)))))


def sequence_pairs(matches: pd.DataFrame) -> dict:
    """The ordered sequence sides and their normalized source names."""
    return {int(r.match_id): ((r.team_a, _norm(r.team_a_name)),
                              (r.team_b, _norm(r.team_b_name)))
            for r in matches.itertuples(index=False)}


def matched_side(pair: tuple, name: object) -> tuple[int | None, str | None]:
    """Resolve a Kaggle team name to exactly one sequence side, or a reason."""
    hits = [side for side, (_, normalized) in enumerate(pair)
            if normalized == _norm(name)]
    if len(hits) != 1:
        return None, "ambiguous_team" if hits else "team_name_mismatch"
    return hits[0], None


def load_raw(raw: Path = RAW) -> tuple[pd.DataFrame, pd.DataFrame]:
    eco, ids = [], []
    for year in range(2021, 2027):
        base = raw / f"vct_{year}"
        e = pd.read_csv(base / "matches/eco_stats.csv")
        i = pd.read_csv(base / "ids/tournaments_stages_matches_games_ids.csv")
        e["year"] = i["year"] = year
        eco.append(e)
        ids.append(i)
    return pd.concat(eco, ignore_index=True), pd.concat(ids, ignore_index=True)


def build_economy(matches: pd.DataFrame, eco: pd.DataFrame,
                  ids: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return one rate row per series side and all failed joins.

    Bridge keys with multiple distinct game/match IDs are ambiguous; their raw
    rows are excluded. Exact source duplicates are removed before any count.
    """
    # "All Maps" is a series summary in eco_stats, not a played map or game.
    # Including it would double-count rounds and has no Game ID in the bridge.
    eco = eco.loc[eco.Map.ne("All Maps")].drop_duplicates().copy()
    bridge_key = ["year", *MAP_KEY]
    bridge = ids[bridge_key + ["Match ID", "Game ID"]].drop_duplicates()
    bridge = bridge.groupby(bridge_key, dropna=False).agg(
        match_ids=("Match ID", lambda s: tuple(sorted(set(s.dropna().astype(int))))),
        game_ids=("Game ID", lambda s: tuple(sorted(set(s.dropna().astype(int))))),
    ).reset_index()
    joined = eco.merge(bridge, how="left", on=bridge_key, validate="many_to_one")
    failures = []

    def fail(row, reason: str, team_name=None, match_id=None):
        failures.append({"year": int(row["year"]), **{k: row[k] for k in KEY},
                         "match_id": match_id, "team_name": team_name, "reason": reason})

    pairs = {}
    for r in matches.itertuples(index=False):
        pairs[int(r.match_id)] = ((r.team_a, _norm(r.team_a_name), r.team_a_name),
                                  (r.team_b, _norm(r.team_b_name), r.team_b_name))

    accepted = []
    for _, row in joined.iterrows():
        mids = row["match_ids"] if isinstance(row["match_ids"], tuple) else ()
        gids = row["game_ids"] if isinstance(row["game_ids"], tuple) else ()
        if not mids:
            fail(row, "no_id_bridge")
            continue
        if len(mids) != 1 or len(gids) != 1:
            fail(row, "ambiguous_id_bridge")
            continue
        mid = mids[0]
        pair = pairs.get(mid)
        if pair is None:
            fail(row, "outside_match_sequence", match_id=mid)
            continue
        hits = [n for n, (_, name, _) in enumerate(pair) if name == _norm(row["Team"])]
        if len(hits) != 1:
            fail(row, "ambiguous_team" if hits else "team_name_mismatch",
                 team_name=row["Team"], match_id=mid)
            continue
        accepted.append((mid, hits[0], gids[0], row["Type"], row["Initiated"], row["Won"]))

    counts = pd.DataFrame(accepted, columns=["match_id", "side", "game_id", "type", "initiated", "won"])
    rows = []
    if not counts.empty:
        for (mid, side), group in counts.groupby(["match_id", "side"], sort=False):
            full = group.loc[group.type.eq("$$$ (won)")]
            pistol = group.loc[group.type.eq("Pistol Won")]
            initiated = pd.to_numeric(full.initiated, errors="coerce").sum()
            won = pd.to_numeric(full.won, errors="coerce").sum()
            pistol_won = pd.to_numeric(pistol.won, errors="coerce").sum()
            n_maps = pistol.game_id.nunique()
            sequence_side = pairs[int(mid)][int(side)]
            rows.append({"match_id": int(mid), "team_id": int(sequence_side[0])
                         if str(sequence_side[0]).isdigit() else None,
                         "team_name": sequence_side[2],
                         "full_buy_win_pct": won / initiated if initiated > 0 else None,
                         "pistol_win_pct": pistol_won / (2 * n_maps) if n_maps else None})
    economy = pd.DataFrame(rows, columns=["match_id", "team_id", "team_name",
                                           "full_buy_win_pct", "pistol_win_pct"])
    failure_frame = pd.DataFrame(failures, columns=FAIL_COLUMNS).drop_duplicates()
    return economy, failure_frame


def coverage(matches: pd.DataFrame, features: pd.DataFrame,
             failures: pd.DataFrame) -> pd.DataFrame:
    records = []
    for year in range(2023, 2027):
        mask = matches.year.eq(year) & matches.tier.eq(1) & matches.score_a.isin((0.0, 1.0))
        f = features.loc[mask]
        both = f.prior_economy_rows_a.ge(3) & f.prior_economy_rows_b.ge(3)
        bad = failures.loc[failures.year.eq(year)]
        series = bad.loc[bad.team_name.isna(), ["year", *KEY]].drop_duplicates()
        teams = bad.loc[bad.team_name.notna(), "team_name"].map(_norm).nunique()
        records.append({"year": year, "rows": int(mask.sum()),
                        "both_sides_3_prior_series": int(both.sum()),
                        "failed_series": len(series), "failed_team_names": int(teams)})
    return pd.DataFrame(records)


def audit(raw: Path = RAW):
    con = db.connect(read_only=True)
    try:
        matches = match_sequence(con).reset_index(drop=True)
    finally:
        con.close()
    eco, ids = load_raw(raw)
    economy, failures = build_economy(matches, eco, ids)
    features, replay_failures = replay(matches, economy)
    if not replay_failures.empty:
        raise ValueError(f"Unexpected replay join failures: {replay_failures.to_dict('records')}")
    return coverage(matches, features, failures), failures, economy


if __name__ == "__main__":
    yearly, failures, economy = audit()
    print(yearly.to_string(index=False))
    print("matched series sides:", len(economy))
    print("mapping failures (one row per unique failed series/team/reason):")
    print(failures.to_string(index=False) if not failures.empty else "none")
