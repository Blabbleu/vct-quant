# Full-veto source audit — 2026-09-25

**Read-only probe:** `python scripts/veto_source_audit.py --live --limit 8`
against the configured self-hosted [vlrggapi](https://github.com/axsddlr/vlrggapi)
`/v2/match` and `/v2/match/details` endpoints. The API exposes a `map_vetos`
string separately from its `maps` array. Example retrospective [VLR match
595657](https://www.vlr.gg/595657/) returned a seven-decision text veto, even
though map rows' `picked_by` fields were blank. Thus the prior DB-only 0/1,853
pick count does **not** establish that vlr.gg lacks veto text; it establishes
that the canonical map table has not stored it.

- Of 60 existing immutable match-detail snapshots, 56 are `final`, 19 have
  nonempty `map_vetos`, and 18 contain parseable seven-map Bo3/Bo5 sequences
  with 2/4 picks and a decider. One nonempty field is `VOD Unavaliable` and is
  not a veto. **All 18 complete sequences were observed in final-page
  snapshots**, not before match start. Their retrospective availability cannot
  validate a pre-series model.
- At 2026-09-25 05:03 UTC, the first 8 upcoming fixtures (starting between
  09:00 UTC that day and 12:00 UTC on Sep 29) each returned a detail page
  **before** its scheduled start, but all 8 `map_vetos` were empty and their
  three map names were `TBD`. The read-only probe did not preserve these API
  responses under `data/raw`; it is a feasibility observation, **not** a
  training/validation set. The API may publish vetoes closer to kickoff or
  only after it; this probe cannot tell.
- `/v2/match/details` can have missing segments or errors. The audit counts
  those separately rather than declaring a missing veto. A failed upstream
  `/v2/match` feed is also distinct: at 05:11 UTC the local proxy returned
  HTTP 502/503 for both upcoming matches and events (upstream circuit open);
  the CLI reports `feed_api_errors=1` and exits nonzero, not `0/0` vetoes.
  `--live --within-hours 1 --limit 8` filters the **whole** upcoming feed by
  scheduled start before limiting to the nearest fixtures; `window_eligible=0`
  means no near-start candidates, not evidence that vetoes are missing. The
  probe is read-only; leave historical raw untouched and do not add a
  dev-worktree collector aimed at the live raw symlink.
- A `TBD`/missing fixture timestamp now increments `invalid_start` without
  preventing other fixture probes. A detail already marked `final` despite
  its fixture's future start increments `stale_final_detail` and cannot count
  as a pre-start veto: the upcoming date may be stale after rescheduling.
  A detail explicitly marked live/in progress, or containing a map with a
  nonzero round score despite a future feed timestamp, is likewise excluded
  (`stale_started_detail` / `stale_played_map`). Those guards prevent a stale
  fixture date from turning post-start veto text into supposed pre-start
  evidence. These cases are unknown, not negative veto observations. Tests
  cover the near-start and unfiltered paths. At 07:55 UTC the live feed still
  returned HTTP 502; no new veto observation was made. The read-only probe now
  rejects HTTP-200 error/malformed envelopes, bad fixture links, malformed
  detail maps, and missing/mismatched detail match IDs rather than counting a
  false negative or accepting a false positive. Duplicate fixture IDs with
  conflicting slugs or start times are excluded entirely from the eligible
  set (`duplicate_fixture_rows`), not probed twice. At 08:09 UTC the within-hour
  probe still received HTTP 502, and the independent event/upcoming title audit
  returned 503/503: neither is a new observation. These are source-integrity
  guards, not evidence of pre-start veto availability. A future feed date
  with a nonzero team series score in the detail page is also excluded
  (`stale_series_score`), even if its status says `scheduled` and map rows are
  absent. Numeric and string scores are covered; 0–0 stays eligible. The
  08:15 UTC within-hour probe again received feed HTTP 503, so this guard has
  no new real near-start observation. The archived audit now requires the
  payload `match_id` to match its snapshot filename; a wrong-ID detail cannot
  inflate retrospective veto coverage. All 60 archived snapshots pass this
  identity check (18 full vetoes); the ~08:22 UTC near-start feed still returned
  HTTP 502, so pre-start availability remains unobserved.

**Decision:** source is promising for *retrospective* complete-veto text but
unproven for *pre-start* forecasts. Do not backfill and score historical
`map_vetos` as if they were contemporaneous. Continue occasional pre-start
checks, especially within 1h of kickoff; only a full sequence fetched and
recorded before the scheduled start can enter a prospective pre-series cohort.
A real collector needs prior approval because it would write immutable raw
snapshots on the live side. Specify match ID, request and response UTC times,
scheduled UTC start, full untouched payload, parse validity, and revision
history; reject response times at/after start, placeholders, incomplete seven-
map sequences, and fixture reschedules unless reconciled. The map model itself
remains rejected on the prior conditional played-map test (series-mean t=-0.79
on 2023–24 validation); source feasibility is separate from model quality.
