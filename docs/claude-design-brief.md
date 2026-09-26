# Claude Design brief: VCT Quant redesign

Paste everything below the line into Claude Design and attach the 4 screenshots
of the current UI (home, matches, match, rankings).

---

## What this is

**VCT Quant** is a small, private web app that forecasts Valorant Champions Tour
(VCT) esports matches. A statistical model (Elo ratings) gives each team a win
chance, and the app shows it next to the betting-market price (Polymarket).
It also keeps an honest, public record of how the model has done.

- **Audience:** about 10 friends who follow VCT closely. They know the teams,
  players and tournament formats, and they are not quants. They open it on
  their **phones**, usually from a Discord link, right before a match or
  during a tournament.
- **Tone:** a sharp sports-data desk, not a startup. Think of the forecast
  pages of a good sports-analytics site crossed with an esports broadcast's
  lower-third graphics. Confident numbers, honest uncertainty, no hype.
- **What it is not:** a betting product. There is no real money. The "Edge"
  page is paper trading only.

## The problem with the current UI (screenshots attached)

It looks AI-generated / "vibe-coded". Specifically:

- Every piece of content sits in a white rounded card with a soft shadow on a
  grey page. The card is the only way anything is grouped.
- The default blue accent is not chosen for anything.
- Tiny uppercase monospace "eyebrow" labels (`2026 SEASON`) above every heading.
- A row of big-number stat tiles on the home page that fill space rather than
  telling you anything.
- Generic sans type everywhere, with hierarchy made by boxes rather than type.
- No sense of place: nothing says "esports" or "Valorant tournament".

Keep the information. Replace the visual language.

## Design direction

- Treat it as a **Monitor + Compare** product: people glance at odds, compare
  the model with the market, and drill into one match. It is **not** a landing
  page, so no hero section and no feature grids.
- **Structure with type, alignment, rules and density, not cards.** Use
  hairline dividers, tabular rows and strong numeric typography. A card is
  allowed only where something is genuinely a separate object (a single match
  on the matches list, for example).
- **Numbers are the hero.** Win percentages need a deliberate numeric face
  (tabular figures, distinctive, readable at a glance). Team tags (PRX, 100T,
  G2) are the second hero: short, bold, broadcast-style.
- **Two series colours, used consistently everywhere:** one for the model,
  one for the market. Choose them deliberately; don't default to blue/orange.
  A third, restrained colour marks the actual result or winner.
- **Esports feel without Riot IP:** no Valorant logo, agent art or Riot's
  exact brand red. Draw on the language of tournament broadcasts (brackets,
  score bugs, map-by-map scores, group tables) instead.
- **Dark theme as the primary**, with a real light theme second. Both need to
  pass WCAG AA contrast.
- Motion is minimal: state changes only, respecting `prefers-reduced-motion`.

Explore **three directions** before committing:

1. **Broadcast:** dark, bold condensed type, score-bug components, feels like
   the in-game tournament overlay.
2. **Editorial data desk:** newspaper sports-section hierarchy, serif or
   grotesk headlines, dense tables, very little colour.
3. **Terminal odds board:** trading-screen density, strict grid, monospaced
   numerics, the model–market gap as the main visual.

## Pages and the data each one shows

Real sample data is below: use it, don't invent numbers.

1. **Home:** the next 3–5 matches with win chances, a one-line live record
   ("Model picked the winner in 4 of 6 graded Champions matches"), the current
   event and stage, links into each section.
2. **Matches:** upcoming matches grouped by day (times in the viewer's local
   time). Each row shows the two logos and tags, the model's win % for each
   side, the market % when there is one (often missing), the stage (e.g.
   "Group Stage: Opening (A)"), and best-of. There is a filter by event.
3. **Match page** (`/match/:id`):
   - Both teams large with logos and names.
   - Model %, market %, and the gap between them.
   - Chance of a 2-0 sweep vs 2-1, and the exact series-score distribution.
   - A line chart of how the model and market moved before the match.
   - Each team's last 5 results (W/L, opponent, date) and last 20 maps.
   - The head-to-head record.
   - After the match: the final score, map-by-map scores, and whether the
     model called it.
4. **Rankings:** the Elo table (rank, logo, team, tag, rating, matches this
   season) plus a head-to-head picker for any two teams that shows the
   neutral-stage win chance.
