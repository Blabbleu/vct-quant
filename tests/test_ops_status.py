"""Ops panel: data freshness and matchday refresh health, read-only."""
from datetime import datetime, timezone

import pandas as pd

from vct_quant.ops_status import (
    newest_raw, parse_matchday_log, prediction_log_status, summarize_runs,
)

NOW = datetime(2026, 9, 26, 6, 0, tzinfo=timezone.utc)

OK_RUN = """=== 2026-09-26T02:15:01Z
Refreshed 15 recent official events
Inserted:
  event metadata upserted          2,034
Fetched 18 upcoming entries; retained 18 official -> /x/upcoming_tier1.parquet
n = 6
log loss 0.5837   (backtest 0.6567, coin flip 0.6931)
"""


def test_parses_ok_skipped_and_failed_runs_in_order():
    text = (
        "=== 2026-09-25T08:15:01Z\nTraceback (most recent call last):\n"
        "requests.exceptions.HTTPError: 502 Server Error\nvct update failed (attempt 1)\n"
        "Traceback (most recent call last):\nvct update failed (attempt 2)\n"
        + OK_RUN
        + "=== 2026-09-26T04:15:01Z\nevents feed unavailable; skipping update\n"
    )
    runs = parse_matchday_log(text)
    assert [r["outcome"] for r in runs] == ["failed", "ok", "skipped"]
    assert runs[0]["started_at"] == "2026-09-25T08:15:01+00:00"
    assert "502" in runs[0]["reason"]
    assert runs[1]["upcoming_fetched"] == 18 and runs[1]["upcoming_retained"] == 18
    assert runs[1]["graded_n"] == 6
    assert runs[2]["reason"] == "events feed unavailable; skipping update"


def test_retry_that_succeeds_is_ok_and_unfinished_last_block_is_incomplete():
    text = ("=== 2026-09-26T00:15:01Z\nTraceback (most recent call last):\n"
            "vct update failed (attempt 1)\nRefreshed 15 recent official events\n"
            "Fetched 3 upcoming entries; retained 2 official -> p\n"
            "=== 2026-09-26T02:15:01Z\nRefreshed 15 recent official events\n")
    runs = parse_matchday_log(text)
    assert runs[0]["outcome"] == "ok" and runs[0]["upcoming_retained"] == 2
    assert runs[1]["outcome"] == "incomplete"


def test_other_skip_reasons_stop_and_warnings():
    text = ("=== 2026-09-26T00:15:01Z\nvlrggapi on :3001 is down; skipping (start it)\n"
            "=== 2026-09-26T01:15:01Z\nprevious refresh still running; skipping\n"
            "=== 2028-01-01T00:15:01Z\npast 2027-12-31; not refreshing (remove the crontab line)\n"
            "=== 2026-09-26T02:15:01Z\nWARNING: untiered VCT-branded event 'VCT 2027: X'\n"
            "Fetched 1 upcoming entries; retained 1 official -> p\n")
    runs = parse_matchday_log(text)
    assert [r["outcome"] for r in runs] == ["skipped", "skipped", "stopped", "ok"]
    assert runs[3]["warnings"] == ["WARNING: untiered VCT-branded event 'VCT 2027: X'"]


def test_malformed_header_and_empty_log():
    assert parse_matchday_log("") == []
    assert parse_matchday_log("stray line\n=== not-a-date\nFetched 1 upcoming entries; retained 1 official -> p\n") == []


def test_summary_status_ok_degraded_stale_unknown():
    ok = {"started_at": "2026-09-26T04:15:01+00:00", "outcome": "ok"}
    skip = {"started_at": "2026-09-26T05:15:01+00:00", "outcome": "skipped", "reason": "x"}
    old_ok = {"started_at": "2026-09-25T20:15:01+00:00", "outcome": "ok"}
    assert summarize_runs([], NOW)["status"] == "unknown"
    s = summarize_runs([ok], NOW)
    assert s["status"] == "ok" and s["last_success_age_hours"] == 1.75
    s = summarize_runs([ok, skip], NOW)
    assert s["status"] == "degraded" and s["last_run"]["outcome"] == "skipped"
    assert s["last_success"]["started_at"] == ok["started_at"]
    s = summarize_runs([old_ok, skip], NOW)
    assert s["status"] == "stale"
    assert summarize_runs([skip], NOW)["status"] == "stale"
    assert summarize_runs([skip], NOW)["last_success"] is None
    # A run in progress is not treated as a failure.
    running = {"started_at": "2026-09-26T05:59:00+00:00", "outcome": "incomplete"}
    assert summarize_runs([ok, running], NOW)["status"] == "ok"
    # Counts over the trailing 24 hours only.
    assert summarize_runs([old_ok, ok, skip], NOW)["last_24h"] == {"ok": 2, "skipped": 1}


def test_newest_raw_by_filename_timestamp(tmp_path):
    for name in ["match_upcoming_20260926T021519Z.json", "match_upcoming_20260925T221520Z.json",
                 "match_upcoming_20260926T021519Z_0001.json", "events_page001_20260926T001522Z.json",
                 "event_matches_2766_20260926T021530Z.json", "match_details_753454_20260926T021540Z.json",
                 "notes.txt"]:
        (tmp_path / name).write_text("{}")
    got = newest_raw(tmp_path, {"upcoming": "match_upcoming_", "events": "events_page",
                                "details": "match_details_", "missing": "nope_"}, NOW)
    assert got["upcoming"]["fetched_at"] == "2026-09-26T02:15:19+00:00"
    assert got["upcoming"]["files"] == 3
    assert got["upcoming"]["age_hours"] == 3.74
    assert got["events"]["fetched_at"] == "2026-09-26T00:15:22+00:00"
    assert got["details"]["files"] == 1
    assert got["missing"] == {"fetched_at": None, "age_hours": None, "files": 0}
    assert newest_raw(tmp_path / "absent", {"x": "x_"}, NOW)["x"]["files"] == 0


def test_prediction_log_status():
    log = pd.DataFrame({
        "match_id": [1, 1, 2, 3],
        "predicted_at": pd.to_datetime(["2026-09-25T20:15Z", "2026-09-26T02:15Z",
                                        "2026-09-26T02:15Z", "2026-09-26T02:15Z"], utc=True),
        "scheduled_at": pd.to_datetime(["2026-09-26T08:00Z", "2026-09-26T08:00Z",
                                        "2026-09-25T08:00Z", "2026-09-27T09:00Z"], utc=True),
        "tier": [1, 1, 3, 1],
    })
    s = prediction_log_status(log, NOW)
    assert s["rows"] == 4 and s["matches"] == 3
    assert s["last_forecast_at"] == "2026-09-26T02:15:00+00:00"
    assert s["upcoming_matches"] == 2
    assert s["next_scheduled_at"] == "2026-09-26T08:00:00+00:00"
    assert prediction_log_status(pd.DataFrame(), NOW) == {
        "rows": 0, "matches": 0, "last_forecast_at": None, "age_hours": None,
        "upcoming_matches": 0, "next_scheduled_at": None}
