# Series format for upcoming fixtures (2026-09-26)

## Problem

The vlrggapi upcoming feed has no best-of field. `official_upcoming` (and the
match-detail fallback when the map list is not 1/3/5 long) used to infer
**Bo5 only for a grand final**. Riot's Champions Shanghai overview says the
Lower Final is also Bo5 (source pinned in `config/brackets/champions_2026.json`,
`docs/champions-2026-bracket.md` [5]). Every VCT regional Stage and Kickoff
also plays Bo5 lower finals, and the 2026 Kickoffs play a Bo5 "Middle Final".

A wrong best-of does **not** change the series win probability
(`p_team_a_win`): the exact-score distribution is built from the map
probability implied by that series probability for the given format. It does
change every derived number: `score_probabilities`, `most_likely_score`,
`p_sweep` (the desk's "Ends 2-0 either way" tile), `p_full_distance` and
`expected_maps`. Under the old rule the Champions 2026 Lower Final (and any
regional lower final) would show Bo3 scores such as 2-1 that cannot occur, and
omit 3-x scores that must. Two logged Game Changers lower finals (743609,
755377) were logged as Bo3; they went 2-3 and 1-3.

## Rule (`vct_quant.etl.events.series_best_of`)

- Stage label contains `lower final`, `middle final` or `grand final` (not a
  `... Final Quals` qualifier bracket) → **Bo5**; everything else → Bo3.
- Game Changers: only main events (`Game Changers YYYY: China | Pacific |
  Brazil Finals | LATAM Main Event`, and the Championship) use the Bo5 lower
  final. Smaller GC cups/splits keep the legacy behaviour (Bo5 grand final
  only), because their lower finals are mostly Bo3.
- A detail payload listing 1/3/5 maps still wins over the label.

## Evidence (read-only, `python scripts/audit_series_format.py`)

A completed series reveals its format: the winner took 3 maps (Bo5) or exactly
2 (Bo3). Bo1 round scores and forfeits are excluded. Archived event-match feeds,
event titles 2023+, dev DB snapshot of 2026-09-26:

| tier | new rule agrees | legacy rule agrees |
| --- | ---: | ---: |
| 1 | **1,844 / 1,855** | 1,792 / 1,855 |
| 2 | 8,959 / 9,227 | 8,941 / 9,227 |
| 3 (GC) | 7,928 / 8,090 | 7,917 / 8,090 |

Tier-1 labels the new rule calls Bo5 went the Bo5 distance 103/104 times (the
exception: VCT 2026 China Stage 2 Lower Final 724634, scored 0-2 in the feed).
The remaining 10 Tier-1 misses are Bo5 series under other labels (Champions
China Qualifier upper bracket, Kickoff upper finals in 2026, where 4/4 went
3-2). Kickoff 2026 upper finals are **left at Bo3**: 2025's were Bo3 (4/4) and
the 2027 Kickoff format is unannounced, so a year-specific rule would be
guessing. Tier 2 is not forecast (upcoming keeps tiers 1 and 3); its lower
finals are mixed (300/446 Bo5), so the rule is not a claim about Challengers.

This is a **format metadata fix**, not a model change: no rating, parameter
or series probability changes, and the prediction log's historical rows are
left as logged. It still changes the derived score numbers `vct update`
emits for lower/middle-final fixtures, so it ships only with an approved merge.
