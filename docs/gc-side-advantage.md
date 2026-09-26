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

(Filled in after the run.)
