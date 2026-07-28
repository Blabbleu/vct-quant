"""Normalize raw source data into the canonical DuckDB schema.

Two source families feed the same tables:
  * data/raw/vlrgg/*.json   — live harvests from the unofficial API
  * data/raw/kaggle/**.csv  — historical scrape (2021-2026)

The schema is keyed on numeric vlr.gg IDs, but the Kaggle match CSVs are keyed
on text (Tournament / Stage / Match Type / Match Name). `all_ids/` bridges the
two worlds, so every loader here resolves through it rather than fuzzy-matching
names. Rows that fail to resolve are counted in `LoadReport`, never dropped
silently — a quietly discarded slice would distort every rating downstream.

Chronology note: the corpus carries no dates. Ordering is by ascending vlr.gg
match_id (verified monotonic across years), so `scheduled_at` is deliberately
left NULL rather than fabricated.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import pandas as pd

from ..config import RAW_KAGGLE_DIR, RAW_VLRGG_DIR
from ..db import connect
from ..ingest.kaggle import list_csvs
from .events import competition_tier

MATCH_KEY = ["Tournament", "Stage", "Match Type", "Match Name"]

# Child-to-parent order, so clearing tables before a reload does not trip
# foreign keys.
_LOAD_ORDER = [
    "match_map_player_stat",
    "match_map_team_score",
    "match_map",
    "match_team",
    "match",
    "event",
    "player",
    "team",
]


@dataclass
class LoadReport:
    """Counts of what landed and what could not be resolved."""

    inserted: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)

    def note(self, table: str, n: int) -> None:
        self.inserted[table] = self.inserted.get(table, 0) + int(n)

    def drop(self, reason: str, n: int) -> None:
        if n:
            self.skipped[reason] = self.skipped.get(reason, 0) + int(n)

    def __str__(self) -> str:
        lines = ["Inserted:"]
        lines += [f"  {t:<28} {n:>9,}" for t, n in self.inserted.items()]
        if self.skipped:
            lines.append("Unresolved / skipped:")
            lines += [f"  {r:<28} {n:>9,}" for r, n in self.skipped.items()]
        return "\n".join(lines)


# --- helpers ---------------------------------------------------------------


def inspect_kaggle(preview_rows: int = 3) -> None:
    """Print every Kaggle CSV with its columns — the starting point for
    writing loaders."""
    csvs = list_csvs()
    if not csvs:
        print(f"No CSVs under {RAW_KAGGLE_DIR}. Run `vct download-kaggle` first.")
        return
    for path in csvs:
        rel = path.relative_to(RAW_KAGGLE_DIR)
        try:
            df = pd.read_csv(path, nrows=preview_rows)
        except Exception as exc:  # some scrape files can be malformed
            print(f"{rel}: FAILED to read ({exc})")
            continue
        print(f"{rel}: {list(df.columns)}")


def _year_dirs() -> list[Path]:
    return sorted(p for p in RAW_KAGGLE_DIR.glob("vct_*") if p.is_dir())


def _read_year(year_dir: Path, rel: str) -> pd.DataFrame:
    path = year_dir / rel
    # low_memory=False: the percentage columns are mixed int/str across chunks.
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def _read_all(rel: str) -> pd.DataFrame:
    frames = [f for f in (_read_year(d, rel) for d in _year_dirs()) if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _pct(s: pd.Series) -> pd.Series:
    """'81%' -> 81.0. Values outside 0-100 become NULL (the schema CHECKs them)."""
    out = pd.to_numeric(
        s.astype("string").str.replace("%", "", regex=False).str.strip(),
        errors="coerce",
    )
    return out.where(out.between(0, 100))


def _num(s: pd.Series, lo: float | None = None) -> pd.Series:
    out = pd.to_numeric(s, errors="coerce")
    return out.where(out >= lo) if lo is not None else out


def _duration_seconds(s: pd.Series) -> pd.Series:
    """'1:02:40' or '46:45' -> seconds."""
    def to_sec(v):
        if not isinstance(v, str):
            return None
        parts = v.strip().split(":")
        if not parts or not all(p.isdigit() for p in parts):
            return None
        nums = [int(p) for p in parts]
        if len(nums) == 3:
            return nums[0] * 3600 + nums[1] * 60 + nums[2]
        if len(nums) == 2:
            return nums[0] * 60 + nums[1]
        return None

    return pd.Series([to_sec(v) for v in s], index=s.index, dtype="Float64")


def _int(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("Float64").astype("Int64")


def _unambiguous(df: pd.DataFrame, name_col: str, id_col: str) -> dict[str, int]:
    """name -> id, keeping only names that map to exactly one non-null ID.

    Orgs relist and handles get reused: 36 team names and 224 player handles
    carry two distinct vlr.gg IDs. Guessing between them would silently merge
    two different entities' histories, so those names resolve to NULL and the
    text name is retained instead.
    """
    d = df[[name_col, id_col]].dropna()
    d = d[d[id_col] > 0]
    counts = d.groupby(name_col)[id_col].nunique()
    d = d[d[name_col].isin(counts[counts == 1].index)].drop_duplicates(name_col)
    return dict(zip(d[name_col], d[id_col].astype("int64")))


def _insert(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame,
            report: LoadReport) -> None:
    if df.empty:
        return
    cols = ", ".join(f'"{c}"' for c in df.columns)
    con.register("_stage", df)
    try:
        con.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _stage")
    finally:
        con.unregister("_stage")
    report.note(table, len(df))


def _match_ids() -> pd.DataFrame:
    """The ID spine: KEY(+Map) -> tournament / match / game IDs."""
    ids = pd.read_csv(RAW_KAGGLE_DIR / "all_ids" / "all_matches_games_ids.csv")
    ids = ids.dropna(subset=["Match ID", "Game ID", "Tournament ID"])
    ids = ids[(ids["Match ID"] > 0) & (ids["Game ID"] > 0) & (ids["Tournament ID"] > 0)]
    for c in ("Match ID", "Game ID", "Tournament ID"):
        ids[c] = ids[c].astype("int64")
    # A few keys are ambiguous (a rematch reusing the same name inside one
    # stage); keep the first so every join stays 1:1.
    return ids.drop_duplicates(subset=MATCH_KEY + ["Map"], keep="first")


# --- loaders ---------------------------------------------------------------


def load_entities(con: duckdb.DuckDBPyConnection, report: LoadReport) -> dict:
    """team, player, event — the spine every other table's FKs point at."""
    raw_teams = pd.read_csv(RAW_KAGGLE_DIR / "all_ids" / "all_teams_ids.csv")
    raw_players = pd.read_csv(RAW_KAGGLE_DIR / "all_ids" / "all_players_ids.csv")

    team_map = _unambiguous(raw_teams, "Team", "Team ID")
    player_map = _unambiguous(raw_players, "Player", "Player ID")
    report.drop("ambiguous team names", raw_teams["Team"].nunique() - len(team_map))
    report.drop("ambiguous player handles",
                raw_players["Player"].nunique() - len(player_map))

    teams = pd.DataFrame({"team_id": list(team_map.values()),
                          "name": list(team_map)}).drop_duplicates("team_id")
    _insert(con, "team", teams, report)

    players = pd.DataFrame({"player_id": list(player_map.values()),
                            "handle": list(player_map)}).drop_duplicates("player_id")
    _insert(con, "player", players, report)

    tour = pd.read_csv(
        RAW_KAGGLE_DIR / "all_ids" / "all_tournaments_stages_match_types_ids.csv"
    )
    tour = tour.dropna(subset=["Tournament ID"])
    tour = tour[tour["Tournament ID"] > 0]
    events = (
        tour.sort_values("Year")
        .drop_duplicates("Tournament ID", keep="first")
        .assign(event_id=lambda d: d["Tournament ID"].astype("int64"),
                name=lambda d: d["Tournament"].astype(str),
                tier=lambda d: pd.Series(
                    [competition_tier(n, int(y)) for n, y in zip(d["Tournament"], d["Year"])],
                    index=d.index,
                    dtype="Int64",
                ),
                # The only temporal signal in the corpus; no real dates exist.
                dates_raw=lambda d: d["Year"].astype(str))
        [["event_id", "name", "tier", "dates_raw"]]
    )
    _insert(con, "event", events, report)

    # Abbreviation -> full name, for match CSVs that use the short form.
    mapping = pd.read_csv(RAW_KAGGLE_DIR / "all_ids" / "all_teams_mapping.csv").dropna()
    counts = mapping.groupby("Abbreviated")["Full Name"].nunique()
    abbr = dict(
        mapping[mapping["Abbreviated"].isin(counts[counts == 1].index)]
        .drop_duplicates("Abbreviated")[["Abbreviated", "Full Name"]]
        .itertuples(index=False, name=None)
    )
    return {"team": team_map, "player": player_map, "abbr": abbr}


