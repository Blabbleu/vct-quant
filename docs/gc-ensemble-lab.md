# Game Changers two-speed / fixed-shrink lab

Protocol frozen before computing any candidate loss (2026-09-26). This is exploratory: 2025–26 GC results have already been consulted repeatedly for K and side advantage, so the test below is **not a clean holdout**. Never use the live prediction log for selection.

## Question and data

Does a slower/fast GC rating blend or a fixed shrink of K=192 improve the already-proposed GC K=192 margin Elo? Both families use `match_sequence(tiers=(3,))`, the production margin signal and continuous match-ID ordered replay. Training/tuning is on decisive matches dated through 2024; one subsequent evaluation is on decisive 2025–26 matches. Replay must include all rows in sequence, including draws, and neither test labels nor post-match scores can be used to fit parameters before their own prediction.

## Frozen selection

* Reference: unmodified margin Elo K=192, no side advantage (A73 candidate). This is **not** a comparison to current production K=48 or the A74 side-advantage shadow. Both A73 and A74 await approval.
* Blend: compute pre-match probabilities from independent K=96 and K=256 replays. `sigmoid(w logit(p96) + (1-w) logit(p256))`, w in {0.25, 0.50, 0.75}. Endpoint components are not recalibrated.
* Shrink: `sigmoid(a logit(p192))`, a in {0.70, 0.80, 0.90, 1.10, 1.20, 1.30}. Fixed a throughout, fitted on tuning years only (not rolling refits). No side-order bonus.
* Choose the single lowest mean tuning log loss across those nine candidates and the unchanged K=192 reference; exact ties choose the reference, then the smallest distance from the reference (`|a-1|` for shrink or `|w-0.5|` for blend), then lexical name. No grid extension or second-stage tuning. If reference wins, do not score 2025–26.
* If a candidate wins tuning, score it **once** on 2025–26 against the K=192 reference on identical rows. Report n, mean log loss and Brier, paired per-match t (positive means candidate better), and per-year loss/t. A proposed **shadow only**, never primary, requires overall paired t >= 2 and lower mean loss in both 2025 and 2026. A failure is rejected, not retuned. The prospective live log is the only remaining clean test, subject to owner approval before logging a new shadow.

Keep GC separate from Tier 1; no primary flag, ranking, data/raw, or live-DB change in this lab.
