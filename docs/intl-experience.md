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

## Results (scored once, 2026-09-26, `scripts/intl_experience_lab.py`)

449 international Tier-1/2 matches in the corpus. Lineup gap available for
most 2023–26 Tier-1 matches (299/333, 433/436, 493/504, 360/592).

| Candidate | Tuned beta (2023–24) | Test | n | Elo | Candidate | paired t |
|---|---:|---|---:|---:|---:|---:|
| A: all Tier-1 | **0.00** | 2025+26 | 1,096 | 0.6587 | 0.6587 | n/a (identical) |
| B: internationals only | −0.02 | 2025 | 76 | 0.6924 | 0.6925 | −0.09 |
| | | 2026 | 52 | 0.6658 | 0.6648 | +0.46 |
| | | 2025+26 | 128 | 0.6816 | 0.6813 | +0.27 |

**Verdict: rejected.** A tunes to beta = 0 (the rule's "rejected" case). B's
tuned beta is essentially zero and slightly *negative* (more experience →
marginally lower win probability), with pooled t = +0.27: noise.

Why (descriptive, 2023–26 internationals with a lineup gap, n = 291): the
experience gap correlates **0.63** with the Elo difference but **−0.02** with
Elo's residual. Experienced lineups do win more, but Elo already prices that
in: in the top quartile of gaps (n = 73) the more experienced side won 67.1%,
against 68.7% expected from Elo alone.

So the GE–Vitality upset is not evidence of a systematic experience effect
the model misses. Re-test when 2027 internationals add data; a finer version
(experience in *playoff* or *elimination* maps, or recency-weighted) would need
its own frozen protocol.