def load_matches(con: duckdb.DuckDBPyConnection, maps: dict,
                 report: LoadReport) -> None:
    """match + match_team, from matches/scores.csv."""
    scores = _read_all("matches/scores.csv")
    if scores.empty:
        return

    spine = _match_ids().drop_duplicates(MATCH_KEY)
    key = spine[MATCH_KEY + ["Match ID", "Tournament ID", "Year"]]
    df = scores.merge(key, on=MATCH_KEY, how="left")
    report.drop("scores without match_id", int(df["Match ID"].isna().sum()))
    df = df.dropna(subset=["Match ID"]).drop_duplicates("Match ID", keep="first")
    if df.empty:
        return

    a, b = _num(df["Team A Score"], 0), _num(df["Team B Score"], 0)
    best = pd.concat([a, b], axis=1).max(axis=1)
    # Bo1 rows record the ROUND score (13-3), not the map score (1-0). A series
    # is never won by more than 3 maps, so anything above that is a round score
    # from a single-map match — verified: every such row has exactly 1 map.
    round_score = best > 3
    report.drop("Bo1 rows storing round scores", int(round_score.sum()))

    known_events = {r[0] for r in con.execute("SELECT event_id FROM event").fetchall()}
    event_id = _int(df["Tournament ID"])

    match = pd.DataFrame({
        "match_id": df["Match ID"].astype("int64"),
        "event_id": event_id.where(event_id.isin(known_events)),
        "event_name": df["Tournament"].astype(str),
        "event_series": df["Stage"].astype(str),
        "status": "completed",
        "date_raw": _int(df["Year"]).astype(str),
        # Bo3 shows as 2 series wins, Bo5 as 3. No veto data in this corpus.
        "best_of": _int((2 * best - 1).where(best > 0).mask(round_score, 1)),
    })
    _insert(con, "match", match, report)

    team_map, abbr = maps["team"], maps["abbr"]

    def resolve(names: pd.Series) -> pd.Series:
        return _int(names.map(lambda n: abbr.get(n, n)).map(team_map))

    def side(num: int, tcol: str, scol: str) -> pd.DataFrame:
        won = (a > b) if num == 1 else (b > a)
        return pd.DataFrame({
            "match_id": df["Match ID"].astype("int64"),
            "team_number": num,
            "team_id": resolve(df[tcol]),
            "team_name": df[tcol].astype(str),
            # Keep this a map count even where the source stored rounds.
            "series_score": _int(_num(df[scol], 0).mask(round_score, won.astype(int))),
            # Bo2 formats really do draw (74 sit at 1-1). A draw is not a loss,
            # so leave it NULL rather than marking both sides losers.
            "is_winner": won.where(a != b),
        })

    mt = pd.concat([side(1, "Team A", "Team A Score"),
                    side(2, "Team B", "Team B Score")], ignore_index=True)

    # UNIQUE (match_id, team_id): both sides resolving to one ID means the
    # resolution is wrong, so drop the IDs for that match and keep the names.
    have = mt.dropna(subset=["team_id"])
    clash = set(have[have.duplicated(["match_id", "team_id"], keep=False)]["match_id"])
    if clash:
        mt.loc[mt["match_id"].isin(clash), "team_id"] = pd.NA
        report.drop("match_team team_id clashes", len(clash))
    _insert(con, "match_team", mt, report)


