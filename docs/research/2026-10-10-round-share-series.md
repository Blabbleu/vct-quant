# Round-share generative series model — pre-registration

This pre-registration was written before scoring, but is committed together with the results in one worker commit.

## Hypothesis and fixed protocol

Round outcomes contain a useful pre-match team-strength signal beyond the official K48 margin Elo. This is a generative round-to-map-to-series model; it does not train Elo on round share or use played map names, vetoes, or any post-series feature.

Replay `match_sequence()` in ascending `match_id`, including Tier 1 and Tier 2 history. Use only paired, nonnegative `match_map_team_score.total_rounds` rows whose `match_map` match ID and `team_number` 1/2 align with the two `match_team` identities returned by `match_sequence()`. Identity is team ID as text, or `name:` plus lower trimmed team name when team ID is null. Keep each team's last N *maps* in a deque and update histories only after predicting the entire match. Invalid maps contribute no history. Count invalid/alignment-rejected maps and coverage.

For each team, sum wins W and losses L across its last N scored maps. With prior strength alpha centered at 0.5, rate = (W + alpha/2)/(W + L + alpha). Set `p_round = sigmoid(logit(rate_A) - logit(rate_B))`. The regulation map win chance is the probability of reaching 13 wins while the opponent has at most 11, plus the probability of 12-12 times the overtime chance `p_round² / (p_round² + (1-p_round)²)`. Overtime is repeated two-round blocks until one team wins both rounds. For best-of 1, 3, or 5, sum the iid-map binomial series win probabilities. Temper the resulting series logit by gamma: `sigmoid(gamma * logit(p_series))`.

The fixed 18-cell grid is N in {10, 30, 100}, alpha in {100, 500}, gamma in {0.25, 0.5, 1.0}, in that nested order. Select minimum mean series log loss on 2023-24 combined; ties use grid order. Freeze that cell before viewing either test year. Unsupported or uncertain best-of, or either team lacking any prior scored rounds, uses the official pre-match Elo probability. The official baseline is the `compute_elo` replay of `match_sequence()` using `margin_signal` and `elo_k`, as in `scripts/benchmark_exact_scores.py` lines 17-35.

Score the identical completed binary Tier-1 matches with `completed_at` year 2023-26, including fallback rows. Report per-year n, map-round coverage, log loss (primary), Brier, accuracy, paired per-match t of Elo loss minus candidate loss, and ten-bin calibration and ECE for both models. Train/tune on 2023-24 only; report 2025 and 2026 separately. **WIN** iff paired t > +2 and candidate ECE <= Elo ECE in **each** test year. Positive t in both years without this bar is **TIE / not proven**; otherwise **LOSS / reject**. The historical years are retrospectively consulted, not clean prospective validation.

## Results

The fixed grid selected **(N=100, alpha=500, gamma=0.5)** on 2023-24 combined mean log loss **0.671052**. In the database snapshot, 28,099 map records existed: 26,153 aligned valid pairs, 0 rejected, 0 alignment rejected, and 1,946 skipped because their matches were outside the official Tier-1/Tier-2 sequence. Every map of the scored matches had a valid score pair. `covered` counts matches that could use the round model; other rows use Elo.

| Year | n | covered | valid / all maps | Model log loss | Elo log loss | Model Brier | Elo Brier | Model accuracy | Elo accuracy | Paired t | Model ECE | Elo ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 tune | 333 | 319 | 832 / 832 | 0.669920 | 0.606869 | 0.238061 | 0.208962 | 0.573574 | 0.657658 | -4.133040 | 0.047069 | 0.043993 |
| 2024 tune | 436 | 429 | 1106 / 1106 | 0.671916 | 0.652227 | 0.239343 | 0.229934 | 0.587156 | 0.614679 | -1.436111 | 0.031415 | 0.057865 |
| 2025 test | 504 | 494 | 1278 / 1278 | 0.661535 | 0.641353 | 0.234634 | 0.225489 | 0.605159 | 0.636905 | -1.802077 | 0.038534 | 0.042336 |
| 2026 test | 614 | 602 | 1564 / 1564 | 0.672109 | 0.662032 | 0.239529 | 0.234301 | 0.578176 | 0.610749 | -1.039051 | 0.036322 | 0.062841 |

The script prints both models' ten-bin count, observed rate, and mean probability for every year. The held-out verdict is **LOSS / reject**: Elo has lower log loss in both 2025 and 2026, and both paired t values are negative. This is a retrospective database replay, not prospective validation.
