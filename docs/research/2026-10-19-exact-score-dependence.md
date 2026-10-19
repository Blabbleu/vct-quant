# Exact-score map dependence: tuning diagnostics and part 2 registration

## Question and data boundary

The desk's exact-score distribution assumes independent maps at the map probability implied by the supplied series win probability. This study asks whether that distribution gets the conditional score, particularly sweeps, right. The series win probability is fixed throughout. The input here is raw margin Elo; the official Tier 1 primary became the fast/slow ensemble in 1ec45a3. Since the proposed adjustment conditions on any supplied series probability, it also transfers to that primary.

Replay `match_sequence` in full match-ID order: Tier 1 and Tier 2 together as the official rating pool with production `elo_k` (K=48 and K=0 respectively), and Game Changers separately (K=192). Assert the independent replay equals production `compute_elo` on **every row of each full sequence**, tolerance 1e-12, before using any rows for diagnostics. The tuning set comprises eligible completed Bo3 and Bo5 series in years through 2024. Use `match.best_of`, with the `scripts/model_lab.py` inference fallback when missing; discard Bo1, Bo2, other formats, forfeits, draws, and impossible final scores. The script reports drop counts by pool and year. The expected test sample counts may be computed from score legality, but no test-year outcome rate, loss, calibration, or fit may be computed in part 1.

## Part 2 trial, fixed before any 2025 or 2026 outcome or loss was computed

**Hypothesis.** Dependence among maps changes the conditional sweep rate. Candidate C preserves each row's series win probability exactly. Conditional on either winner, take the independent-maps probability of the shortest score (2-0/0-2 for Bo3; 3-0/0-3 for Bo5), add a single shift θ to its log-odds, and multiply by that winner's series probability. For Bo5, split the remaining conditional mass between 3-1 and 3-2 in their independent-maps ratio. Use one θ per pool and format. Fit it by maximum likelihood on that cell's eligible rows through 2024, bounded to [-2, 2]. No parameter uses a test-year outcome.

Test 2025 and 2026 separately, on the identical eligible rows for C and independent maps, only for a pool/format cell with at least 100 eligible rows in **both** years. The primary metric is mean conditional exact-score log loss, equivalent to full exact-score log loss for this comparison because the series term cancels. Compute paired per-series t for independent-maps loss minus C loss in each year. Secondary descriptive metrics are multiclass Brier and per-score calibration gap. For each legal score, the per-score calibration gap is the absolute difference between mean predicted probability and observed frequency on the same rows; it never enters the verdict.

For a given pool, format, and test year, the predicted sweep rate is the mean over eligible rows of the model's total probability of a sweep (2-0 plus 0-2 for Bo3, 3-0 plus 0-3 for Bo5). The observed sweep rate is the share of those same rows that ended in a sweep. The sweep calibration gap is the absolute value of predicted minus observed. C and independent maps are always compared on the identical set of rows; “no larger” means C's gap is less than or equal to the independent-maps gap.

**Verdict rule:** WIN for a pool and format only if the paired t is above 2 in both 2025 and 2026 and the sweep calibration gap is no larger in both years; otherwise NOT PROVEN; a win only justifies an owner ask for a shadow exact-score column, never a direct change.

Expected eligible test counts, from score-legality filtering only:

| Pool | Format | 2025 n | 2026 n | Part 2 status |
| --- | --- | ---: | ---: | --- |
| Tier 1 | Bo3 | 468 | 588 | Qualifies |
| Tier 1 | Bo5 | 30 | 34 | Excluded: fewer than 100 in both years |
| Tier 2 | Bo3 | 2,276 | 2,809 | Qualifies |
| Tier 2 | Bo5 | 145 | 108 | Qualifies |
| GC | Bo3 | 2,018 | 1,755 | Qualifies |
| GC | Bo5 | 51 | 55 | Excluded: fewer than 100 in both years |

No test-year outcome or loss is calculated in part 1.

## Part 1 tuning-year results

These results use only eligible rows through 2024. The paired t below is for **naive loss minus independent-maps loss**; a negative value means the pooled-sweep naive baseline was better. The naive baseline uses the pooled tuning-year sweep frequency conditional on either winner; for Bo5 it allocates non-sweep mass in the independent-maps 3-1:3-2 ratio. This baseline is descriptive and uses the same tuning rows for its rate and evaluation.

| Pool | Format | n | Predicted sweep | Observed sweep | Independent conditional loss | Naive conditional loss | Paired t | Fitted θ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tier 1 | Bo3 | 9,017 | .5148 | .7068 | .6706 | .6050 | -16.43 | .80497 |
| Tier 1 | Bo5 | 222 | .2658 | .3874 | 1.1137 | 1.0847 | -1.50 | .56340 |
| Tier 2 | Bo3 | 6,434 | .5105 | .6761 | .6870 | .6298 | -13.45 | .71073 |
| Tier 2 | Bo5 | 295 | .2653 | .3458 | 1.1093 | 1.0947 | -1.11 | .41444 |
| GC | Bo3 | 4,878 | .5504 | .7374 | .6345 | .5758 | -9.80 | .85274 |
| GC | Bo5 | 135 | .3051 | .4222 | 1.1192 | 1.0693 | -1.81 | .51826 |

The detailed filter counts, five favourite-probability bins (edges 0.5, 0.6, 0.7, 0.8, 0.9, 1.0; final bin includes 1.0), and conditional winner tables follow. `NaN` means the bin contains no rows.