def load_maps(con: duckdb.DuckDBPyConnection, maps: dict,
              report: LoadReport) -> pd.DataFrame:
    """match_map + match_map_team_score, from matches/maps_scores.csv.

    match_map_id is the real vlr.gg Game ID rather than a sequence value, so
    downstream tables can join on it directly.
    """
    ms = _read_all("matches/maps_scores.csv")
    if ms.empty:
        return pd.DataFrame()

    # Forfeits/walkovers have a null Map and 0-0 scores. Pandas joins null to
    # null, so they must go before the merge or they arrive with a game_id and
    # no map name (match_map.map_name is NOT NULL).
    report.drop("forfeits (no map played)", int(ms["Map"].isna().sum()))
    ms = ms[ms["Map"].notna()]

    ids = _match_ids()[MATCH_KEY + ["Map", "Match ID", "Game ID"]]
    ids = ids[ids["Map"].notna()]
    df = ms.merge(ids, on=MATCH_KEY + ["Map"], how="left")
    report.drop("maps without game_id", int(df["Game ID"].isna().sum()))
    df = df.dropna(subset=["Game ID"]).drop_duplicates("Game ID", keep="first")

    known = {r[0] for r in con.execute("SELECT match_id FROM match").fetchall()}
    before = len(df)
    df = df[df["Match ID"].isin(known)]
    report.drop("maps whose match is absent", before - len(df))
    if df.empty:
        return pd.DataFrame()

    df = df.assign(match_map_id=df["Game ID"].astype("int64"),
                   match_id=df["Match ID"].astype("int64"))
    # Maps are played in order and vlr.gg issues game IDs sequentially.
    df["map_number"] = (df.groupby("match_id")["match_map_id"]
                        .rank(method="first").astype(int))

    _insert(con, "match_map", pd.DataFrame({
        "match_map_id": df["match_map_id"],
        "match_id": df["match_id"],
        "map_number": df["map_number"],
        "map_name": df["Map"].astype(str),
        "duration_seconds": _int(_duration_seconds(df["Duration"])),
    }), report)

    team_map, abbr = maps["team"], maps["abbr"]
    scores = pd.concat([
        pd.DataFrame({
            "match_map_id": df["match_map_id"],
            "team_number": num,
            "team_id": _int(df[side].map(lambda n: abbr.get(n, n)).map(team_map)),
            "total_rounds": _int(_num(df[f"{side} Score"], 0)),
            "attack_rounds": _int(_num(df[f"{side} Attacker Score"], 0)),
            "defense_rounds": _int(_num(df[f"{side} Defender Score"], 0)),
            "overtime_rounds": _int(_num(df[f"{side} Overtime Score"], 0)),
        })
        for num, side in enumerate(["Team A", "Team B"], start=1)
    ], ignore_index=True)
    _insert(con, "match_map_team_score", scores, report)

    return df[MATCH_KEY + ["Map", "match_map_id", "Team A", "Team B"]]


