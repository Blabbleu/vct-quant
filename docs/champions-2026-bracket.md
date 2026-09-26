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

- The 16 opening entrants are now bound to **exact vlr.gg team IDs** in
  `team_ids`, positional to `teams` for each pinned opening match ID. On
  2026-09-26 03:57–04:00 UTC, read-only `GET /v2/match/details?match_id=<ID>`
  from the local vlrggapi returned ID-checked details for 753444, 753445,
  753449, 753450, 753455, and 753459, with both names and numeric IDs matching
  the schedule. Archived ID-checked detail snapshots for 753454 and 753460
  supplied the other four entrants.[4] No new raw snapshot was written.
  Names alone are **not** proof of identity (JD Gaming and NRG have no exact
  canonical `team.name` in this DB), and the fixture cache's name resolution
  is corroboration, not the source. Recheck those six ephemeral detail
  observations against an archived/official source before publishing odds;
  unknown or contradictory IDs block odds for that entrant.
- Verify the **playoff group-winner/runner-up seeding** and every upper/lower
  advancement edge against an official bracket or a scored/drawn fixture
  graph. Riot's format summary confirms double elimination but does **not**
  specify the exact quarterfinal pairings or lower-bracket crossover. The
  vlr.gg playoff bracket still showed all 14 slots as `TBD vs. TBD` on a
  read-only 2026-09-26 probe, so it cannot verify group seeding either.[3]
  Riot says playoff Pick'Ems open **October 4 after the Draw Show completes**
  and matchups are confirmed.[6] The draw is a future evidence checkpoint,
  not permission to assume a bracket now. Recheck the official drawn pairings
  and lower-bracket graph then. Those edges are `unresolved` in the JSON.
  Do not infer them from match IDs
  or enumerated order. Riot's official event overview confirms group matches
  and all playoff series are Bo3 **except Lower Final and Grand Final, both
  Bo5**; the validated `series_best_of` records this separately.[5] It does
  not state that a grand-final bracket reset is played. The vlr.gg graph has
  one grand-final slot, but slot count alone is not proof of reset semantics;
  confirm the rule before modeling title odds.
- Group advancement is implemented as a **fail-closed routing primitive**,
  exposed descriptively at read-only `GET /api/champions/2766` using the
  canonical DB snapshot. No odds or inferred playoff pairings are emitted.
  Each completed DB result must match its pinned match ID, event, stage,
  distinct positive team IDs, integer series scores and winner flags; opener
  participants must match the pinned exact IDs. The earlier detail adapter
  independently requires an ID-checked final detail with the same safeguards.
  Winners/losers of both openers feed the winner's and elimination slots;
  the winner's loser meets the elimination winner in the decider. The winner's
  winner qualifies immediately; the second qualifier awaits the decider.
  An unverified completed row is listed by match ID and cannot route its team.
  The router also refuses a completed downstream slot without its upstream
  results or with contradictory participants. A played Bo3 final must be 2–0
  or 2–1: a final-flagged 1–0 forfeit, tie, or impossible 3-map win cannot
  silently advance a team. `as_of` identifies the newest canonical row's
  source observation; it does not promise a fresh event-page fetch. The dev DB
  snapshot currently contains four completed C/D openers and no completed
  A/B matches. A read-only 2026-09-26 ~04:07 UTC
  local vlrggapi probe of [2] and `/v2/match/details?match_id=` for the four C/D
  openers matched the next listed pairings: C winner's G2 Esports–Paper Rex
  (753456), C elimination TYLOO–Team Liquid (753457); D winner's Karmine
  Corp–NRG (753461), D elimination Xi Lai Gaming–Nongshim RedForce (753462).
  This checks the **group** edges only; none of the deciders has a final result
  and playoff seeding/crossover remains unresolved. Two opener details are in
  the archived raw files [4]; the other two were read-only observations and
  must be rechecked at publication.
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

The shipped loader validates 16 unique named entrants and 16 distinct positive
team IDs, positional to the eight opening match IDs; it rejects missing or
premature future-participant IDs. It also validates 34 distinct positive
match IDs/stages, including four copies of every group slot type and exact
playoff-stage counts. It refuses unsupported event IDs. The API endpoint is
read-only and descriptive; no UI or production forecast change is included.
Playoff routing and title odds remain gated as above.

## Sources

[1] https://valorantesports.com/news/champions-shanghai-everything-you-need-to-know — Champions Shanghai: Everything You Need To Know
[2] https://www.vlr.gg/event/matches/2766/?series_id=all — Valorant Champions 2026 matches
[3] https://www.vlr.gg/event/2766/valorant-champions-2026/playoffs — Valorant Champions 2026 playoff bracket
[4] https://www.vlr.gg/753444/ — representative opening match detail; the same
    `/v2/match/details?match_id=` read-only source was checked for IDs 753445,
    753449, 753450, 753455 and 753459. Archived raw detail filenames are
    `match_details_753454_20260924T171005Z.json` and
    `match_details_753460_20260925T111520Z.json`.
[5] https://valorantesports.com/en-US/tournament/115576361459045501/overview — Riot official Champions Shanghai overview, "Playoffs" series format.
[6] https://valorantesports.com/en-US/news/champions-shanghai-pickems-powered-by-aws — Riot's September 11 Pick'Ems article, "Playoffs Pick'Ems" dates: October 4 after Draw Show and matchup confirmation.