```text
Filter counts by pool, year, reason (eligible included):
  pool  year     filter_reason    n
    GC  2022          eligible  602
    GC  2022      other_format  671
    GC  2023          eligible 2070
    GC  2023      other_format    6
    GC  2024          eligible 2341
    GC  2024      other_format   90
    GC  2025          eligible 2069
    GC  2025      other_format 1225
    GC  2026          eligible 1810
    GC  2026      other_format  573
Tier 1  2021 draw_or_no_winner    1
Tier 1  2021          eligible 5016
Tier 1  2021      other_format 1692
Tier 1  2022          eligible 3458
Tier 1  2022      other_format   60
Tier 1  2023          eligible  331
Tier 1  2023      other_format    2
Tier 1  2024          eligible  434
Tier 1  2024      other_format    2
Tier 1  2025          eligible  498
Tier 1  2025      other_format    6
Tier 1  2026          eligible  622
Tier 2  2022          eligible  178
Tier 2  2022      other_format   77
Tier 2  2023          eligible 2813
Tier 2  2023      other_format 1100
Tier 2  2024          eligible 3738
Tier 2  2024      other_format  688
Tier 2  2025          eligible 2421
Tier 2  2025      other_format  342
Tier 2  2026          eligible 2917
Tier 2  2026      other_format  296

Expected test n (eligibility counts only; zero shown explicitly):
Tier 1 Bo3: 2025=468, 2026=588
Tier 1 Bo5: 2025=30, 2026=34
Tier 2 Bo3: 2025=2276, 2026=2809
Tier 2 Bo5: 2025=145, 2026=108
GC Bo3: 2025=2018, 2026=1755
GC Bo5: 2025=51, 2026=55

Tier 1 Bo3: n=9017
sweep predicted=0.5148 observed=0.7068; conditional loss independent=0.6706 naive=0.6050 paired t(naive-independent)=-16.43; theta=0.80497
       bin    n  predicted  observed
[0.5, 0.6) 5841     0.5019    0.6915
[0.6, 0.7) 2044     0.5197    0.7143
[0.7, 0.8)  892     0.5579    0.7747
[0.8, 0.9)  220     0.6193    0.7591
[0.9, 1.0]   20     0.7173    0.8000
   winner    n  shortest_predicted  shortest_observed
favourite 6012              0.5401             0.7462
 underdog 3005              0.4804             0.6280

Tier 1 Bo5: n=222
sweep predicted=0.2658 observed=0.3874; conditional loss independent=1.1137 naive=1.0847 paired t(naive-independent)=-1.50; theta=0.56340
       bin   n  predicted  observed
[0.5, 0.6) 133     0.2523    0.3985
[0.6, 0.7)  58     0.2684    0.3793
[0.7, 0.8)  25     0.3083    0.3600
[0.8, 0.9)   6     0.3635    0.3333
[0.9, 1.0]   0        NaN       NaN
   winner   n  shortest_predicted  shortest_observed  full_length_predicted  full_length_observed
favourite 137              0.2899             0.4380                 0.3325                0.2190
 underdog  85              0.2272             0.3059                 0.4033                0.2706

Tier 2 Bo3: n=6434
sweep predicted=0.5105 observed=0.6761; conditional loss independent=0.6870 naive=0.6298 paired t(naive-independent)=-13.45; theta=0.71073
       bin    n  predicted  observed
[0.5, 0.6) 4929     0.5007    0.6827
[0.6, 0.7)  896     0.5200    0.6618
[0.7, 0.8)  418     0.5563    0.6411
[0.8, 0.9)  191     0.6167    0.6492
[0.9, 1.0]    0        NaN       NaN
   winner    n  shortest_predicted  shortest_observed
favourite 3636              0.5245             0.7057
 underdog 2798              0.4850             0.6376

Tier 2 Bo5: n=295
sweep predicted=0.2653 observed=0.3458; conditional loss independent=1.1093 naive=1.0947 paired t(naive-independent)=-1.11; theta=0.41444
       bin   n  predicted  observed
[0.5, 0.6) 195     0.2515    0.3231
[0.6, 0.7)  66     0.2710    0.3788
[0.7, 0.8)  20     0.2990    0.3500
[0.8, 0.9)  14     0.3831    0.5000
[0.9, 1.0]   0        NaN       NaN
   winner   n  shortest_predicted  shortest_observed  full_length_predicted  full_length_observed
favourite 166              0.2831             0.3554                 0.3402                0.2771
 underdog 129              0.2295             0.3333                 0.4007                0.2946

GC Bo3: n=4878
sweep predicted=0.5504 observed=0.7374; conditional loss independent=0.6345 naive=0.5758 paired t(naive-independent)=-9.80; theta=0.85274
       bin    n  predicted  observed
[0.5, 0.6) 1976     0.5024    0.7110
[0.6, 0.7) 1134     0.5209    0.6993
[0.7, 0.8)  857     0.5588    0.7491
[0.8, 0.9)  548     0.6289    0.7993
[0.9, 1.0]  363     0.7652    0.8788
   winner    n  shortest_predicted  shortest_observed
favourite 3364              0.5901             0.7782
 underdog 1514              0.4648             0.6466

GC Bo5: n=135
sweep predicted=0.3051 observed=0.4222; conditional loss independent=1.1192 naive=1.0693 paired t(naive-independent)=-1.81; theta=0.51826
       bin  n  predicted  observed
[0.5, 0.6) 40     0.2527    0.4750
[0.6, 0.7) 32     0.2701    0.4688
[0.7, 0.8) 33     0.3121    0.3939
[0.8, 0.9) 24     0.3854    0.3750
[0.9, 1.0]  6     0.4824    0.1667
   winner  n  shortest_predicted  shortest_observed  full_length_predicted  full_length_observed
favourite 97              0.3440             0.4433                 0.2824                0.2062
 underdog 38              0.2130             0.3684                 0.4223                0.2105
```