def load_player_stats(con: duckdb.DuckDBPyConnection, maps: dict,
                      map_rows: pd.DataFrame, report: LoadReport) -> None:
    """match_map_player_stat, from matches/overview.csv.

    overview.csv holds three rows per player per map (both / attack / defend)
    plus an 'All Maps' aggregate; only the per-map 'both' row belongs here.
    Loaded year by year — the file totals ~1.15M rows.
    """
    if map_rows.empty:
        return

    lookup = map_rows.set_index(MATCH_KEY + ["Map"])
    player_map, abbr = maps["player"], maps["abbr"]
    # Year folders overlap: a tournament straddling a year boundary is scraped
    # into both (e.g. Valorant Conquerors Championship sits in vct_2021 and
    # vct_2022). The match/map loaders dedupe globally, but this loop reads one
    # year at a time, so it has to remember what it already inserted.
    seen_maps: set[int] = set()

    for year_dir in _year_dirs():
        ov = _read_year(year_dir, "matches/overview.csv")
        if ov.empty:
            continue
        ov = ov[(ov["Side"] == "both") & (ov["Map"] != "All Maps")]
        report.drop("player rows with no handle", int(ov["Player"].isna().sum()))
        ov = ov[ov["Player"].notna()]
        if ov.empty:
            continue

        ov = ov.join(lookup, on=MATCH_KEY + ["Map"], how="inner")
        if ov.empty:
            continue

        already = ov["match_map_id"].isin(seen_maps)
        report.drop("player rows already seen in an earlier year", int(already.sum()))
        ov = ov[~already]
        if ov.empty:
            continue

        # Which side of the map was this player on?
        full = ov["Team"].map(lambda n: abbr.get(n, n))
        side = pd.Series(pd.NA, index=ov.index, dtype="Int64")
        side[full == ov["Team A"].map(lambda n: abbr.get(n, n))] = 1
        side[full == ov["Team B"].map(lambda n: abbr.get(n, n))] = 2
        report.drop("player rows with unknown side", int(side.isna().sum()))
        ov = ov[side.notna()].assign(team_number=side.dropna().astype(int))
        if ov.empty:
            continue

        ov = ov.drop_duplicates(["match_map_id", "team_number", "Player"], keep="first")
        ov["player_slot"] = ov.groupby(["match_map_id", "team_number"]).cumcount() + 1

        pid = _int(ov["Player"].map(player_map))
        # UNIQUE (match_map_id, player_id): a reused handle inside one map
        # would collide, so keep the first and null the rest.
        clash = pid.notna() & pd.DataFrame(
            {"m": ov["match_map_id"], "p": pid}
        ).duplicated(["m", "p"], keep="first")
        report.drop("duplicate player_id on a map", int(clash.sum()))

        _insert(con, "match_map_player_stat", pd.DataFrame({
            "match_map_id": ov["match_map_id"].astype("int64"),
            "team_number": ov["team_number"].astype(int),
            "player_slot": ov["player_slot"].astype(int),
            "player_id": pid.where(~clash),
            "player_handle": ov["Player"].astype(str),
            "agent_name": ov["Agents"].astype("string"),
            "rating": _num(ov["Rating"]),
            "acs": _num(ov["Average Combat Score"]),
            "kills": _int(_num(ov["Kills"], 0)),
            "deaths": _int(_num(ov["Deaths"], 0)),
            "assists": _int(_num(ov["Assists"], 0)),
            "kill_death_diff": _int(ov["Kills - Deaths (KD)"]),
            "kast_pct": _pct(ov["Kill, Assist, Trade, Survive %"]),
            "adr": _num(ov["Average Damage Per Round"]),
            "headshot_pct": _pct(ov["Headshot %"]),
            "first_kills": _int(_num(ov["First Kills"], 0)),
            "first_deaths": _int(_num(ov["First Deaths"], 0)),
            "first_kill_diff": _int(ov["Kills - Deaths (FKD)"]),
        }), report)
        seen_maps.update(ov["match_map_id"].astype("int64").tolist())


