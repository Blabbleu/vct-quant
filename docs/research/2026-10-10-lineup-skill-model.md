# Lineup skill model: pre-registration (2026-10-10)

## Hypothesis and protocol (written before held-out scoring)

A team represented by the five players who played will predict series outcomes better than the production team Elo when rosters change. Each player has an independent Gaussian skill posterior. A map's team performance is the sum of five skills plus independent Gaussian performance noise; the model uses the normal win probability and TrueSkill-style assumed-density filtering after the result. Player variance grows by `tau² × idle calendar days` before a game. Predictions use only posteriors available before that match. Matches without five identifiable players on each side use the production Elo probability and do not update player posteriors. If a side has more than five distinct participants across maps, choose the five with the most map appearances (stable player-ID tie break). The match-map `team_number` mapping to team A/B must be checked against observed map wins before scoring.

Use `scripts/model_lab.py::load()` and its chronological match sequence. Replay all earlier Tier-1 matches to form priors, updating only after each prediction. Production Elo is `model_lab.run(Config())`, checked against `compute_elo` as in that script. Score only completed Tier-1 matches with binary outcomes. Tune the pure lineup model on **2023–2024 Tier-1 mean log loss only**, over exactly 54 configurations: `beta ∈ {4, 8, 12}`, `sigma0 ∈ {4, 8, 16}`, `tau ∈ {0, 0.25, 0.75}` (skill units per square-root day), and update mode `{once per series, once per map}`. Prior mean is zero for every new player. Break equal validation losses by grid order. Freeze this one configuration before viewing 2025 or 2026 scores; the 50/50 logit blend with production Elo uses the same frozen configuration and has no extra tuning. Per-map mode applies the observed counts in a fixed alternating order because the loader supplies map totals rather than map order.

Report 2025 and 2026 separately on identical Tier-1 matches, including the Elo fallback matches. Primary metric: mean series log loss. Secondary metrics: Brier score, accuracy at 0.5, 10-bin reliability and expected calibration error (ECE). Paired t uses per-match `Elo log loss − candidate log loss`, so positive favors the candidate. **WIN** only if the paired t is greater than +2 in **both** 2025 and 2026 and candidate ECE is no worse than Elo ECE in both years. **Not proven** if paired t is positive in both years but the WIN bar fails. **Rejected** otherwise. Apply the rule separately to the pure model and blend. Existing model research has consulted these years, so this is a historical test rather than a fresh prospective holdout.

## Results

The 54-config grid selected **beta=12, sigma0=4, tau=0.25, per-map updates**; validation (2023–24 combined) log loss was **0.6645**. The loader's current `match_sequence` already includes `completed_at`, so the CLI removes that duplicate column before calling `model_lab.load()`. A 1,000-row map-score sample with non-null team IDs matched `match_team.team_number` with zero mismatches. For series with substitutions, the five players with the most map appearances were selected. The sole 2026 match without complete lineups used Elo.

### Coverage and scores

All rows are completed Tier-1 series with binary outcomes. The paired t compares each candidate with production Elo on exactly the same matches; positive favors the candidate. Accuracy uses a 0.5 threshold. ECE is 10-bin expected calibration error.

| Year | Full lineups / scored | Model | n | Log loss | Brier | Accuracy | Paired t vs Elo | ECE |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 | 333 / 333 | Elo | 333 | 0.6069 | 0.2090 | 0.658 | 0.00 | 0.0440 |
| 2023 | 333 / 333 | Pure lineup | 333 | 0.6250 | 0.2170 | 0.655 | -1.10 | 0.0298 |
| 2023 | 333 / 333 | 50/50 blend | 333 | 0.6050 | 0.2086 | 0.697 | +0.21 | 0.0795 |
| 2024 | 436 / 436 | Elo | 436 | 0.6522 | 0.2299 | 0.615 | 0.00 | 0.0579 |
| 2024 | 436 / 436 | Pure lineup | 436 | 0.6947 | 0.2457 | 0.587 | -2.74 | 0.1018 |
| 2024 | 436 / 436 | 50/50 blend | 436 | 0.6626 | 0.2342 | 0.594 | -1.38 | 0.0761 |
| 2025 | 504 / 504 | Elo | 504 | 0.6414 | 0.2255 | 0.637 | 0.00 | 0.0423 |
| 2025 | 504 / 504 | Pure lineup | 504 | 0.6571 | 0.2296 | 0.623 | -1.19 | 0.0746 |
| 2025 | 504 / 504 | 50/50 blend | 504 | 0.6403 | 0.2245 | 0.627 | +0.15 | 0.0441 |
| 2026 | 613 / 614 | Elo | 614 | 0.6620 | 0.2343 | 0.611 | 0.00 | 0.0628 |
| 2026 | 613 / 614 | Pure lineup | 614 | 0.6984 | 0.2475 | 0.601 | -2.68 | 0.1022 |
| 2026 | 613 / 614 | 50/50 blend | 614 | 0.6685 | 0.2371 | 0.607 | -0.96 | 0.0700 |

