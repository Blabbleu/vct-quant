# Frozen three-model logit stack

## Pre-registration (written before scoring)

Hypothesis: complementary pre-match evidence from production Elo, round-share series strength, and lineup skill improves Tier-1 series forecasts. Inputs are aligned by match ID with identical binary outcomes. Elo is the production `compute_elo` replay using `match_sequence`, `margin_signal`, and `elo_k`. Round-share is `round_share_series.predict_sequence` at frozen `(N=100, alpha=500, gamma=1.0)`. Lineup skill is `lineup_skill.replay` at frozen `Config(beta=12, sigma0=4, tau=0.25, per_map=True)` using `lineup_skill.load_data`. Component fallback probabilities stay equal to Elo.

The forecast is `sigmoid(w_elo logit(p_elo) + w_rs logit(p_rs) + w_ls logit(p_ls))`, with **no intercept** because team-side order is arbitrary. Fit weights once by minimizing mean binary log loss plus `0.001 * ||w - [1,0,0]||² / 2` on completed binary Tier-1 matches from 2023–24. Freeze those weights for separate 2025 and 2026-to-date tests. Primary metric is paired per-match log loss against production Elo; also report Brier score, accuracy, 10-bin reliability, ECE, and sample size. Secondary, report-only analyses are an expanding refit (through 2024 for 2025; through 2025 for 2026) and two-model Elo+round-share and Elo+lineup stacks fitted on 2023–24. No test-year tuning.

**Verdict rule:** WIN iff the primary stack has paired `t > +2` and ECE no worse than Elo in **each** of 2025 and 2026. If both paired t values are positive otherwise, NOT PROVEN. Else REJECTED. The 2025 and 2026 results were consulted by earlier experiments, so this is retrospective, not clean prospective validation. This pre-registration and its results land in one worker commit.

## Results

Snapshot run: 2023–24 fit yielded `w = [0.81959, -0.08543, 0.12807]` for `[Elo, round-share, lineup]`. The negative round-share weight is a fitted value, not a post-hoc adjustment. Paired t uses Elo per-match loss minus stack per-match loss. The 2023 and 2024 rows are **in-sample**.

The implementation preserves pure Elo if every component logit is identical on the fit set; that degenerate case has no independent component information. It did not occur in this run.

| Year | Sample | n | Loss | Elo loss | Brier | Elo Brier | Accuracy | Elo accuracy | Paired t | ECE | Elo ECE | Weights |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2023 | Primary, in-sample | 333 | 0.60522 | 0.60687 | 0.20846 | 0.20896 | 0.66967 | 0.65766 | +0.44 | 0.05009 | 0.04399 | [0.81959, -0.08543, 0.12807] |
| 2024 | Primary, in-sample | 436 | 0.65045 | 0.65223 | 0.22938 | 0.22993 | 0.61009 | 0.61468 | +0.67 | 0.05840 | 0.05787 | [0.81959, -0.08543, 0.12807] |
| 2025 | Primary, frozen | 504 | 0.63730 | 0.64135 | 0.22369 | 0.22549 | 0.63492 | 0.63690 | +1.66 | 0.03729 | 0.04234 | [0.81959, -0.08543, 0.12807] |
| 2026 | Primary, frozen | 614 | 0.65876 | 0.66203 | 0.23325 | 0.23430 | 0.62052 | 0.61075 | +1.29 | 0.06739 | 0.06284 | [0.81959, -0.08543, 0.12807] |

### Secondary analyses (report only)

| Year | Stack | n | Loss | Brier | Accuracy | Paired t | ECE | Elo ECE | Weights |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2025 | Expanding through 2024 | 504 | 0.63730 | 0.22369 | 0.63492 | +1.66 | 0.03729 | 0.04234 | [0.81959, -0.08543, 0.12807] |
| 2026 | Expanding through 2025 | 614 | 0.65806 | 0.23300 | 0.62052 | +1.24 | 0.06888 | 0.06284 | [0.70162, -0.05608, 0.19030] |
| 2025 | Elo+round-share | 504 | 0.63983 | 0.22483 | 0.63889 | +0.75 | 0.06176 | 0.04234 | [0.96509, -0.10677] |
| 2026 | Elo+round-share | 614 | 0.65998 | 0.23370 | 0.61238 | +0.99 | 0.05646 | 0.06284 | [0.96509, -0.10677] |
| 2025 | Elo+lineup | 504 | 0.63717 | 0.22365 | 0.63889 | +1.91 | 0.04004 | 0.04234 | [0.76090, 0.13663] |
| 2026 | Elo+lineup | 614 | 0.65857 | 0.23309 | 0.62541 | +1.62 | 0.06429 | 0.06284 | [0.76090, 0.13663] |

The script prints ten reliability bins per year for the primary stack and Elo. Each bin reports its count, mean forecast, and observed win rate. The table reports their count-weighted absolute calibration gaps as ECE.

**Verdict: NOT PROVEN.** Both test-year paired t values are positive, but neither exceeds +2, and 2026 ECE exceeds Elo's. This result does not justify replacing production Elo. Prior consultation of both test years limits the strength of even a passing retrospective result.
