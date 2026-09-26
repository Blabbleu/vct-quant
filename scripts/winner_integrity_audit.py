"""Read-only audit: does each stored series winner match its score and source?

    python scripts/winner_integrity_audit.py [--tier 1] [--list 40]

Motivation (docs/placeholder-sensitivity.md): event match 97028 was forfeited
by TBD, the vlr.gg feed marked IlluZion the winner, but the additive event
loader derived the winner from ``score_a > score_b`` and ``0 > NaN`` is false,
so the DB stores TBD as winner. That is one instance of a general question:
where does the stored ``is_winner`` disagree with (a) the stored series score
or (b) the source feed's own explicit ``is_winner`` flags?

Elo reads the label as ``CASE WHEN a.is_winner THEN 1 WHEN b.is_winner THEN 0
ELSE 0.5``, so both-false rows are silently scored as draws, and both-NULL rows
are legitimate only for a genuinely drawn Bo2.

This script never writes the DB or raw data. It classifies; it does not repair.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import duckdb
import pandas as pd

from vct_quant import db
from vct_quant.etl.entity_resolution import normalize_name


_SQL = """
SELECT m.match_id, e.tier, m.best_of, m.vlr_url,
       a.team_name AS name_a, b.team_name AS name_b,
       a.series_score AS score_a, b.series_score AS score_b,
       a.is_winner AS win_a, b.is_winner AS win_b,
       (SELECT count(*) FROM match_map mm WHERE mm.match_id = m.match_id) AS n_maps
FROM "match" m
JOIN event e ON e.event_id = m.event_id
JOIN match_team a ON a.match_id = m.match_id AND a.team_number = 1
JOIN match_team b ON b.match_id = m.match_id AND b.team_number = 2
WHERE lower(m.status) = 'completed' AND e.tier IN (1, 2, 3)
ORDER BY m.match_id
"""


def _flag(v) -> bool | None:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA:
        return None
    return bool(v)


def label(win_a, win_b) -> str:
    """The Elo training label implied by the stored flags."""
    a, b = _flag(win_a), _flag(win_b)
    if a and b:
        return "both_true"
    if a:
        return "a"
    if b:
        return "b"
    if a is False and b is False:
        return "both_false"  # Elo scores this 0.5, but it is not a stored draw
    return "none"  # NULL/NULL (legit only for a drawn Bo2) or half-NULL


def score_winner(score_a, score_b) -> str | None:
    """Winner implied by the stored map score; None if missing or level."""
    if pd.isna(score_a) or pd.isna(score_b):
        return None
    if score_a > score_b:
        return "a"
    if score_b > score_a:
        return "b"
    return "draw"


def classify_db(row) -> str:
    lab = label(row.win_a, row.win_b)
    sw = score_winner(row.score_a, row.score_b)
    if lab == "both_true":
        return "both_flagged_winner"
    if lab == "both_false":
        return "both_false_scored_as_draw"
    if lab == "none":
        # A played draw has maps on the board (1-1, 2-2). 0-0 is a forfeit or
        # no-show with no result recorded, and Elo would still score it 0.5.
        if sw == "draw" and row.score_a > 0:
            return "legit_draw"
        return "scoreless_no_winner" if sw == "draw" else "no_winner_not_draw"
    if sw is None:
        return "winner_without_full_score"
    if sw == "draw":
        return "winner_on_level_score"
    return "consistent" if sw == lab else "winner_contradicts_score"


def feed_winners(paths: list[Path], read_rows) -> pd.DataFrame:
    """Latest completed snapshot per match with exactly one explicit winner flag.

    ``read_rows(path)`` must return validated feed rows (normalize's
    ``_archived_feed_rows``), so poisoned envelopes never count as evidence.
    """
    latest: dict[int, dict] = {}
    for path in paths:
        for seg in read_rows(path):
            if str(seg.get("status", "")).lower() != "completed":
                continue
            try:
                mid = int(seg["match_id"])
            except (KeyError, TypeError, ValueError):
                continue
            t1, t2 = seg.get("team1") or {}, seg.get("team2") or {}
            f1, f2 = t1.get("is_winner"), t2.get("is_winner")
            if not (isinstance(f1, bool) and isinstance(f2, bool)) or f1 == f2:
                continue
            latest[mid] = {
                "match_id": mid,
                "feed_name_1": str(t1.get("name", "")),
                "feed_name_2": str(t2.get("name", "")),
                "feed_score_1": t1.get("score"),
                "feed_score_2": t2.get("score"),
                "feed_winner_side": 1 if f1 else 2,
                "feed_winner_name": str((t1 if f1 else t2).get("name", "")),
                "feed_flag_vs_score": flag_vs_score(t1.get("score"), t2.get("score"), 1 if f1 else 2),
                "feed_file": path.name,
            }
    return pd.DataFrame(latest.values())


def flag_vs_score(score_1, score_2, winner_side: int) -> str:
    """Does the feed's own winner flag agree with its own (map or round) score?"""
    def num(v) -> float | None:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        return None if x != x else x
    a, b = num(score_1), num(score_2)
    if a is None or b is None or a == b:
        return "no_decisive_score"
    return "agrees" if (1 if a > b else 2) == winner_side else "contradicts"


