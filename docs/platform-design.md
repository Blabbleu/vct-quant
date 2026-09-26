# VCT Quant platform design (2026-09-25)

Goal: grow the one-page desk (`frontend/index.html`, `server.js`,
`dashboard.py`) into an all-in-one Valorant prediction platform: every
forecast, the evidence behind it, and an honest record of how it has done.

## Match Center API and mobile UI slice (dev branch)

`GET /api/match/:id` reads the append-only prediction log through
`python -m vct_quant.match_center ID`, without updating data or replaying Elo.
It returns a `points` array of UTC `observed_at`, `elo`, `market`, and `spread`
for **pre-start sampled refreshes**, with the latest pairing's A/B orientation.
Quotes from a different market contract are null rather than joined into one
line. No log/pre-start observations gives 404; bad IDs also give 404.

`GET /match/:id` now serves a mobile Match Center view from the existing
single-file frontend: fixture-list links, latest Elo and comparable midpoint,
a 0–100% movement chart with market gaps, and an exact-values list. Its 390px
viewport has no horizontal overflow in the browser smoke check. Missing IDs
show an explicit empty state; the baked offline report keeps plain fixture
names rather than links to a server it cannot reach. This is not the complete
Match Center (form, result, map pools, veto what-if, and player history remain).
The backend's Python default targets the repo's `.venv`, while `PYTHON` remains
configurable. This slice does not yet migrate the frontend to Vite; that
separate build step was approved for a later phase. Merging `server.js` changes
and restarting the running desk are separate user approvals.

## Exact-ID player profile (dev branch)

`GET /api/player/:id` runs `python -m vct_quant.player_profile ID` against
read-only DuckDB. A positive safe numeric ID must exist in `player`; unknown
IDs are 404. It aggregates recorded Tier-1 scored maps with exact player and
team IDs, completed before the current UTC date. This conservative cutoff
excludes the current day because historical completion timestamps often carry
only a date at midnight. Game Changers, undated maps, incomplete round scores,
TBD opponents and null team IDs are excluded. A player with no eligible maps
has an explicit empty profile rather than a 404. Agent labels are grouped
case-insensitively, and team counts group by ID across name changes; all-map
counts and a latest-20 map list are descriptive, **not** player forecasts.
The mobile `/player/:id` page links exact team IDs, shows agent/team histories
and per-map K/D/A, ACS and rating. It does not claim current roster membership.
No player discovery links exist yet from the team or Match Center pages; a
read-only recent-lineup API is a separate next slice.

## Where the desk is today

One scrolling page, one `/api/snapshot` payload:
headline backtest numbers, upcoming fixtures (Elo vs Polymarket, sweep %),
calibration plot, Elo leaders, a two-team head-to-head picker, the graded live
ledger with shadow models, and the experiment ledger. It is good at "what does
the model say and can I trust it"; it cannot answer "why", "what if", or
"what does this mean for the tournament".

Ops notes: the desk runs as a `node server.js` in a terminal since Sep 24 (no
service, dies on reboot); `server.js` defaults to `venv/bin/python`, the repo
venv is `.venv`.

## Data we actually have (live DB, 2026-09-25)

| have | rows | enables |
|---|---:|---|
| match / match_team | 39,493 | results, form, H2H, Elo history |
| match_map + team scores (atk/def/OT rounds) | 27,471 | map pools, map win %, side splits |
| match_map_player_stat (agent, rating, ACS, KAST, ADR, HS%, FK/FD) | 273,541 | player form, agent pools, lineups-in-practice |
| player / team / event | 14,775 / – / 2,215 | entity pages |
| prediction_log (every refresh, with market mid/spread/volume) | 105+ | probability movement, CLV, track record |

Empty today: rounds, economy, kill matrix, advanced stats, VODs, news, roster
snapshots, transactions, standings, full pre-match vetoes. Features below avoid
them or list the ingest they would need.

## Feature set

### 1. Match Center: one page per fixture (highest value)
- Win probability, series score distribution (2-0/2-1/1-2/0-2), expected
  maps; Elo vs market vs every shadow model side by side.
- **Probability movement** chart: model and market over time, from the
  prediction log's repeated snapshots (market drift = closing-line data).
- Form: last 10 results each with Elo change; head-to-head history.
- **Map pool matrix**: both teams' win % and sample size per active map, with
  attack/defense round share; flag the likely picks and bans.
- **Veto what-if**: pick maps and get per-map and series odds (the CLI already
  supports `vct predict --maps`).
- Probable lineups and player form (rating/ACS/KAST last N maps, agent pool).
- After the match: result, grade (log loss vs market), post-mortem line.

