"""Read-only finished-match detail for the Match Center, verified before display.

A result is shown only when the canonical rows agree with themselves and with
the forecast: both identity keys match the logged pairing, series score and
winner flags are consistent and decisive for the recorded best-of, and the
completion day is not before the scheduled day. Map rows are shown only when
they are complete (numbered 1..n, n equal to maps played, named, decisive
round scores whose map wins reproduce the series score). Anything else is
reported as ``unverified`` with a reason rather than guessed.

This is descriptive history; it never feeds ratings, forecasts or grading.
"""
from __future__ import annotations

import math

import pandas as pd

from . import db



def _safe_source(url: object) -> str | None:
    """Only https vlr.gg links reach the page (never javascript: or other hosts)."""
    return url if isinstance(url, str) and url.startswith("https://www.vlr.gg/") else None

def identity_key(team_id, team_name) -> str | None:
    """Same identity rule as ``features.build.match_sequence``."""
    if team_id is not None and not (isinstance(team_id, float) and math.isnan(team_id)) and pd.notna(team_id):
        return str(int(team_id))
    if team_name is None or pd.isna(team_name):
        return None
    return "name:" + str(team_name).strip().lower()


def _int(value) -> int | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return int(number) if number.is_integer() and number >= 0 else None


def _decisive(a: int, b: int, best_of) -> bool:
    if a == b:
        return False
    need = _int(best_of)
    if need is None:
        return (max(a, b), min(a, b)) in ((1, 0), (2, 0), (2, 1), (3, 0), (3, 1), (3, 2))
    if need % 2 == 0:  # Bo2 draws/other even formats: no decisive-result rule here
        return False
    wins = need // 2 + 1
    return max(a, b) == wins and min(a, b) < wins


def _maps(rows: pd.DataFrame, total: int, series_1: int, series_2: int) -> list[dict] | None:
    if rows is None or rows.empty or len(rows) != total:
        return None
    rows = rows.sort_values("map_number")
    numbers = [_int(x) for x in rows.map_number]
    if numbers != list(range(1, total + 1)):
        return None
    out, wins_1, wins_2 = [], 0, 0
    for r in rows.itertuples():
        name = "" if r.map_name is None or pd.isna(r.map_name) else str(r.map_name).strip()
        one, two = _int(r.rounds_1), _int(r.rounds_2)
        if not name or name.lower() == "tbd" or one is None or two is None or one == two:
            return None
        wins_1 += one > two
        wins_2 += two > one
        out.append({"number": int(r.map_number), "map": name.title(), "rounds_1": one, "rounds_2": two})
    return out if (wins_1, wins_2) == (series_1, series_2) else None


def result_detail(meta: dict | None, teams: pd.DataFrame, maps: pd.DataFrame,
                  team_a_key: str, team_b_key: str, p_team_a: float | None = None) -> dict | None:
    """Return the verified or explicitly unverified result, oriented to side a/b.

    ``p_team_a`` is the last pre-start logged probability for forecast side a;
    it is echoed for the eventual winner only when the result is verified.
    """
    if not meta or str(meta.get("status") or "").strip().lower() != "completed":
        return None
    completed = pd.to_datetime(meta.get("completed_at"), utc=True, errors="coerce")
    last_seen = pd.to_datetime(meta.get("last_seen_at"), utc=True, errors="coerce")
    base = {"status": "unverified", "reason": None, "winner": None, "maps_a": None,
            "maps_b": None, "maps": [], "maps_complete": False, "pre_start_winner_p": None,
            "completed_on": None if pd.isna(completed) else completed.date().isoformat(),
            "source_url": _safe_source(meta.get("vlr_url")),
            "as_of": None if pd.isna(last_seen) else last_seen.isoformat()}

    sides = {}
    for row in teams.itertuples() if teams is not None else ():
        sides[_int(row.team_number)] = row
    if set(sides) != {1, 2}:
        return {**base, "reason": "teams missing from canonical result"}
    key_1 = identity_key(sides[1].team_id, sides[1].team_name)
    key_2 = identity_key(sides[2].team_id, sides[2].team_name)
    # A forecast logged before team-ID resolution carries the name key; the
    # canonical row may since have gained the numeric ID. Accept either key
    # of the *same* canonical side, but each forecast side must match one side.
    names_1 = {key_1, identity_key(None, sides[1].team_name)}
    names_2 = {key_2, identity_key(None, sides[2].team_name)}
    a, b = str(team_a_key), str(team_b_key)
    straight = a in names_1 and b in names_2
    swapped = a in names_2 and b in names_1
    if key_1 == key_2 or a == b or straight == swapped:
        return {**base, "reason": "teams do not match the forecast pairing"}

    s1, s2 = _int(sides[1].series_score), _int(sides[2].series_score)
    w1, w2 = sides[1].is_winner, sides[2].is_winner
    flags_ok = all(isinstance(w, (bool,)) or type(w).__name__ == "bool_" for w in (w1, w2))
    if (s1 is None or s2 is None or not flags_ok or not _decisive(s1, s2, meta.get("best_of"))
            or bool(w1) != (s1 > s2) or bool(w2) != (s2 > s1)):
        return {**base, "reason": "series score or winner flags are not a decisive result"}

    scheduled = pd.to_datetime(meta.get("scheduled_at"), utc=True, errors="coerce")
    if pd.isna(completed) or (pd.notna(scheduled) and completed.normalize() < scheduled.normalize()):
        return {**base, "reason": "completion date missing or before the scheduled day"}

    flip = swapped
    map_rows = _maps(maps, s1 + s2, s1, s2)
    oriented = [{"number": m["number"], "map": m["map"],
                 "rounds_a": m["rounds_2"] if flip else m["rounds_1"],
                 "rounds_b": m["rounds_1"] if flip else m["rounds_2"]} for m in map_rows or []]
    maps_a, maps_b = (s2, s1) if flip else (s1, s2)
    winner = "a" if maps_a > maps_b else "b"
    p_winner = None
    if p_team_a is not None and pd.notna(p_team_a) and 0 <= float(p_team_a) <= 1:
        p_winner = float(p_team_a) if winner == "a" else 1 - float(p_team_a)
    return {**base, "status": "verified", "winner": winner, "maps_a": maps_a, "maps_b": maps_b,
            "maps": oriented, "maps_complete": map_rows is not None,
            "pre_start_winner_p": p_winner}