def compare_feed(db_row, feed_row) -> str:
    """Stored winner vs the feed's explicit winner.

    Matched by team name; when names drifted (Kaggle vs vlr.gg spellings) the
    comparison falls back to position, labelled as such. A disagreement where
    the feed's own flag contradicts its own score is a feed defect, not
    evidence against the DB.
    """
    lab = label(db_row.win_a, db_row.win_b)
    names = {normalize_name(str(db_row.name_a)), normalize_name(str(db_row.name_b))}
    feed = {normalize_name(feed_row.feed_name_1), normalize_name(feed_row.feed_name_2)}
    if names != feed or len(names) != 2:
        if lab not in ("a", "b"):
            return "names_differ_db_no_winner"
        same = (lab == "a") == (feed_row.feed_winner_side == 1)
        return "names_differ_agree_by_position" if same else "names_differ_flipped_by_position"
    if lab not in ("a", "b"):
        return "db_has_no_single_winner"
    winner = db_row.name_a if lab == "a" else db_row.name_b
    if normalize_name(str(winner)) == normalize_name(feed_row.feed_winner_name):
        return "agree"
    return "feed_self_contradicts" if feed_row.feed_flag_vs_score == "contradicts" else "flipped"


def audit(con: duckdb.DuckDBPyConnection, feed: pd.DataFrame) -> pd.DataFrame:
    rows = con.execute(_SQL).df()
    rows["db_class"] = [classify_db(r) for r in rows.itertuples(index=False)]
    if feed.empty:
        rows["feed_class"] = "no_feed_winner"
        return rows
    merged = rows.merge(feed, on="match_id", how="left")
    merged["feed_class"] = [
        "no_feed_winner" if pd.isna(r.feed_winner_name) else compare_feed(r, r)
        for r in merged.itertuples(index=False)
    ]
    return merged


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tier", type=int, default=1, help="tier whose anomalies to list")
    ap.add_argument("--list", type=int, default=40, help="max anomaly rows to print")
    ap.add_argument("--csv", type=Path, help="write every row with its classes here")
    args = ap.parse_args(argv)

    from vct_quant.etl.normalize import _archive_chronological_paths, _archived_feed_rows

    feed = feed_winners(_archive_chronological_paths("event_matches_*.json"), _archived_feed_rows)
    with db.connect(read_only=True) as con:
        res = audit(con, feed)
    if args.csv:
        res.to_csv(args.csv, index=False)

    print(f"completed official/GC matches: {len(res)}; feed rows with one explicit winner: {len(feed)}")
    for tier, g in res.groupby("tier"):
        print(f"\ntier {tier}: n={len(g)}")
        for k, v in sorted(Counter(g.db_class).items()):
            print(f"  db  {k:28s} {v}")
        for k, v in sorted(Counter(g.feed_class).items()):
            print(f"  feed {k:27s} {v}")

    bad = res[(res.tier == args.tier)
              & ((~res.db_class.isin(["consistent", "legit_draw"]))
                 | res.feed_class.isin(["flipped", "db_has_no_single_winner"]))]
    print(f"\ntier {args.tier} anomalies: {len(bad)} (showing {min(len(bad), args.list)})")
    cols = ["match_id", "name_a", "name_b", "score_a", "score_b", "win_a", "win_b",
            "n_maps", "db_class", "feed_class", "feed_winner_name"]
    cols = [c for c in cols if c in bad.columns]
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(bad[cols].head(args.list).to_string(index=False))
    print("\nRead-only. Do not edit the live DB or change primary Elo without approval.")


if __name__ == "__main__":
    main()
