"""Ops panel: data freshness per source and matchday refresh health.

Read-only and offline. Everything comes from files the pipeline already
writes: the matchday cron log (``data/interim/matchday.log``), the raw
snapshot filenames under ``data/raw`` (each carries its UTC fetch time), the
prediction log and the canonical tables. Nothing here calls vlrggapi or
Polymarket, so opening the page never touches an upstream source, and nothing
feeds ratings, forecasts, grading or the checkpoint rule.

Status rules (fixed here, shown on the page):

* ``ok``: the latest finished matchday run refreshed forecasts.
* ``degraded``: the latest finished run skipped or failed, but a successful
  refresh happened within ``STALE_HOURS``.
* ``stale``: no successful refresh within ``STALE_HOURS`` (the cron runs every
  two hours, so this is three missed refreshes).
* ``unknown``: no matchday log on this checkout.

A run whose block has no terminal line and started under ``RUNNING_MINUTES``
ago is treated as in progress and ignored for status.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import DB_PATH, INTERIM_DIR, PROCESSED_DIR, RAW_POLYMARKET_DIR, RAW_VLRGG_DIR

STALE_HOURS = 6.0
RUNNING_MINUTES = 30
MAX_LOG_BYTES = 512 * 1024
RECENT_RUNS = 12

HEADER = re.compile(r"^=== (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z\s*$")
FETCHED = re.compile(r"^Fetched (\d+) upcoming entries; retained (\d+) official")
GRADED = re.compile(r"^n = (\d+)\s*$")
RAW_STAMP = re.compile(r"_(\d{8}T\d{6})Z(?:_\d{4})?\.json$")

VLRGG_SOURCES = {
    "events": "events_page",
    "event_matches": "event_matches_",
    "upcoming": "match_upcoming_",
    "match_details": "match_details_",
}
MARKET_SOURCES = {"polymarket": "valorant_events_"}


def _hours(delta) -> float:
    return round(delta.total_seconds() / 3600, 2)


def parse_matchday_log(text: str) -> list[dict]:
    """One dict per ``=== <UTC>`` block, oldest first."""
    runs: list[dict] = []
    current: dict | None = None
    lines: list[str] = []

    def close():
        if current is not None:
            runs.append(_classify(current, lines))

    for line in text.splitlines():
        header = HEADER.match(line)
        if header:
            close()
            lines = []
            current = {"started_at": datetime.fromisoformat(header[1])
                       .replace(tzinfo=timezone.utc).isoformat()}
            continue
        if line.startswith("=== "):
            close()  # malformed header: drop its block rather than misfile it
            current, lines = None, []
            continue
        if current is not None:
            lines.append(line)
    close()
    return runs


def _classify(run: dict, lines: list[str]) -> dict:
    out = {**run, "outcome": "incomplete", "reason": None, "upcoming_fetched": None,
           "upcoming_retained": None, "graded_n": None, "warnings": []}
    failed = False
    for line in lines:
        text = line.strip()
        fetched = FETCHED.match(text)
        if fetched:
            out["outcome"] = "ok"
            out["upcoming_fetched"], out["upcoming_retained"] = map(int, fetched.groups())
            out["reason"] = None
        elif text.startswith("WARNING") or text.startswith("Polymarket unavailable"):
            out["warnings"].append(text)
        elif "; skipping" in text:
            out["outcome"], out["reason"] = "skipped", text
        elif "not refreshing" in text:
            out["outcome"], out["reason"] = "stopped", text
        elif out["outcome"] != "ok" and not line[:1].isspace() and (
                "Error" in text or "Exception" in text) and not text.startswith("Traceback"):
            out["reason"] = text
        elif text.startswith("vct update failed (attempt 2)"):
            failed = True
        elif out["graded_n"] is None and out["outcome"] == "ok" and (graded := GRADED.match(text)):
            out["graded_n"] = int(graded[1])
    if failed and out["outcome"] != "ok":
        out["outcome"] = "failed"
    return out


def summarize_runs(runs: list[dict], now: datetime) -> dict:
    out = {"status": "unknown", "last_run": None, "last_success": None,
           "last_success_age_hours": None, "last_24h": {}, "stale_hours": STALE_HOURS}
    if not runs:
        return out
    started = [datetime.fromisoformat(r["started_at"]) for r in runs]
    finished = [r for r, t in zip(runs, started)
                if not (r["outcome"] == "incomplete"
                        and (now - t).total_seconds() < RUNNING_MINUTES * 60)]
    last_ok = next((r for r in reversed(runs) if r["outcome"] == "ok"), None)
    out["last_run"] = runs[-1]
    out["last_success"] = last_ok
    for r, t in zip(runs, started):
        if (now - t).total_seconds() <= 24 * 3600:
            out["last_24h"][r["outcome"]] = out["last_24h"].get(r["outcome"], 0) + 1
    if last_ok is None:
        out["status"] = "stale"
        return out
    age = _hours(now - datetime.fromisoformat(last_ok["started_at"]))
    out["last_success_age_hours"] = age
    if age > STALE_HOURS:
        out["status"] = "stale"
    elif finished and finished[-1]["outcome"] != "ok":
        out["status"] = "degraded"
    else:
        out["status"] = "ok"
    return out


def newest_raw(directory: Path, prefixes: dict[str, str], now: datetime) -> dict:
    """Newest fetch time per source, read from the snapshot filenames."""
    names = [p.name for p in directory.iterdir()] if directory.is_dir() else []
    out = {}
    for source, prefix in prefixes.items():
        stamps = [m[1] for n in names if n.startswith(prefix) and (m := RAW_STAMP.search(n))]
        if not stamps:
            out[source] = {"fetched_at": None, "age_hours": None, "files": 0}
            continue
        newest = datetime.strptime(max(stamps), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        out[source] = {"fetched_at": newest.isoformat(), "age_hours": _hours(now - newest),
                       "files": len(stamps)}
    return out


def prediction_log_status(log: pd.DataFrame, now: datetime) -> dict:
    empty = {"rows": 0, "matches": 0, "last_forecast_at": None, "age_hours": None,
             "upcoming_matches": 0, "next_scheduled_at": None}
    if log.empty:
        return empty
    predicted = pd.to_datetime(log.predicted_at, utc=True, errors="coerce")
    scheduled = pd.to_datetime(log.scheduled_at, utc=True, errors="coerce")
    frame = pd.DataFrame({"match_id": log.match_id, "predicted": predicted, "scheduled": scheduled})
    latest = frame.sort_values("predicted").groupby("match_id").tail(1)
    future = latest.loc[latest.scheduled.gt(pd.Timestamp(now))]
    last = predicted.max()
    return {
        "rows": int(len(log)), "matches": int(frame.match_id.nunique()),
        "last_forecast_at": None if pd.isna(last) else last.isoformat(),
        "age_hours": None if pd.isna(last) else _hours(now - last.to_pydatetime()),
        "upcoming_matches": int(future.match_id.nunique()),
        "next_scheduled_at": None if future.empty else future.scheduled.min().isoformat(),
    }


def _read_tail(path: Path) -> str | None:
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        size = handle.seek(0, os.SEEK_END)
        handle.seek(max(0, size - MAX_LOG_BYTES))
        text = handle.read().decode("utf-8", errors="replace")
    # A cut mid-file starts inside some block; drop up to the first header.
    if size > MAX_LOG_BYTES:
        cut = text.find("\n=== ")
        text = text[cut + 1:] if cut >= 0 else ""
    return text


def _database(now: datetime) -> dict:
    out: dict = {"modified_at": None, "age_hours": None, "matches": None,
           "latest_completed_on": None, "latest_seen_at": None}
    if not DB_PATH.exists():
        return out
    modified = datetime.fromtimestamp(DB_PATH.stat().st_mtime, tz=timezone.utc)
    out.update(modified_at=modified.isoformat(), age_hours=_hours(now - modified))
    from .db import connect
    con = connect(read_only=True)
    try:
        matches, completed, seen = con.execute(
            "SELECT count(*), max(completed_at), max(last_seen_at) FROM match").fetchone()
    finally:
        con.close()
    out["matches"] = int(matches)
    out["latest_completed_on"] = None if completed is None else pd.Timestamp(completed).date().isoformat()
    out["latest_seen_at"] = None if seen is None else pd.Timestamp(seen).tz_convert("UTC").isoformat()
    return out


def build(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    log_path = Path(os.getenv("VCT_MATCHDAY_LOG", INTERIM_DIR / "matchday.log"))
    text = _read_tail(log_path)
    runs = parse_matchday_log(text) if text is not None else []
    matchday = summarize_runs(runs, now)
    matchday["log_found"] = text is not None
    matchday["recent_runs"] = runs[-RECENT_RUNS:][::-1]
    pred_path = PROCESSED_DIR / "prediction_log.parquet"
    log = pd.read_parquet(pred_path) if pred_path.exists() else pd.DataFrame()
    return {
        "generated_at": now.isoformat(),
        "matchday": matchday,
        "sources": {**newest_raw(RAW_VLRGG_DIR, VLRGG_SOURCES, now),
                    **newest_raw(RAW_POLYMARKET_DIR, MARKET_SOURCES, now)},
        "prediction_log": prediction_log_status(log, now),
        "database": _database(now),
        "note": ("Read from files the pipeline already writes; this page never calls an "
                 "upstream source. Fetch times come from raw snapshot filenames (UTC)."),
    }


def main() -> None:
    print(json.dumps(build(), allow_nan=False))


if __name__ == "__main__":
    main()