def history_keys(teams: pd.DataFrame | None, team_a_key: str, team_b_key: str) -> tuple[str, str]:
    """Upgrade a logged ``name:`` key to the numeric ID of the *same* canonical side.

    Forecasts logged before team-ID resolution carry name keys, while history
    (form, maps, head-to-head) is keyed on the resolved numeric ID. Upgrade only
    when this match's two canonical rows map one-to-one onto the forecast sides
    (same rule as ``result_detail``); otherwise keep the logged keys unchanged.
    """
    a, b = str(team_a_key), str(team_b_key)
    if teams is None or teams.empty or a == b:
        return a, b
    sides = {_int(row.team_number): row for row in teams.itertuples()}
    if set(sides) != {1, 2}:
        return a, b
    keys = {n: identity_key(sides[n].team_id, sides[n].team_name) for n in (1, 2)}
    names = {n: {keys[n], identity_key(None, sides[n].team_name)} for n in (1, 2)}
    straight = a in names[1] and b in names[2]
    swapped = a in names[2] and b in names[1]
    if keys[1] is None or keys[2] is None or keys[1] == keys[2] or straight == swapped:
        return a, b
    return (keys[1], keys[2]) if straight else (keys[2], keys[1])


def load_history_keys(match_id: int, team_a_key: str, team_b_key: str) -> tuple[str, str]:
    """Read this match's canonical team rows and apply ``history_keys``."""
    with db.connect(read_only=True) as con:
        teams = con.execute("""
            SELECT team_number, team_id, team_name FROM match_team
            WHERE match_id = ? ORDER BY team_number
        """, [match_id]).df()
    return history_keys(teams, team_a_key, team_b_key)


def load_result(match_id: int, team_a_key: str, team_b_key: str,
                p_team_a: float | None = None) -> dict | None:
    """Read canonical rows for one match from the (read-only) DB."""
    with db.connect(read_only=True) as con:
        meta = con.execute("""
            SELECT match_id, status, completed_at, scheduled_at, best_of, vlr_url, last_seen_at
            FROM match WHERE match_id = ?
        """, [match_id]).df()
        if meta.empty:
            return None
        teams = con.execute("""
            SELECT team_number, team_id, team_name, series_score, is_winner
            FROM match_team WHERE match_id = ? ORDER BY team_number
        """, [match_id]).df()
        maps = con.execute("""
            SELECT mm.map_number, mm.map_name,
                   max(CASE WHEN s.team_number = 1 THEN s.total_rounds END) AS rounds_1,
                   max(CASE WHEN s.team_number = 2 THEN s.total_rounds END) AS rounds_2
            FROM match_map mm LEFT JOIN match_map_team_score s USING (match_map_id)
            WHERE mm.match_id = ? GROUP BY mm.map_number, mm.map_name ORDER BY mm.map_number
        """, [match_id]).df()
    record = meta.iloc[0].to_dict()
    teams["is_winner"] = teams.is_winner.astype(object).where(teams.is_winner.notna(), None)
    return result_detail(record, teams, maps, team_a_key, team_b_key, p_team_a)
