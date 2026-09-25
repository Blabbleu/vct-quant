# Open-era roster coverage audit (dev snapshot, 2026-09-25)

Run read-only: `vctdev python scripts/open_roster_coverage.py`. This joins the
canonical `match_sequence` to event title/completion metadata and counts teams
with at least five player IDs/handles from loaded map stats. Calendar-year
coverage is based on **completed_at**, not `date_raw` (the latter is NULL for
many harvested event rows). The 2027 target cohort instead uses **2027 in the
event title**, so November 2026 qualifiers are included.

- Tier 2: 2023 **0/7,946**, 2024 **0/9,016**, 2025 **0/5,594**, and 2026
  **0/6,640** eligible sides have a five-player lineup in the DB snapshot.
- Tier 1: 2026 **720/1,180** sides have a five-player lineup (590 dated matches).
- 2027 open-stage completed matches: **0**; no actual qualifier lineup/source
  can be evaluated yet. The 18 cached official fixtures previously had zero
  identifiable inherited sources, and most are already-rated teams or TBDs.

**Consequence.** The roster carry-over shadow only inherits for a new Tier-1
team when its latest observed lineup contains an en-bloc core from a rated
team. With the current Tier-2 detail coverage, a new team entering through
2027 open qualifiers will usually have no known lineup; the shadow silently
falls back to 1500. Historical parity/backtest improvement does **not** prove
prospective viability. No production promotion based on these results.

`open_roster_coverage.py` reports the *latest three completed open-stage
matches per named team* whose map/player detail is missing, deduped by match
ID. It ranks before filtering missing stats, so older missing games cannot
crowd out the most recent lineup. This is a read-only target list, not a
collector: **do not write under the dev worktree's symlinked `data/raw`**. When
real 2027 titles/results appear, assess the size and availability of match
details, then arrange an approved live-side fetch/load (or a safe separate
collector) and rerun the audit. If detail payloads omit players, seek a
pre-match roster source rather than inferring from future results. The script
uses completed lineups only for subsequent forecasts, never the fixture's own
post-match stats.
