# Season-start Elo error and as-of lineup churn

## Protocol registered before diagnostics (2026-10-19)

**Hypothesis.** Production margin Elo may have higher error in a continuing team's first Tier-1 series of a calendar year, and strictly prior, observed lineup churn may explain some of that error. This is a descriptive availability audit. No rating adjustment is fitted or scored in this task.

**Data and order.** Read the local snapshot through `scripts/model_lab.py::load`. Ascending match ID is the chronology proxy, including for lineups; it is not a verified kickoff time. Calendar year from that sequence is the season. Replay all Tier-1 series, including draws, for production Elo; Tier-2 results have zero Elo weight. Score only decisive Tier-1 series in 2023, 2024, 2025, and 2026, on identical rows. Assert replay probabilities equal `compute_elo` within absolute tolerance `1e-12` on all Tier-1 rows.

**Windows.** A continuing team key has at least one Tier-1 series in the immediately previous calendar year. Its first, second, and third *decisive* Tier-1 series in the current year form the first-three window. Its first such series forms the first-series window. A scored row enters a window if either side qualifies; count rows with both sides separately. All other decisive Tier-1 rows in that year are the corresponding rest group. New keys and keys absent from the preceding Tier-1 year do not qualify. A team appearing in a draw has not advanced its decisive-series counter.

**Churn.** For each side, retain its last observed lineup in the preceding calendar year and its most recent observed lineup from any tier in the current year with a strictly lower match ID. Churn is the share of the previous-year five absent from the current-year lineup. Require an observed five-player previous-year lineup; otherwise churn is missing. Missing current-year prior lineup also yields missing churn. A current match's own lineup produces a separately labelled *oracle* churn, used only descriptively. Missing lineups never erase an earlier observation. If a team has multiple qualifying sides in a match, each side is counted once. For row-level loss splits, use the maximum known churn across qualifying sides and mark as-of availability when at least one qualifying side has known as-of churn.

**Diagnostics.** For each year and both windows, report the season-start and rest n, production Elo log loss (primary), Brier, their start-minus-rest differences, a Welch t on per-row loss, and ten-bin ECE on season-start rows. Report as-of churn coverage as known versus missing qualifying sides, plus distributions of as-of and oracle churn (bins 0, (0, 0.4], and >0.4, with missing shown). Report mean Elo log loss on season-start rows by oracle churn bin and by as-of availability. Accuracy is a secondary descriptive metric. Welch t is signed positive when start loss exceeds rest loss; it does not imply causal churn effects. A missing group has no mean or t.

**Pre-registered follow-up trial, not run here.** At each team's first Tier-1 series of a new calendar year, before predicting that series, move its current rating toward 1500 by fraction `a + b × as-of churn`, with missing churn treated as zero. The as-of lineup must have a lower match ID. Use grid `a ∈ {0, 0.1, 0.2, 0.3, 0.5}` and `b ∈ {0, 0.25, 0.5}`; select the pair with lowest pooled log loss on 2024 plus 2025 season-start **first-three** rows. Keep production K, margin signal, and all other Elo mechanics fixed. Score the selected pair once on 2026 season-start first-three rows against production Elo on identical matches. Report paired t of per-match production loss minus trial loss, plus both ECEs. A **WIN** requires paired t strictly above +2 and trial ECE no worse on 2026, plus confirmation on Kickoff 2027 rows before any go-live request. Otherwise the verdict is **NOT PROVEN**. No rule is selected or scored in this task. This 2026 snapshot has already been consulted by other research, so even that later score will not be a clean holdout. The season-start sample is expected to be small; measured n is recorded below after the diagnostic run.

## Results

Run with `python research/season_start.py` on the local snapshot. The production replay matched `compute_elo` on every Tier-1 row at absolute tolerance `1e-12`. `Δ` is season-start minus rest; positive Welch t means higher season-start log loss. ECE and accuracy refer to season-start rows. The expected sample for the later 2026 first-three score is **79 rows** (33 first-series rows); this is an observed snapshot count, not a power guarantee.

