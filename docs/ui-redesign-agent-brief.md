# Terminal Arena redesign: shared brief for implementation agents

You are implementing a UI redesign of the VCT Quant web app (Valorant esports
match forecasts). Read this whole file first.

## Where to work (hard rules)

- Worktree: `/home/blabbleu/projects/valorant/vct-quant-ui`, branch
  `ui/terminal-arena`. Work ONLY here. Never touch
  `/home/blabbleu/projects/valorant/vct-quant` (live site) or
  `/home/blabbleu/projects/valorant/vct-quant-auto` (another agent's worktree),
  except that `data/` inside the UI worktree is symlinked there: treat all of
  `data/` as READ-ONLY.
- Run EVERY project command through the wrapper `vctui <cmd>` (runs as user
  blabbleu inside the worktree with node v24 + the Python venv on PATH), e.g.
  `vctui sh -c 'cd web && npm run build'`, `vctui npm run check`,
  `vctui git add -A web && vctui git commit -m "..."`, `vctui pytest -q`.
- Commit on `ui/terminal-arena` in small logical commits. Never push, never
  merge, never rebase, never force, never `git reset --hard`.
- `npm install` only inside `web/` (commit package.json + lockfile). Keep
  `server.js` dependency-free and do not change its API unless your task says so.
- Dev server for visual checks: start it with the terminal tool
  `background=true`:
  `vctui env PORT=<your port> HOST=127.0.0.1 timeout 1500 node server.js`
  (use the port given in your task). Stop it by killing THAT process session
  only. NEVER run `pkill -f "node server.js"` or anything matching broadly: it
  kills the live site. After stopping, confirm
  `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/health`
  is still 200.
- Rebuild (`npm run build`) before viewing: server.js serves `web/dist`.

## The design

The full spec is `docs/design-terminal-arena.pdf` in the worktree. Read it with
the read_file tool (it extracts the text). It is the source of truth for tokens,
type, shapes, components, states, copy and do-nots. Summary of the key points:

- Dense dark "odds board" with tactical-shooter menu language: cut-corner panels
  (clip-path, no border radius anywhere), slanted chips/tags/pips (skewX -14deg
  with counter-skewed text), segmented pip bars, corner brackets.
- Colour roles: model = chartreuse `--model`, market = pink `--market`,
  result/winner = white `--result`. Neutrals are green-greys. No gradients, no
  shadows, no glassmorphism. Model and market also differ by SHAPE (model =
  slanted square/bar, market = triangle notch/diamond).
- Fonts: Chakra Petch (500/600/700) for words and tags; JetBrains Mono
  (400/500/700/800) for every number, time and meta line, always tabular-nums.
  Self-host via npm `@fontsource/chakra-petch` and `@fontsource/jetbrains-mono`
  (import only the listed weights, latin subset). No Inter/Roboto/system font.
- Dark theme default and a real light theme (`:root[data-theme="light"]`); follow
  `prefers-color-scheme` until the viewer picks, then persist the choice in
  localStorage. Put a small theme toggle in the nav/menu.
- Phone first at 390 px (gutter 12 px, hit targets >= 44 px, nothing scrolls
  sideways), scaling to a 1200 px desktop layout.
- Motion: 120 ms state changes only; honour `prefers-reduced-motion`.
- Honesty copy is FIXED text (see spec "Copy and do-nots").
- Do-nots: rounded white cards with shadows, gradients, eyebrow labels above
  headings, icons above headings, coloured left strips on cards, stat tiles that
  don't help a decision, Riot IP, invented numbers.

## Answers to the spec's open questions (use these)

- **Record line:** use real numbers from `/api/results` `by_tier`. Tier 1 today:
  6 verified, favourite won 4 → "Model picked the winner in 4 of 6 graded Tier 1
  matches". Never hard-code; compute from the payload.
- **Data feeds already in the payload:** `/api/match/:id` (see
  `web/src/lib/types.ts` `Movement`) has `points` (forecast history with
  `observed_at`, `elo`, `market`, `spread`: this IS the price history for the
  chart), `recent_form` (last 5 with opponent + date), map history, `head_to_head`,
  `result` (score + map scores when played). Use them. Anything genuinely missing
  gets the spec's placeholder state; never invent.
- **Dark logos:** decide per logo automatically. Logos are same-origin PNGs at
  `/logos/<id>.png`; compute mean luminance of opaque pixels client-side with a
  canvas once per logo (cache in a module-level Map) and use `--logo-plate-dark`
  when it is below ~0.18. EDG and Paper Rex should come out dark; verify.
- **Low data threshold:** fewer than 10 rated matches this season.
- **Big gap threshold:** 10 points (put both thresholds in one constants file).
- Keep the existing routes (`/champions/2766`, `/track-record`, `/status`,
  `/about`) rather than the spec's shorter names.

## Existing code (read before changing)

- `web/src/main.tsx` routes; `web/src/components/Layout.tsx` shell + nav;
  `web/src/styles.css` the single global stylesheet (being replaced);
  `web/src/lib/{api.ts,types.ts,format.ts}` data hooks/types/formatters;
  components: TeamLogo, TeamName, FixtureCard, LineChart, Calibration,
  HeadToHead, ResultPanel, ScoreForecast, PaperLedger, CheckpointPanel,
  LiveByPool, ui.tsx; one file per page in `web/src/pages/`.
- Reuse the data hooks and types. Keep every page's existing information unless
  the spec explicitly drops it (e.g. the home stat tiles go).
- CSS organisation: `web/src/styles.css` holds tokens, base, shape helpers and
  shared components. Page-specific rules go in `web/src/pages/<Page>.css`
  imported by that page, so parallel agents don't collide.

## Definition of done for any task

1. `vctui sh -c 'cd web && npm run build'` passes (strict tsc).
2. `vctui npm run check` passes (server route check), and `vctui pytest -q`
   still passes.
3. You opened every page you touched in the browser at 390x844 (mobile
   emulation) AND 1200x800, in dark AND light theme, took screenshots and
   looked at them: no horizontal overflow
   (`document.documentElement.scrollWidth` equals the viewport width), no
   console errors, fonts loaded, spec look achieved.
4. Run the slop check: no rounded corners, shadows, gradients, eyebrows,
   Inter/system font, or invented numbers anywhere you touched.
5. Committed on `ui/terminal-arena`. Your final answer lists: commits (sha +
   subject), files touched, what you verified (with the scrollWidth numbers),
   screenshot paths for the key views, and anything you could not do.
