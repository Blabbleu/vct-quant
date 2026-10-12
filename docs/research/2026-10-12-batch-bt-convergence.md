# Frozen batch BT convergence audit (2026-10-12)

## Protocol registered before computation

Hypothesis: the frozen maps Bradley–Terry cell (365-day half-life, penalty 1.0) can silently stop before numerical convergence because its L-BFGS-B fit allows only 20 iterations and checks only finite strengths. This is a numerical fidelity audit of that existing forecast, **not a fresh walk-forward model test**, a parameter search, or a revision of the earlier retrospective verdict. No outcomes are used to choose the chronology sample beyond the fixed binary/decisive Tier-1 eligibility definition.

Data: the local canonical match sequence, ordered by match ID, with the same team indexing, map observations, three-day calendar buckets, strict prior-bucket exclusion, age weights, and warm starts as `research/batch_bt.py::replay`. For each of 2023, 2024, 2025, and 2026 with eligible fixtures, form distinct three-day buckets containing a Tier-1 fixture whose `score_a` is 0 or 1. Select the **first, lower median, and last** such bucket by bucket date (deduplicate if fewer than three). Match-ID chronology can revisit a calendar bucket and trigger a new warm-started fit. For each selected date bucket, audit its **first forecast visit containing an eligible fixture of that year**, and select all eligible fixtures in that contiguous visit. The visit tie-break uses match-ID order and eligibility only; neither winner direction nor model score influences it. Freeze the selection before any refit.

For every selected bucket visit, record the frozen 20-iteration fit's success flag, termination message, iteration count, objective, and maximum absolute analytic gradient, plus the selected fixture probabilities. Refit its **identical eligible observations, age weights, team index and original warm-start vector** with L-BFGS-B `maxiter=2000`, `ftol=1e-12`, `gtol=1e-8`. The registered reference convergence check is maximum absolute analytic gradient **at most 1e-5**, independent of the optimizer success flag. If any reference fit fails it, the result is **INCONCLUSIVE**; do not claim stable forecasts. A capped or unconverged original fit is one that reaches 20 iterations or has gradient above 1e-5 or reports failure. Compare each bucket fixture's absolute probability change; summarize maximum and median changes by year and overall. A material numerical impact is any fixture change at least **0.005** in absolute probability, or an overall median at least **0.001**. If all reference fits pass, label MATERIAL if this bar is met, otherwise STABLE AT THIS SAMPLE. The pass bar is about the frozen forecast's numerical fidelity, not predictive log loss.

Primary measurement is absolute change in pre-match probability. Log loss is the original model research's primary predictive metric; Brier, accuracy and calibration are secondary there. They are not recalculated here because paired outcomes do not establish numerical convergence and this small chronology sample is not a new walk-forward evaluation. The prior Elo baseline and prior 2025/2026 test-year verdict remain as reported in the frozen-cell and stack studies. Execution budget: one frozen-cell replay, then at most twelve registered refits, on at most two CPUs and 2 GiB; no grid or new dependencies.

## Registered-pass results

An initial instrumented replay exposed repeated visits to the same calendar bucket and stopped before any refit or probability-change result. The first/median/last date buckets stayed fixed; the first eligible visit rule above was clarified before the completed audit replay. This limits the audit to one actual forecast fit per selected bucket.

The local snapshot yielded three selected calendar buckets per year. Each date below is the three-day bucket start; fixture IDs are the eligible Tier-1 matches in the first eligible forecast visit. The frozen replay was run once. All twelve original fits reported optimizer success and stopped on relative objective reduction, but all had gradients above the registered `1e-5` check; none hit the 20-iteration cap. The registered reference fits also all reported optimizer success and stopped on relative objective reduction, but **all twelve failed the gradient check**. Thus the preregistered result is **INCONCLUSIVE**; its small probability changes cannot establish numerical stability.

In both tables `f`, `r1`, and `r2` mean original frozen fit, registered reference, and post-audit reference. All three report success with termination `CONVERGENCE: RELATIVE REDUCTION OF F <= FACTR*EPSMCH`. `G` is maximum absolute analytic gradient, `F` is the weighted MAP objective, and changes are absolute probability differences against `f` over the listed fixtures.

| Year | Bucket start | Fixture IDs | n | f iters | f F | f G | r1 iters | r1 F | r1 G | max Δp | median Δp |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 | 2023-02-13 | 167348, 167349, 167350, 167351, 167352, 167353, 167354, 167355 | 8 | 12 | 8342.951513 | 0.014 | 23 | 8342.951237 | 0.000157 | 0.000096190 | 0.000018840 |
| 2023 | 2023-05-17 | 184032, 184033, 184034, 184035 | 4 | 10 | 8217.823011 | 0.0117 | 22 | 8217.822699 | 0.000184 | 0.000083068 | 0.000032347 |
| 2023 | 2023-08-24 | 248276, 248277 | 2 | 6 | 8761.692484 | 0.0132 | 18 | 8761.692123 | 9.74e-05 | 0.000228109 | 0.000228109 |
| 2024 | 2024-02-14 | 295605, 295606 | 2 | 11 | 7093.596790 | 0.0277 | 22 | 7093.596574 | 2.27e-05 | 0.000002708 | 0.000001898 |
| 2024 | 2024-05-23 | 348059, 348061, 348063, 348064 | 4 | 11 | 8720.613212 | 0.0133 | 22 | 8720.612893 | 9.93e-05 | 0.000049188 | 0.000019968 |
| 2024 | 2024-08-24 | 378829 | 1 | 5 | 9016.065903 | 0.0932 | 17 | 9016.065455 | 0.000201 | 0.000242251 | 0.000242251 |
| 2025 | 2025-01-09 | 430837, 430838 | 2 | 14 | 8031.901998 | 0.106 | 25 | 8031.900612 | 0.000623 | 0.000012007 | 0.000011317 |
| 2025 | 2025-05-06 | 482503, 482504 | 2 | 8 | 8814.227010 | 0.148 | 21 | 8814.225559 | 3.99e-05 | 0.000017187 | 0.000011627 |
| 2025 | 2025-10-03 | 542270, 542272 | 2 | 6 | 8390.396898 | 0.0132 | 17 | 8390.396722 | 4.42e-05 | 0.000117821 | 0.000117821 |
| 2026 | 2026-01-13 | 596398, 596399 | 2 | 7 | 7133.451871 | 0.0186 | 18 | 7133.451730 | 5.34e-05 | 0.000033889 | 0.000022702 |
| 2026 | 2026-05-13 | 660369, 660370, 660371, 660372 | 4 | 8 | 9186.590864 | 0.013 | 20 | 9186.590569 | 6.56e-05 | 0.000046461 | 0.000033688 |
| 2026 | 2026-10-10 | 754734, 754735 | 2 | 5 | 8305.292262 | 0.132 | 20 | 8305.290560 | 2.46e-05 | 0.001526149 | 0.001097755 |