| Year | Window | Start n | Both sides | Rest n | Start LL | Rest LL | ΔLL | Welch t | Start Brier | Rest Brier | ΔBrier | Start ECE | Start accuracy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 | First | 16 | 15 | 317 | 0.68814 | 0.60277 | +0.08538 | +0.57 | 0.23363 | 0.20772 | +0.02591 | 0.37534 | 0.62500 |
| 2023 | First-three | 57 | 36 | 276 | 0.63383 | 0.60130 | +0.03252 | +0.49 | 0.21876 | 0.20694 | +0.01182 | 0.09371 | 0.66667 |
| 2024 | First | 24 | 12 | 412 | 0.50605 | 0.66074 | −0.15469 | −2.25 | 0.16667 | 0.23362 | −0.06694 | 0.11082 | 0.75000 |
| 2024 | First-three | 69 | 39 | 367 | 0.72384 | 0.63876 | +0.08508 | +1.35 | 0.25805 | 0.22465 | +0.03340 | 0.11265 | 0.57971 |
| 2025 | First | 33 | 11 | 471 | 0.60492 | 0.64391 | −0.03898 | −0.61 | 0.20925 | 0.22663 | −0.01738 | 0.15110 | 0.69697 |
| 2025 | First-three | 79 | 51 | 425 | 0.65725 | 0.63840 | +0.01886 | +0.39 | 0.23227 | 0.22423 | +0.00804 | 0.10786 | 0.63291 |
| 2026 | First | 33 | 11 | 589 | 0.72825 | 0.65968 | +0.06857 | +1.01 | 0.26434 | 0.23327 | +0.03107 | 0.20453 | 0.57576 |
| 2026 | First-three | 79 | 52 | 543 | 0.70264 | 0.65759 | +0.04504 | +1.04 | 0.25309 | 0.23228 | +0.02081 | 0.13214 | 0.58228 |

Coverage and churn distributions count **qualifying sides**, so they may exceed row n. The four distribution columns are exact-zero, (0, 0.4], >0.4, and missing, respectively. Lineups with a preceding-year roster other than exactly five players have missing churn. On a row with two qualifying sides, the loss split below takes the maximum known churn.

| Year | Window | As-of known / missing sides | As-of churn distribution | Oracle churn distribution |
| --- | --- | ---: | --- | --- |
| 2023 | First | 0 / 31 | 0, 0, 0, 31 | 3, 10, 17, 1 |
| 2023 | First-three | 60 / 33 | 6, 21, 33, 33 | 9, 31, 50, 3 |
| 2024 | First | 0 / 36 | 0, 0, 0, 36 | 2, 17, 16, 1 |
| 2024 | First-three | 70 / 38 | 4, 34, 32, 38 | 6, 51, 48, 3 |
| 2025 | First | 0 / 44 | 0, 0, 0, 44 | 7, 21, 16, 0 |
| 2025 | First-three | 86 / 44 | 14, 44, 28, 44 | 21, 65, 44, 0 |
| 2026 | First | 0 / 44 | 0, 0, 0, 44 | 2, 22, 20, 0 |
| 2026 | First-three | 87 / 44 | 4, 44, 39, 44 | 6, 65, 60, 0 |

Mean production Elo loss by **oracle** churn bin (n / LL). Oracle uses the current match lineup and is never a candidate input.

| Year | Window | 0 | (0, 0.4] | >0.4 | Missing |
| --- | --- | ---: | ---: | ---: | ---: |
| 2023 | First | 0 / NA | 4 / 0.59685 | 12 / 0.71858 | 0 / NA |
| 2023 | First-three | 2 / 0.79466 | 14 / 0.56824 | 40 / 0.65374 | 1 / 0.43387 |
| 2024 | First | 2 / 0.17716 | 6 / 0.42705 | 15 / 0.59860 | 1 / 0.24950 |
| 2024 | First-three | 5 / 1.19353 | 20 / 0.63897 | 43 / 0.68824 | 1 / 1.60349 |
| 2025 | First | 5 / 0.48540 | 15 / 0.58493 | 13 / 0.67395 | 0 / NA |
| 2025 | First-three | 5 / 0.65199 | 37 / 0.64883 | 37 / 0.66639 | 0 / NA |
| 2026 | First | 2 / 0.78796 | 14 / 0.75006 | 17 / 0.70326 | 0 / NA |
| 2026 | First-three | 2 / 0.53344 | 29 / 0.69912 | 48 / 0.71181 | 0 / NA |

Mean production Elo loss by **as-of availability** (row n / LL). Known means at least one qualifying side has known as-of churn.

| Year | Window | Known | Missing |
| --- | --- | ---: | ---: |
| 2023 | First | 0 / NA | 16 / 0.68814 |
| 2023 | First-three | 40 / 0.61710 | 17 / 0.67319 |
| 2024 | First | 0 / NA | 24 / 0.50605 |
| 2024 | First-three | 48 / 0.77395 | 21 / 0.60931 |
| 2025 | First | 0 / NA | 33 / 0.60492 |
| 2025 | First-three | 60 / 0.65775 | 19 / 0.65568 |
| 2026 | First | 0 / NA | 33 / 0.72825 |
| 2026 | First-three | 60 / 0.70292 | 19 / 0.70174 |

**Descriptive verdict: NOT PROVEN.** Start-versus-rest log loss changes sign between years, and the 2026 first-three gap has Welch t only +1.04. Oracle churn is often high, but the corresponding bins do not show a stable error gradient. In this snapshot, no continuing first-series side has a current-year lineup observed before its first decisive Tier-1 series; the proposed one-time first-series adjustment would therefore treat churn as zero on those rows. The first-three coverage arises after the first series and does not establish first-series availability. Match ID may misorder overlapping completed matches. The 2026 data have been consulted by earlier desk research, and these small subsets are retrospective. **No shrink rule was scored or selected.**