def load_kaggle(con: duckdb.DuckDBPyConnection | None = None,
                replace: bool = True) -> LoadReport:
    """Load the whole Kaggle corpus into the canonical tables.

    `replace=True` clears the target tables first so the load is repeatable;
    raw data is immutable, so replaying is always safe.
    """
    report = LoadReport()
    owned = con is None
    con = con or connect()
    try:
        if replace:
            for table in _LOAD_ORDER:
                con.execute(f"DELETE FROM {table}")
        maps = load_entities(con, report)
        load_matches(con, maps, report)
        map_rows = load_maps(con, maps, report)
        load_player_stats(con, maps, map_rows, report)
    finally:
        if owned:
            con.close()
    return report


def _vlrgg_events() -> pd.DataFrame:
    """Event IDs and titles from the paged vlrggapi event listing."""
    rows: list[dict] = []
    for path in sorted(RAW_VLRGG_DIR.glob("events_page*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(payload.get("data", {}).get("segments", []))
    if not rows:
        return pd.DataFrame()

    d = pd.DataFrame(rows).drop_duplicates("event_id", keep="last")
    return pd.DataFrame({
        "event_id": _int(d["event_id"]),
        "name": d["title"].astype(str),
        "tier": pd.Series(
            [competition_tier(name) for name in d["title"]],
            index=d.index,
            dtype="Int64",
        ),
        "status": d["status"].astype("string"),
        "region_code": d["region"].astype("string"),
        "dates_raw": d["dates"].astype("string"),
        "prize_pool_raw": d["prize"].astype("string"),
        "logo_url": d["thumb"].astype("string"),
        "vlr_url": d["url_path"].astype("string"),
    })


def _upsert_vlrgg_events(
    con: duckdb.DuckDBPyConnection, events: pd.DataFrame, report: LoadReport
) -> None:
    if events.empty:
        return
    cols = list(events.columns)
    quoted = ", ".join(f'"{c}"' for c in cols)
    updates = ", ".join(
        f'"{c}" = excluded."{c}"' for c in cols if c != "event_id"
    )
    con.register("_events", events)
    try:
        con.execute(
            f"""INSERT INTO event ({quoted}) SELECT {quoted} FROM _events
                ON CONFLICT (event_id) DO UPDATE SET {updates}"""
        )
    finally:
        con.unregister("_events")
    report.note("event metadata upserted", len(events))


def _classify_stored_events(
    con: duckdb.DuckDBPyConnection, report: LoadReport
) -> None:
    """Apply the same scope rules to Kaggle events not present in API pages."""
    d = con.execute("SELECT event_id, name, dates_raw FROM event").df()
    year = pd.to_numeric(d["dates_raw"], errors="coerce")
    d["tier"] = pd.Series(
        [
            competition_tier(name, int(y) if pd.notna(y) else None)
            for name, y in zip(d["name"], year)
        ],
        dtype="Int64",
    )
    con.register("_event_tiers", d[["event_id", "tier"]])
    try:
        con.execute("""UPDATE event SET tier = _event_tiers.tier
                       FROM _event_tiers
                       WHERE event.event_id = _event_tiers.event_id""")
    finally:
        con.unregister("_event_tiers")
    report.note("official events classified", int(d["tier"].notna().sum()))


def _vlrgg_event_matches(events: pd.DataFrame | None = None) -> pd.DataFrame:
    """Every completed match harvested by scripts/backfill_vlrgg.py.

    Two quirks in this feed, both verified against the harvest:
      * the scraper appends "Today"/"Yesterday" to the date string, and one row
        carries a Dec 31 1969 epoch-0 sentinel;
      * a Bo1 reports the ROUND score (13-3), exactly as the Kaggle corpus does
        — 18,147 of 72,495 rows. A series is never won by more than 3 maps.
    """
    rows: list[dict] = []
    for path in sorted(RAW_VLRGG_DIR.glob("event_matches_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for seg in payload.get("data", {}).get("segments", []):
            rows.append({
                **seg,
                "event_id": int(re.search(r"event_matches_(\d+)_", path.name).group(1)),
            })
    if not rows:
        return pd.DataFrame()

    d = pd.DataFrame(rows)
    d = d[d["status"].str.lower() == "completed"]
    # A later harvest of an ongoing event supersedes an earlier one.
    d = d.drop_duplicates("match_id", keep="last")

    date = pd.to_datetime(
        d["date"].astype(str).str.replace(r"(Yesterday|Today)$", "", regex=True),
        format="%a, %B %d, %Y",
        errors="coerce",
    )
    d = d.assign(
        match_id=pd.to_numeric(d["match_id"], errors="coerce"),
        completed_at=date.where(date > "2010-01-01"),
        score_a=pd.to_numeric([t.get("score") for t in d["team1"]], errors="coerce"),
        score_b=pd.to_numeric([t.get("score") for t in d["team2"]], errors="coerce"),
        name_a=[t.get("name") for t in d["team1"]],
        name_b=[t.get("name") for t in d["team2"]],
    )
    d = d.dropna(subset=["match_id"]).astype({"match_id": "int64"})
    events = _vlrgg_events() if events is None else events
    if events.empty:
        d["event_name"] = pd.NA
        return d
    return d.merge(
        events[["event_id", "name"]].rename(columns={"name": "event_name"}),
        on="event_id",
        how="left",
    )


def load_vlrgg_match_results(con: duckdb.DuckDBPyConnection | None = None) -> LoadReport:
    """Merge the vlrggapi event harvest into `match` + `match_team`.

    Additive, not a replace: matches already loaded from Kaggle keep their rows
    and only gain `completed_at`, which is the first real timestamp this project
    has had. New matches are inserted whole. Safe to re-run.
    """
    report = LoadReport()
    owned = con is None
    con = con or connect()
    try:
        events = _vlrgg_events()
        _upsert_vlrgg_events(con, events, report)
        _classify_stored_events(con, report)
        d = _vlrgg_event_matches(events)
        if d.empty:
            return report

        known = {r[0] for r in con.execute("SELECT match_id FROM match").fetchall()}
        known_events = {r[0] for r in con.execute("SELECT event_id FROM event").fetchall()}
        d["event_id"] = _int(d["event_id"]).where(d["event_id"].isin(known_events))
        existing = d[d["match_id"].isin(known)]
        fresh = d[~d["match_id"].isin(known)]

        # Backfill dates onto rows the Kaggle load already owns.
        # Kaggle already carries the correct event ID/title. Updating those
        # columns trips DuckDB's referenced-row FK limitation, so the overlap
        # only needs the real date that Kaggle lacks.
        dated = existing.dropna(subset=["completed_at"])[["match_id", "completed_at"]]
        if not dated.empty:
            con.register("_dates", dated)
            try:
                con.execute("""
                    UPDATE match SET completed_at = _dates.completed_at
                    FROM _dates WHERE match.match_id = _dates.match_id
                """)
            finally:
                con.unregister("_dates")
            report.note("match dates backfilled", len(dated))

        report.drop("matches missing a date", int(d["completed_at"].isna().sum()))
        if fresh.empty:
            return report

        best = fresh[["score_a", "score_b"]].max(axis=1)
        # See the docstring: >3 means this is a Bo1's round score.
        round_score = best > 3
        report.drop("Bo1 rows storing round scores", int(round_score.sum()))

        won_a = fresh["score_a"] > fresh["score_b"]

        _insert(con, "match", pd.DataFrame({
            "match_id": fresh["match_id"],
            "event_id": _int(fresh["event_id"]),
            "event_name": fresh["event_name"].astype("string"),
            "event_series": fresh["event_series"].astype("string"),
            "status": "completed",
            "completed_at": fresh["completed_at"],
            # date_raw stays the YEAR, matching what the Kaggle load writes —
            # features.build reads the year back out of it.
            "date_raw": fresh["completed_at"].dt.year.astype("Int64").astype(str),
            "best_of": _int((2 * best - 1).where(best > 0).mask(round_score, 1)),
            "vlr_url": fresh["url"].astype(str),
        }), report)

        team_map = _unambiguous(
            con.execute("SELECT name, team_id FROM team").df(), "name", "team_id"
        )

        def side(num: int, name_col: str, score_col: str) -> pd.DataFrame:
            won = won_a if num == 1 else ~won_a
            return pd.DataFrame({
                "match_id": fresh["match_id"],
                "team_number": num,
                "team_id": _int(fresh[name_col].map(team_map)),
                "team_name": fresh[name_col].astype(str),
                "series_score": _int(
                    fresh[score_col].mask(round_score, won.astype(int))
                ),
                # Bo2 draws are real; a draw is not a loss for either side.
                "is_winner": won.where(fresh["score_a"] != fresh["score_b"]),
            })

        mt = pd.concat([side(1, "name_a", "score_a"),
                        side(2, "name_b", "score_b")], ignore_index=True)
        # UNIQUE (match_id, team_id): both sides resolving to one ID means the
        # resolution is wrong, so drop the IDs and keep the names.
        have = mt.dropna(subset=["team_id"])
        clash = set(have[have.duplicated(["match_id", "team_id"], keep=False)]["match_id"])
        if clash:
            mt.loc[mt["match_id"].isin(clash), "team_id"] = pd.NA
            report.drop("match_team team_id clashes", len(clash))
        _insert(con, "match_team", mt, report)
    finally:
        if owned:
            con.close()
    return report


def _vlrgg_match_details() -> list[dict]:
    """Latest raw match-detail payload per match."""
    latest: dict[int, Path] = {}
    for path in sorted(RAW_VLRGG_DIR.glob("match_details_*.json")):
        match = re.match(r"match_details_(\d+)_", path.name)
        if match:
            latest[int(match.group(1))] = path

    details: list[dict] = []
    for match_id, path in latest.items():
        data = json.loads(path.read_text(encoding="utf-8")).get("data", {})
        segments = data.get("segments") or [data]
        details.extend(
            detail for detail in segments if int(detail.get("match_id", 0)) == match_id
        )
    return details


def load_vlrgg_match_details(
    con: duckdb.DuckDBPyConnection | None = None,
) -> LoadReport:
    """Load harvested match maps, scores, and player stats. Safe to re-run."""
    report = LoadReport()
    owned = con is None
    con = con or connect()
    try:
        details = _vlrgg_match_details()
        known = {row[0] for row in con.execute("SELECT match_id FROM match").fetchall()}
        loaded = {
            row[0]
            for row in con.execute("""
                SELECT DISTINCT mm.match_id
                FROM match_map mm
                JOIN match_map_player_stat s USING (match_map_id)
            """).fetchall()
        }
        report.drop(
            "details whose match is absent",
            sum(int(detail["match_id"]) not in known for detail in details),
        )
        report.drop(
            "details already loaded",
            sum(int(detail["match_id"]) in loaded for detail in details),
        )
        report.drop(
            "details without maps",
            sum(not detail.get("maps") for detail in details),
        )
        details = [
            detail for detail in details
            if int(detail["match_id"]) in known
            and int(detail["match_id"]) not in loaded
            and detail.get("maps")
        ]
        if not details:
            return report

        team_ids = {
            (int(match_id), int(team_number)): team_id
            for match_id, team_number, team_id in con.execute(
                "SELECT match_id, team_number, team_id FROM match_team"
            ).fetchall()
        }
        player_ids = _unambiguous(
            con.execute("SELECT handle, player_id FROM player").df(),
            "handle",
            "player_id",
        )
        maps: list[dict] = []
        scores: list[dict] = []
        stats: list[dict] = []

        for detail in details:
            match_id = int(detail["match_id"])
            for map_number, game_map in enumerate(detail.get("maps", []), 1):
                # Detail payloads expose map order but not vlr.gg game IDs.
                match_map_id = -(match_id * 10 + map_number)
                maps.append({
                    "match_map_id": match_map_id,
                    "match_id": match_id,
                    "map_number": map_number,
                    "map_name": re.sub(
                        r"PICK$", "", str(game_map.get("map_name", "")), flags=re.I
                    ).strip(),
                    "picked_by_raw": game_map.get("picked_by") or None,
                    "duration_seconds": _duration_seconds(
                        pd.Series([game_map.get("duration")])
                    ).iloc[0],
                    "status": detail.get("status"),
                })

                for team_number, key in ((1, "team1"), (2, "team2")):
                    scores.append({
                        "match_map_id": match_map_id,
                        "team_number": team_number,
                        "team_id": team_ids.get((match_id, team_number)),
                        "total_rounds": game_map.get("score", {}).get(key),
                        "attack_rounds": game_map.get("score_t", {}).get(key),
                        "defense_rounds": game_map.get("score_ct", {}).get(key),
                        "overtime_rounds": game_map.get("score_ot", {}).get(key),
                    })
                    for slot, player in enumerate(
                        game_map.get("players", {}).get(key, []), 1
                    ):
                        stats.append({
                            "match_map_id": match_map_id,
                            "team_number": team_number,
                            "player_slot": slot,
                            "player_id": player_ids.get(player.get("name")),
                            "player_handle": player.get("name"),
                            "agent_name": player.get("agent"),
                            "rating": player.get("rating"),
                            "acs": player.get("acs"),
                            "kills": player.get("kills"),
                            "deaths": player.get("deaths"),
                            "assists": player.get("assists"),
                            "kill_death_diff": player.get("kd_diff"),
                            "kast_pct": player.get("kast"),
                            "adr": player.get("adr"),
                            "headshot_pct": player.get("hs_pct"),
                            "first_kills": player.get("fk"),
                            "first_deaths": player.get("fd"),
                            "first_kill_diff": player.get("fk_diff"),
                        })

        map_df = pd.DataFrame(maps)
        score_df = pd.DataFrame(scores)
        stat_df = pd.DataFrame(stats)
        for col in (
            "total_rounds", "attack_rounds", "defense_rounds", "overtime_rounds"
        ):
            score_df[col] = _int(score_df[col])
        for col in (
            "kills", "deaths", "assists", "kill_death_diff",
            "first_kills", "first_deaths", "first_kill_diff",
        ):
            stat_df[col] = _int(stat_df[col])
        for col in ("rating", "acs", "adr"):
            stat_df[col] = _num(stat_df[col])
        for col in ("kast_pct", "headshot_pct"):
            stat_df[col] = _pct(stat_df[col])

        con.execute("BEGIN")
        try:
            _insert(con, "match_map", map_df, report)
            _insert(con, "match_map_team_score", score_df, report)
            _insert(con, "match_map_player_stat", stat_df, report)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    finally:
        if owned:
            con.close()
    return report
