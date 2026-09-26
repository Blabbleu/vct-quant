# Forfeit and winner-label integrity

Status: **read-only audit + counterfactual; no primary forecast change.**
Scripts: `scripts/winner_integrity_audit.py`, `scripts/forfeit_label_impact.py`.

## Why

`docs/placeholder-sensitivity.md` found event match 97028 stored with the
wrong winner: the vlr.gg feed marks IlluZion the winner of a forfeit by TBD,
but the additive event loader computes `score_a > score_b`, and `0 > NaN` is
false, so TBD was stored as the winner. The audit here asks the general
question for every completed Tier-1/2/GC match in the DB snapshot: does the
stored `is_winner` agree with the stored score, and with the source feed's own
explicit `is_winner` flags (latest valid archived `event_matches_*` snapshot)?

Elo's label is `CASE WHEN a.is_winner THEN 1 WHEN b.is_winner THEN 0 ELSE 0.5`
and `margin_signal` falls back to that label when no map was scored. So a
stored 0-0 with NULL flags is replayed as a **draw** (both teams pulled toward
each other), and a forfeit with a missing score is replayed by whatever the
flags say.

## Audit (dev DB snapshot, 2026-09-26)

`python scripts/winner_integrity_audit.py`, 38,658 completed matches; 29,205
archived feed rows carry exactly one winner flag.

| class | Tier 1 | Tier 2 | GC |
| --- | ---: | ---: | ---: |
| stored winner consistent with stored score | 12,021 | 14,487 | 11,431 |
| played draw (Bo2 1-1 / 2-2), NULL flags | 71 | 83 | 5 |
| **0-0, no winner stored (replayed as a draw)** | **8** | **220** | **240** |
| **winner stored with one side's score missing** | **1** | **79** | **12** |

Against the feed: every 0-0/no-winner row that has a feed winner (8 / 218 /
233) is a forfeit the feed resolves to one side; every missing-score row that
has a feed winner (1 / 78 / 12) is stored **flipped** (the `0 > NaN` bug:
the real team is marked loser and the `TBD` placeholder winner). Tier 1: 2,436
agree by name, 300 agree by position where Kaggle and vlr.gg spell a team
differently, and 0 disagree except 97028 and 78157. 78157 is a feed defect,
not a DB defect: the feed scores it 1-2 but flags team 1 the winner; the DB
follows the score and 3 stored maps. The audit classes this
`feed_self_contradicts` (1 Tier 1, 2 Tier 2, 5 GC).

All 9 Tier-1 rows are 2022 (IDs 76139-98525). The GC pool has 252 affected
rows spread across its history, and GC forecasts are published.

## Counterfactual rule (written before running the impact script)

Variants, replayed with production settings (`margin_signal`, `elo_k`):

* **current**: the DB as stored.
* **skip** (preferred on principle): drop from the replay every completed
  match with no scored map (either side's series score missing, or 0-0 with no
  winner). A forfeit carries no performance information; Elo should neither
  call it a draw nor credit a win nobody played. Played Bo2 draws stay.
* **feed-winner**: keep those rows but label them with the feed's explicit
  winner as a binary result (and fix the flipped ones). Descriptive only.

Scoring: pre-match probabilities on resolved 2025-2026 matches of each pool
(Tier 1 in the official replay, GC in its own pool), paired per-match log-loss
difference vs current, positive t = variant better. 2025-26 has been consulted
before, so this is **not** a clean holdout and the numbers are a no-harm check,
not evidence of a gain.

Decision rule: propose **skip** as a data-correctness fix if, in each pool,
its paired t vs current is > -2 (no significant harm). If either pool shows
t <= -2, do not propose it for that pool and document why. Either way, it
changes emitted probabilities, so switching it on needs the owner's approval;
it would be built behind an opt-in flag first. A live-DB repair of the stored
flags is a separate decision.

## Results

`python -m scripts.forfeit_label_impact` (dev DB snapshot 2026-09-26):

| pool | unscored rows in replay | n scored 2025-26 | current | skip | skip t | skip max abs dp | feed-winner | feed t |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| official (Tier 1 scored) | 308 (9 T1, 299 T2 at weight 0) | 1,096 | 0.658685 | 0.658688 | -1.38 | 0.00013 | 0.658691 | -1.35 |
| Game Changers | 252 | 5,652 | 0.622753 | 0.622556 | **+2.43** | 0.040 | 0.622719 | +0.12 |

* **Rule applied: skip passes in both pools** (t > -2). Tier 1 is
  numerically a no-op: every 2025-26 probability moves by at most 0.00013 and
  the 8 cached Tier-1 fixtures by at most 0.00009 (Karmine Corp-NRG 0.38442
  -> 0.38433). The t of -1.38 is on a mean difference of 0.0000025/match. The
  largest final-rating changes are the anonymous `name:tbd` key (-28) and
  IlluZion 4529 (+26, the 97028 flip; neither is in a current fixture).
* Game Changers gains: 0.6228 -> 0.6226 on 5,652 matches, the placeholder
  `name:tbd` key loses 202 rating points of fake wins, and GC probabilities
  move by up to 0.04. 2025-26 was consulted before (not a clean holdout), so
  read this as "correct and not harmful", not as a model improvement.
* Feed-winner relabelling is worse than skipping in both pools; a forfeit
  win is not evidence of strength. Rejected.
* Walk-forward Tier-1 benchmark with the flag on: 0.6567 / 0.2320 / 61.6%,
  unchanged to 4 decimals (n 1,678 -> 1,688 only because dropping 308 rows
  moves the positional fold boundaries).

Built behind `features.build.SKIP_UNSCORED_FORFEITS` (default **off**), applied
inside `match_sequence` so every consumer (forecasts, rankings, shadows,
backtests, Match Center history) sees the same sequence. Turning it on changes
emitted GC probabilities, so it needs the owner's approval. The DB rows
themselves are not repaired; the 91 flipped official/GC `is_winner` rows (1 Tier 1, 78 Tier 2, 12 GC) still
show the wrong winner in any descriptive view that reads them directly (team
pages filter to scored maps, so they are already hidden there).