### Held-out reliability

Each cell is `n / mean predicted P(A) / observed A win rate`; `—` means an empty bin. The ECE values above summarize the absolute gaps weighted by bin count.

| Year | P(A) bin | Elo | Pure lineup | 50/50 blend |
| --- | --- | --- | --- | --- |
| 2025 | 0.0–0.1 | 2 / .097 / .000 | 14 / .051 / .071 | 9 / .067 / .111 |
| 2025 | 0.1–0.2 | 21 / .156 / .190 | 25 / .154 / .320 | 23 / .161 / .174 |
| 2025 | 0.2–0.3 | 40 / .248 / .300 | 45 / .247 / .267 | 42 / .252 / .357 |
| 2025 | 0.3–0.4 | 61 / .350 / .475 | 59 / .350 / .458 | 56 / .355 / .446 |
| 2025 | 0.4–0.5 | 93 / .451 / .398 | 83 / .455 / .506 | 78 / .451 / .449 |
| 2025 | 0.5–0.6 | 101 / .550 / .564 | 76 / .550 / .579 | 117 / .549 / .521 |
| 2025 | 0.6–0.7 | 93 / .648 / .645 | 73 / .646 / .575 | 66 / .656 / .652 |
| 2025 | 0.7–0.8 | 60 / .748 / .683 | 56 / .748 / .643 | 59 / .745 / .627 |
| 2025 | 0.8–0.9 | 32 / .846 / .844 | 48 / .854 / .729 | 46 / .851 / .870 |
| 2025 | 0.9–1.0 | 1 / .902 / 1.000 | 25 / .938 / .840 | 8 / .931 / .875 |
| 2026 | 0.0–0.1 | 1 / .099 / .000 | 17 / .065 / .176 | 6 / .075 / .167 |
| 2026 | 0.1–0.2 | 18 / .152 / .222 | 41 / .159 / .390 | 26 / .159 / .269 |
| 2026 | 0.2–0.3 | 48 / .254 / .354 | 56 / .258 / .250 | 56 / .249 / .304 |
| 2026 | 0.3–0.4 | 102 / .356 / .265 | 91 / .351 / .396 | 96 / .353 / .344 |
| 2026 | 0.4–0.5 | 104 / .450 / .442 | 78 / .446 / .423 | 97 / .456 / .423 |
| 2026 | 0.5–0.6 | 121 / .551 / .545 | 82 / .553 / .463 | 100 / .555 / .530 |
| 2026 | 0.6–0.7 | 143 / .644 / .545 | 82 / .653 / .561 | 109 / .654 / .495 |
| 2026 | 0.7–0.8 | 54 / .746 / .648 | 92 / .752 / .576 | 83 / .739 / .627 |
| 2026 | 0.8–0.9 | 23 / .832 / .739 | 54 / .845 / .611 | 38 / .846 / .763 |
| 2026 | 0.9–1.0 | — | 21 / .925 / .857 | 3 / .930 / 1.000 |

### Verdict

**Rejected for both candidates.** The pure lineup model has negative paired t and worse ECE in both held-out years. The blend has a negligible 2025 log-loss gain (t=+0.15), then loses in 2026 (t=-0.96); its ECE is worse in both years. Neither meets even the pre-registered “not proven” condition. This result does not support replacing production Elo. The per-map update uses counts in a fixed alternating order because actual map order is absent from `model_lab.load()`; that approximation may affect the final posterior, but it was specified before scoring.
