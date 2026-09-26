# International experience lab: protocol (frozen before scoring)

Frozen 2026-09-26, before any test-period number was computed.

## Question

The user's hypothesis, from Vitality beating Global Esports 2-1 at Champions 2026
(Elo 60.6% GE, market 45.5% GE): players with more **international**
experience (Masters / Champions / LOCK//IN) perform better than team Elo
predicts, especially at international events. Elo is team-level and cannot
see this.

## Feature (point-in-time)

- **International event:** a Tier-1 event whose name is `Valorant Champions
  <year>`, contains `Masters <City>` (Reykjavík, Berlin, Copenhagen, Tokyo,
  Madrid, Shanghai, Bangkok, Toronto, Santiago, London…), or contains `LOCK//IN`.
  The 2021 regional "Stage 1: Masters" events (name ends in `: Masters`) are
  **not** international.
- **Player experience:** the number of international **maps** a player (vlr
  player ID; handle when the ID is missing, as in `player_form`) had played in
  matches with a strictly smaller `match_id` (the chronological key).
- **Side experience:** mean over that match's lineup of `log1p(international
  maps)`. Lineups are the players in that match's own stats, the same
  assumption `player_form` makes (lineups are public before kickoff).
- **Gap:** `x = exp_a - exp_b`. Missing lineup on either side → `x = 0`
  (falls back to Elo exactly).

## Candidates (each reproduces production Elo at beta = 0)

`p' = sigmoid(logit(p_elo) + beta * x)`, with `p_elo` the production Elo
probability from `build_features`.

- **A (all):** beta applied to every Tier-1 match.
- **B (internationals only):** beta applied only when the match itself is at an
  international event; every other match keeps `p_elo`.

## Tuning and test

- **Tuning:** beta on a grid of 0 to 0.60 in steps of 0.02 (and the same
  negative values, so the sign is learned, not assumed), chosen by mean log
  loss on Tier-1 2023–24 (for B: 2023–24 internationals only).
- **Test:** 2025 and 2026 Tier-1 matches, scored once with the tuned beta and
  no retuning. Paired per-match log-loss t against production Elo, per year
  and pooled. For B the test is the 2025–26 international matches (small n,
  expected ~150–250).

## Decision rule

- **Shadow-worthy** (log as a shadow column, flag off, primary unchanged): pooled
  2025+26 paired t > +2.0 **and** both years improve on production.
- **Not proven:** improvement with t between 0 and +2.0 in pooled data. Record
  and keep the idea; re-test when 2027 internationals exist.
- **Rejected:** pooled t ≤ 0, or a tuned beta of exactly 0.
- No primary-forecast change comes out of this lab under any result; that
  needs the owner's approval and prospective evidence.

## Caveats written in advance

- 2025 and 2026 have been consulted by earlier experiments; passing is
  necessary, not sufficient.
- International experience correlates with team strength that Elo already
  captures, so a positive beta has to beat Elo on held-out data, not merely be
  positive.
- One match (GE vs VIT) motivated the idea; it is in the 2026 test set and
  must not be singled out as evidence.