### 2. Tournament simulator (Champions 2026 is live now)
- Monte Carlo of the actual format (GSL groups, then double-elim playoffs):
  each team's odds to exit groups, reach top 4, win the title, updated after
  every result. Compare with the outright market if one exists.
- Bracket view with the most likely path; "what if X beats Y" toggles.
- Needs a per-event bracket spec (hand-written JSON; `event_standing_row` is
  empty).

### 3. Teams and players
- Team page: Elo trajectory, current core five (from recent map stats), map
  pool, results and schedule, travel/regional record at internationals.
- Player page: form trend, agent pool, per-map stats, teams history.
- Leaderboards: Elo by region/tier (Tier 1, Challengers, Game Changers),
  weekly movers, player stat leaders with minimum-map filters.

### 4. Track record ("model lab")
- Running log loss/Brier over time for Elo, market and each shadow model;
  calibration by bucket; every graded forecast searchable.
- Experiment ledger with links to each doc; promotion rule stated on the page.
- This is the credibility page: nothing hidden, rejections included.

### 5. Edge board (optional; betting-adjacent)
- Model vs market gaps ranked by size, filtered by spread and volume.
- **Paper-trading ledger**: flat-stake and fractional-Kelly P&L if every gap
  over a threshold had been taken at the logged price, plus CLV (did the
  market move toward the model after we logged?). Shows whether edges are
  real without risking money.

### 6. Alerts (Discord via Hermes)
- New fixture forecast; model-market gap over threshold with a liquid market;
  big line move; result graded; weekly track-record digest.

### 7. 2027 hub
- Open-qualifier tracker by territory, newcomer/roster carry-over notes, Tier
  2 teams with enough history to rate. Fills in as Riot publishes titles.

### 8. Ops panel
- Data freshness per source, last refresh, API health, autodev activity
  (latest journal entries, pending approvals).

## Architecture changes

- **Routing and per-entity APIs.** Keep GET-only and the mtime cache, but
  replace the single payload with per-view endpoints: `/api/match/:id`,
  `/api/team/:id`, `/api/player/:id`, `/api/event/:id/sim`,
  `/api/track-record`. Each runs a small Python entry point; heavy Elo replay
  stays cached in-process.
- **Results list (built 2026-09-26, auto/dev).** GET `/api/results`
  (`src/vct_quant/results_list.py`) lists every logged fixture whose canonical
  match is completed: the last forecast logged strictly before kickoff, the
  liquid (spread ≤ 0.10, volume ≥ 1,000) market on that same row, and the
  result verified by `match_result.load_result`. Unverified results carry the
  reason and no score or loss. Per-tier tallies (favourite won, mean log loss)
  are descriptive; Game Changers is listed as its own tier. Mobile page
  `/results`. Never an input to ratings, shadows or the checkpoint rule.
- **Frontend build.** The no-build single file is at 600 lines. Past two or
  three pages, move to Vite + React + TypeScript with a charts lib (uPlot or
  Recharts). `server.js` serves `dist/`. Keeps the zero-dependency backend.
  The baked offline report can stay for the published artifact.
- **Run the desk as a systemd service** (restart on failure, starts on boot).
- **Mobile first**: the user reads on a phone; every page must work at 390px.
- Exposure: currently 127.0.0.1 only. Anything public needs auth or a
  read-only static export; decide before deploying.

## Phasing

1. **Now (Champions window):** Match Center, tournament simulator,
   probability movement, systemd service, router + per-entity API skeleton.
2. **Next:** team and player pages, map pool matrix, veto what-if,
   track-record page.
3. **Later:** edge board and paper trading, Discord alerts, 2027 hub, ops
   panel, public deployment decision.

## Decisions (user, 2026-09-25)

- **Audience: friends.** A small invited group, not public. Access is the
  user's existing Tailscale setup; the user handles exposure, so it is out of
  scope for autodev. Keep `HOST`/`PORT` configurable (default 127.0.0.1),
  no in-app login needed for now, and never open ports or install tunnels.
- **Edge board and paper trading: yes.** Paper only; no real-money actions.
- **Frontend build step: yes.** Vite + React + TypeScript under `frontend/`,
  npm dependencies installed in the dev worktree only (`frontend/node_modules`,
  lockfile committed). `server.js` stays dependency-free and serves the built
  `frontend/dist/`.

Friends-audience consequences: mobile-first, readable without project
context (plain-language labels, a short "how to read this" per page),
no admin/ops details or autodev approvals visible to friends (ops panel
is owner-only), and read-only everything.
