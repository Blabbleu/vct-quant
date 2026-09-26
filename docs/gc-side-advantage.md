# Game Changers side-1 advantage (protocol frozen 2026-09-26, before any h-model loss is computed)

## Why

`docs/gc-signal-lab.md` found, descriptively, that the stored side 1 of a GC
match wins about 5 points more often than GC Elo expects, in every year
2022-26 (side-1 win rate 0.587-0.613 vs mean Elo p 0.536-0.557 at K=192).
Tier 1 shows no gap after 2022 (2023-26 side-1 rates 0.526/0.537/0.532/0.470
vs p 0.526/0.543/0.527/0.516).

Is side order pre-match information? Evidence so far:

* The stored side order matches the vlr.gg URL slug `<team1>-vs-<team2>` for
  all 10,009 slug-matchable GC rows (1,654 unmatched by name spelling, 25
  without a name; 0 flipped). A match page's slug is minted when the page is
  created, normally before play.
* The prediction log records the upcoming feed's team1/team2 before kickoff;
  all 6 logged fixtures that have since completed (4 Tier 1, 2 GC) kept the
  same orientation in the canonical tables.
* Only 6 matches were seen both before and after completion in the archived
  event feeds (all same orientation).

Plausible mechanism: vlr.gg lists the higher bracket seed / upper-bracket
side first, which Elo does not see. It is not proven; if side order were ever
set after the result, this would be leakage. The live log is the only fully
clean test and is prospective by construction.

## Protocol

* Data: production GC sequence `match_sequence(tiers=(3,))`, default flags,
  margin signal, one continuous replay. Scored rows `score_a != 0.5`.
* Model H: Elo with a side-1 advantage of h rating points, used in both the
  prediction and the update (`e = 1 / (1 + 10^((rb - ra - h) / 400))`,
  `ra += K (s - e)`, `rb -= K (s - e)`), i.e. standard home-advantage Elo.
  h = 0 is exactly production Elo at that K.
* Tune on `year <= 2024`: grid h in {0, 10, 20, ..., 120}, K in
  {96, 128, 192, 256}. Select the (K, h) with lowest mean log loss. If h sits
  on the grid's top edge, extend h by +20 steps on the tune years only.
* If the selection has h = 0: negative, 2025-26 not scored.
* Otherwise score once on `year >= 2025` against the A73 reference (margin,
  K = 192, h = 0). Paired per-match log-loss difference.
* Decision rule, **stricter than usual because 2025-26 side-1 rates have been
  seen**: propose H iff paired t >= +2.0 on 2025-26 **and** the per-year
  mean loss difference favours H in both 2025 and 2026. Even then, the
  proposal is a GC **shadow column first** (prospective check on the live
  log), not a primary switch, unless the owner says otherwise.
* Reported only: Brier, per-year t, calibration table, a side-1 bias check
  (mean p vs side-1 win rate on the test years).

Not in scope: Tier 1 (no gap after 2022), Tier 2 (zero Elo weight).

## Result

Run 2026-09-26 on the dev DB snapshot (11,688 GC matches),
`python scripts/gc_side_lab.py tune`, then `test`.

Tune (years <= 2024, n = 5,779), mean log loss, h across, K down:

| K | h=0 | 10 | 20 | **30** | 40 | 50 | 60 |
|---|---|---|---|---|---|---|---|
| 96 | .60814 | .60546 | .60354 | .60238 | .60198 | .60232 | .60340 |
| 128 | .59976 | .59744 | .59589 | .59510 | .59507 | .59579 | .59724 |
| **192** | .59272 | .59094 | .58994 | **.58971** | .59026 | .59157 | .59363 |
| 256 | .59449 | .59308 | .59248 | .59268 | .59367 | .59544 | .59798 |

Pick K = 192, h = 30 (interior; h up to 120 all worse).

Test (2025-26, n = 5,664, scored once) vs A73 reference (K = 192, h = 0):

* 0.603787 -> **0.599634, paired t = +3.76**; Brier 0.20988 -> 0.20798.
* 2025: n = 3,298, 0.60200 -> 0.59839, t = +2.51.
  2026: n = 2,366, 0.60627 -> 0.60137, t = +2.85. Both years favour H.