5. **Results:** finished matches: score, the model's last pre-match %, the
   market %, and an "upset" marker when the favourite lost. Filter by tier
   (Tier 1 / Game Changers).
6. **Champions 2026:** four groups (GSL format, 4 teams each), each team's
   chance of reaching playoffs, and results so far.
7. **Edge (paper trading):** matches where the model and market disagree most,
   and a small paper-trade ledger (entry odds, result, units won/lost).
8. **Track record:** a calibration chart (predicted % vs actual %), the model's
   log loss vs a coin flip and vs the market, and a table of every graded call.
9. **Team page / Player page:** team results and maps; player map stats.

## Real sample data

Upcoming (Valorant Champions 2026, all Bo3):

| When (UTC) | Stage | Team A | Team B | Model A | Market A |
|---|---|---|---|---:|---:|
| Sep 27 09:00 | Group Stage: Opening (A) | 100 Thieves (100T) | T1 | 53.5% | none |
| Sep 27 12:00 | Group Stage: Opening (A) | JD Gaming (JDG) | FUT Esports (FUT) | 28.0% | none |
| Sep 29 09:00 | Group Stage: Winner's (C) | G2 Esports (G2) | Paper Rex (PRX) | 48.3% | none |
| Sep 29 12:00 | Group Stage: Winner's (D) | Karmine Corp (KC) | NRG | 38.4% | none |
| Sep 30 12:00 | Group Stage: Winner's (B) | Team Vitality (VIT) | LOUD | 41.4% | none |

Finished:

- **Global Esports 1–2 Team Vitality.** Model had GE at 60.6%, market 45.5%:
  an upset that the model got wrong and the market got right.
- **LOUD 2–0 EDward Gaming.** Model 69.1% LOUD, market 70.5%.
- **Karmine Corp 2–0 Xi Lai Gaming.** Model 58% KC, market 80.5%.

Record: Tier 1, the favourite won 4 of 6 graded matches. Model log loss is 0.596
against 0.693 for a coin flip. Against properly traded market prices over 7
matches, model 0.607 vs market 0.593 (a statistical tie).

Rankings top 5: LEVIATÁN (LEV) 1867 · 100 Thieves (100T) 1854 · Mega Minors
1850 · Paper Rex (PRX) 1834 · NRG 1833.

## Constraints

- **Phone first:** designed at 390 px wide, then scaled up to a 1200 px desktop
  layout. Hit targets are at least 44 px. Nothing scrolls sideways.
- **Logos:** team logos are square PNGs in wildly different styles (some are
  wordmarks, some are colourful, some are nearly black). Design a logo slot
  that makes all of them look intentional in both themes: consistent size,
  a neutral backing if needed, and an initials fallback when a logo is missing.
- **Team names:** some are long ("Nongshim RedForce", "EDward Gaming"). The
  tag replaces the name when space is tight. Some teams have no tag (T1,
  NRG, MIBR), where the name is already short.
- **Missing data is normal:** there is often no market price, and new teams have
  few rated matches. Design those empty and low-confidence states on purpose.
- **Honesty is a feature:** percentages come with plain-language context, e.g.
  "from ratings only: no map veto or roster news". Keep that tone.
- **Implementation:** a Vite + React + TypeScript app with react-router and
  one plain CSS stylesheet using CSS custom properties. There is no Tailwind
  and no component library. Charts are hand-written SVG. Web fonts are fine
  (self-hostable, at most 2 families).

## Deliverables

1. The three directions above as one comparison board: Match page + Matches
   list at 390 px for each.
2. After I pick one, the full design system: colour tokens (dark + light), type
   scale, spacing, the logo slot, the team-name/tag component, a win-probability
   bar, model-vs-market comparison, the score bug, table rows, the chart style,
   and empty/loading/error states.
3. High-fidelity screens for every page above at 390 px, plus Matches and the
   Match page at 1200 px.
4. The tokens as CSS custom properties, ready to paste.

## Do not

- Use white rounded cards with shadows as the default container.
- Put a gradient or glassmorphism anywhere.
- Add tiny uppercase monospace eyebrow labels above headings.
- Put icons above headings or a colored accent strip on the left of cards.
- Use Inter or a system font by default.
- Add big "monument" stat tiles that don't help anyone decide something.
- Invent metrics, testimonials, features or copy that isn't in this brief.