### Registered summary

| Year | Sampled fits | Fixtures | Capped or unconverged frozen fits | Failed reference checks | Max Δp | Median Δp |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 | 3 | 14 | 3 | 3 | 0.000228109 | 0.000026866 |
| 2024 | 3 | 7 | 3 | 3 | 0.000242251 | 0.000014194 |
| 2025 | 3 | 6 | 3 | 3 | 0.000117821 | 0.000014597 |
| 2026 | 3 | 8 | 3 | 3 | 0.001526149 | 0.000039141 |
| overall | 12 | 35 | 12 | 12 | 0.001526149 | 0.000023308 |

## Second, post-audit numerical pass

**Caveat:** This second pass was prompted by the failed registered reference check; it was not part of the original pass bar. It starts from each identical original warm-start vector and uses identical strictly prior-bucket training indices and age weights. It changes only L-BFGS-B termination to `ftol=0`, `gtol=1e-8`, with a finite `maxiter=5000`. It applies the unchanged `1e-5` maximum absolute gradient check. These are twelve additional refits, making one frozen replay plus 24 refits across the two labeled passes. The script checks `training_day < bucket_start_day` for every refit.

| Year | Bucket start | r2 iters | r2 F | r2 G | max Δp | median Δp |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2023 | 2023-02-13 | 33 | 8342.951237 | 4.54e-07 | 0.000095795 | 0.000018751 |
| 2023 | 2023-05-17 | 32 | 8217.822699 | 4.39e-07 | 0.000083175 | 0.000032180 |
| 2023 | 2023-08-24 | 27 | 8761.692123 | 1.08e-06 | 0.000227402 | 0.000227402 |
| 2024 | 2024-02-14 | 29 | 7093.596574 | 4.85e-07 | 0.000002715 | 0.000001896 |
| 2024 | 2024-05-23 | 30 | 8720.612893 | 4.46e-06 | 0.000049233 | 0.000019735 |
| 2024 | 2024-08-24 | 27 | 9016.065455 | 4.77e-07 | 0.000241359 | 0.000241359 |
| 2025 | 2025-01-09 | 35 | 8031.900612 | 1.28e-06 | 0.000011695 | 0.000011115 |
| 2025 | 2025-05-06 | 30 | 8814.225559 | 5.3e-07 | 0.000017178 | 0.000011600 |
| 2025 | 2025-10-03 | 28 | 8390.396722 | 7.19e-07 | 0.000117031 | 0.000117031 |
| 2026 | 2026-01-13 | 29 | 7133.451730 | 4.13e-07 | 0.000033837 | 0.000022767 |
| 2026 | 2026-05-13 | 29 | 9186.590569 | 3.92e-06 | 0.000046458 | 0.000033703 |
| 2026 | 2026-10-10 | 29 | 8305.290560 | 1.43e-06 | 0.001526107 | 0.001097756 |

### Post-audit summary

| Year | Sampled fits | Fixtures | Capped or unconverged frozen fits | Failed reference checks | Max Δp | Median Δp |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 | 3 | 14 | 3 | 0 | 0.000227402 | 0.000026918 |
| 2024 | 3 | 7 | 3 | 0 | 0.000241359 | 0.000013692 |
| 2025 | 3 | 6 | 3 | 0 | 0.000117031 | 0.000014437 |
| 2026 | 3 | 8 | 3 | 0 | 0.001526107 | 0.000039113 |
| overall | 12 | 35 | 12 | 0 | 0.001526107 | 0.000023018 |

The post-audit pass meets the stated gradient check in all twelve fits. Its largest change is on 2026-10-10, match 754735: frozen `0.578783139` versus converged `0.580309246` (absolute change `0.001526107`). Another concrete case is 2024-08-24, match 378829: `0.499830208` versus `0.499588849` (change `0.000241359`). The overall median change is `0.000023018`; neither preregistered material-impact threshold is crossed. **Post-audit conclusion: STABLE AT THIS SAMPLE.** This applies only to the first eligible visits of twelve selected date buckets and does not establish stability for every replay fit or alter the previous four-input stack verdict.

The script prints the full original and refit success flags, termination reasons, objectives, gradients, fixture IDs, and per-fixture probabilities for both passes. Command: `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python research/batch_bt_convergence.py` with a 2 GiB virtual-memory cap. No new model selection or predictive backtest was performed.
