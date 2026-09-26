"""Audit the stage-label best-of rule against played series scores.

    python scripts/audit_series_format.py [--since 2023]

The upcoming feed has no format field, so `etl.events.series_best_of` infers
Bo3/Bo5 from the stage label. A played series reveals its format when the
winner took three maps (Bo5) or exactly two (Bo3 -- a 2-x in a Bo5 is
impossible, so 2 maps means Bo3). Bo1 round scores and forfeits are skipped.
Read-only: uses the archived event-match feeds and the event table.
"""
from __future__ import annotations

import argparse
import re

import pandas as pd


def legacy_best_of(event: str | None, series: str | None) -> int:
    """The pre-2026-09-26 rule: Bo5 only for a grand final."""
    return 5 if "grand final" in str(series or "").lower() else 3


def label_outcomes(rows: pd.DataFrame, rule=None) -> pd.DataFrame:
    """Per tier and predicted format, how often the winner needed 2 vs 3 maps.

    `rows` has event_name, series, tier, score_a, score_b.
    """
    from vct_quant.etl.events import series_best_of

    rule = rule or series_best_of
    d = rows.copy()
    d["winner_maps"] = d[["score_a", "score_b"]].max(axis=1)
    d = d[d.winner_maps.isin([2, 3])]
    d["rule"] = [rule(e, s) for e, s in zip(d.event_name, d.series)]
    d["observed"] = d.winner_maps.map({2: 3, 3: 5})
    d["ok"] = d.rule.eq(d.observed)
    out = d.groupby(["tier", "rule"]).agg(n=("ok", "size"), agree=("ok", "sum")).reset_index()
    out["agree"] = out.agree.astype(int)
    out["share"] = out.agree / out.n
    return out


def _archived_rows(since: int) -> pd.DataFrame:
    from vct_quant import db
    from vct_quant.etl.normalize import _archive_chronological_paths, _archived_feed_rows

    rows = []
    for path in _archive_chronological_paths("event_matches_*.json"):
        event_id = int(re.search(r"event_matches_(\d+)_", path.name).group(1))
        for seg in _archived_feed_rows(path):
            rows.append({
                "event_id": event_id, "match_id": seg.get("match_id"),
                "series": seg.get("event_series"), "status": str(seg.get("status", "")),
                "score_a": pd.to_numeric(seg["team1"].get("score"), errors="coerce"),
                "score_b": pd.to_numeric(seg["team2"].get("score"), errors="coerce"),
            })
    d = pd.DataFrame(rows)
    d = d[d.status.str.lower().eq("completed")].drop_duplicates("match_id", keep="last")
    con = db.connect(read_only=True)
    try:
        events = con.execute("SELECT event_id, name AS event_name, tier FROM event").df()
    finally:
        con.close()
    d = d.merge(events, on="event_id", how="inner")
    year = pd.to_numeric(d.event_name.str.extract(r"(20\d\d)")[0], errors="coerce")
    return d[d.tier.isin([1, 2, 3]) & year.ge(since)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=int, default=2023)
    args = parser.parse_args()
    rows = _archived_rows(args.since)
    fmt = {"share": "{:.3f}".format}
    for name, rule in (("current", None), ("legacy grand-final-only", legacy_best_of)):
        out = label_outcomes(rows, rule)
        print(f"\n{name} rule vs played winner map count ({args.since}+)")
        print(out.to_string(index=False, formatters=fmt))
        by_tier = out.groupby("tier")[["n", "agree"]].sum()
        print("  agreement by tier:", {int(t): f"{r.agree}/{r.n}" for t, r in by_tier.iterrows()})


if __name__ == "__main__":
    main()
