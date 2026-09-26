# Champions Shanghai 2026 bracket source and simulation gate

This is a **source-pinned schedule**, not title odds. The machine-readable
`config/brackets/champions_2026.json` captures event 2766, its opening
participants, four groups' five match slots each, and 14 playoff match slots.
It is pinned to the raw read-only event-match snapshot
`data/raw/vlrgg/event_matches_2766_20260926T021503Z.json` (34 rows); the
corresponding event match listing is cited here.[2] Slots are keyed by exact vlr.gg match
IDs, not team-name guesses or a chronological sort. The raw snapshot is not
checked into git; its source-match test skips in clean clones without it.

Riot specifies September 24–October 4 groups (four groups of four, one team
per region, two losses eliminate a team, best-of-three) and October 7–18
**double-elimination** playoffs for the eight survivors.[1] The archived
match list labels the group slots `Opening`, `Winner's`, `Elimination`,
`Decider`, and lists playoff slots from `Upper Quarterfinals` to `Grand Final`
[2]. As of that snapshot, the C/D opening results were known, B/A openings
future; the JSON deliberately does **not** freeze scores or later participant
labels. A refreshed result must come from an ID-checked scored source, never
from this static schedule.

## Before simulating or publishing probabilities

- Bind the 16 opening entrants to **exact team IDs** from validated detail
  or canonical records. An event feed name alone must not create a second
  1500-rated team; unknown ID blocks odds for that entrant.
- Verify the **playoff group-winner/runner-up seeding** and every upper/lower
  advancement edge against an official bracket or a scored/drawn fixture
  graph. Riot's format summary confirms double elimination but does **not**
  specify the exact quarterfinal pairings or lower-bracket crossover. The
  vlr.gg playoff bracket shows all quarterfinal participants as blank as of
  this probe, so it cannot verify group seeding either.[3] Those edges are
  `unresolved` in the JSON. Do not infer them from match IDs or enumerated
  order. A final with bracket-reset semantics is likewise not assumed;
  confirm the final rule before modeling title odds.
- Use a frozen **pre-match** Elo replay for every simulation. Completed
  matches are fixed only from point-in-time scored results; future pairings
  use the primary Elo probability without changing `predict_upcoming` or
  `vct update`. The group and playoff bracket must reject incomplete/duplicate
  winners rather than silently advancing a team. Group advancement is the
  group winners-match winner plus the decider winner; validate it with real
  results before presenting an event page.
- Record Monte Carlo seed, draw count, and binomial Monte Carlo error, then
  test conservation: each draw has exactly two qualifiers per group, one
  champion, and the group-qualified probabilities sum to eight. No outright
  market comparison until a timestamped comparable market is available.

The shipped loader validates 16 unique named entrants and 34 distinct positive
match IDs/stages, including four copies of every group slot type and exact
playoff-stage counts. It refuses unsupported event IDs. This work makes no
API/UI change and no production forecast change.

## Sources

[1] https://valorantesports.com/news/champions-shanghai-everything-you-need-to-know — Champions Shanghai: Everything You Need To Know
[2] https://www.vlr.gg/event/matches/2766/?series_id=all — Valorant Champions 2026 matches
[3] https://www.vlr.gg/event/2766/valorant-champions-2026/playoffs — Valorant Champions 2026 playoff bracket