* Side-1 win rate 0.604; mean p 0.549 (h = 0) -> 0.580 (h = 30). h = 30
  closes about 60% of the gap; the < 50% buckets are still hot for side 1.

**Decision under the frozen rule: propose H (K = 192, h = 30) as a GC shadow
column**, graded on the live log before any primary switch. Approval A74.

Caveats: (1) 2025-26 side-1 rates had been seen before this protocol was
written; the rule was tightened for it, but only the live log is clean.
(2) The mechanism (bracket seed listed first) is inferred, not verified from
vlr.gg documentation. If side order were ever assigned after the result, this
is leakage; the slug and the 6 logged fixtures say it is not, and the shadow
would expose it (live fixtures are oriented before kickoff by construction).
(3) h depends on K: combined with A73 only. On production K = 48 it was not
tested.

## Cross-pool order diagnostic (descriptive follow-up, 2026-09-26)

`vctdev python -m scripts.side_order_audit` replays the exact Tier-1 primary
margin Elo (K=48, Tier-2 update weight zero) and the already-frozen GC K=192
h=0/h=30 variants. On decisive, dated matches, side-1 actual minus pre-match
expected win rate in percentage points:

| Year | Tier 1 n | Tier 1 residual | GC n | GC h=0 residual | GC h=30 residual |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2021 | 6,638 | +7.60 | — | — | — |
| 2022 | 3,519 | +8.18 | 1,273 | +6.32 | +2.43 |
| 2023 | 333 | -0.09 | 2,075 | +4.11 | +0.95 |
| 2024 | 436 | -0.62 | 2,431 | +5.49 | +2.28 |
| 2025 | 504 | +0.48 | 3,298 | +5.26 | +2.14 |
| 2026 | 592 | -4.60 | 2,366 | +5.76 | +2.74 |

The archived completed-event feed agrees with canonical order in **all
11,669 GC rows** (19 rows have no usable archived counterpart) by exact
case-insensitive team names; no flipped rows. Tier-1 exact-name overlap:
2022 819 same, 0 flipped, 61 unmatched aliases, 2,647 absent; 2023-26
1,626 same, 0 flipped, 239 unmatched. There is **no 2021 archived
counterpart** for any of its 6,709 canonical Tier-1 rows. In 2022 the
feed-covered decisive subset has side-1 win rate 61.0% versus 53.5% Elo;
feed-absent rows 61.5% versus 53.1%. The historical anomaly is not restricted
to Kaggle-only rows, but post-match feed agreement does not establish that
order was fixed before kickoff.

This corroborates the GC side signal's persistence, **not** its mechanism or
prospective validity. Tier 1's order bias disappears after the league
restructure and reverses in 2026, so do not transfer h=30 to Tier 1 or select
on these already-consulted years. The audit's z value is only a standardized
descriptive residual (independent fixed-Bernoulli approximation), not an
inferential test across dependent matches. Require pre-kickoff side snapshots
in the live log to check the GC shadow, as stated above. No model or rule
changed in this follow-up.

## Prospective orientation gate (2026-09-26)

`vctdev python -m scripts.prospective_side_order` compares the last logged
forecast **strictly before scheduled kickoff** with both canonical sides after
a completed result. It also flags any side reversal across earlier pre-start
log rows; name-key to numeric-ID upgrades of the same side do not count as
reversals. Ambiguous/missing pairings and completion dates preceding the
scheduled day cannot establish orientation. This is a read-only diagnostic,
not a forecast grader and not a clean holdout: a reschedule could put an
ostensibly pre-scheduled-start snapshot after actual play.

On the dev snapshot, 14 matches have a pre-scheduled-start forecast: GC 2/2
completed with unchanged orientation, 0 flips or pre-start reversals; Tier 1
4/4 completed unchanged and 8 still pending. Six completed matches are too
few to establish stable GC source ordering. Re-run after A74 logs the GC
shadow and more GC matches finish; investigate any flip before interpreting
shadow performance. No forecast/log/DB change was made.
