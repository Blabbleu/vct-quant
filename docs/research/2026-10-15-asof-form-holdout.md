# Frozen Elo plus as-of form: post-cutoff holdout

## Preregistered protocol (written before scoring)

The two-column Elo plus as-of lineup form model was selected post hoc after looking at previously consulted 2025 and 2026 rows. Its earlier scores are retrospective evidence only. This holdout tests whether its log-loss gain persists on matches completed strictly after **2026-10-15T07:00:00Z**. Both inputs are causal under the [as-of replay policy](2026-10-15-asof-player-form.md): production Elo replay and player form from earlier matches only. A later snapshot can therefore supply new outcomes without changing the model choice.

Fit is fixed on decisive Tier-1 matches in 2023 and 2024 (769 rows on the freeze snapshot). Freeze the two-column diagnostic weights from `asof_form_stack.fit_frozen` and its first form-difference scale. The model is sigmoid(weight 1 × production Elo logit + weight 2 × as-of form difference / scale), with missing form difference set to zero. The scorer reads these values from `research/asof_form_holdout_frozen.json` and never refits. A freeze refit must agree within 1e-6 with documented weights **[0.87296870, 0.07737623]** and scale **0.09254274**, or fail.

Eligible rows are decisive Tier-1 series with UTC `completed_at` strictly after the freeze time. Sort by `completed_at` ascending and use the **first 150 rows** for the primary decision once available. Report any later rows separately. Compare candidate and production Elo on identical rows. Primary metric is paired per-series log-loss difference (Elo minus candidate) and its paired t statistic. Secondary metrics are Brier score, accuracy, and ten-bin expected calibration error (ECE), for both forecasts; also report distinct event count.

**Decision rule:** PENDING while fewer than 150 eligible rows exist. At 150 or more, WIN only if primary paired t > 2 and candidate ECE ≤ Elo ECE; NOT PROVEN if paired t > 0 but WIN fails; REJECTED if paired t ≤ 0. A WIN permits asking the owner for a live shadow column; it changes nothing by itself. The cutoff, first-150 window, and bar are frozen before any post-cutoff score is inspected.

## Results on worker snapshot

The offline scorer ran against the copied worker snapshot after the freeze artifact was written. It found **0** decisive Tier-1 series completed strictly after the cutoff, across **0** distinct events. The primary first-150 window contains **0** rows; there are **0** later rows. No post-freeze log loss, Brier, accuracy, paired t, or ECE exists yet for either forecast.

| Window | Decisive Tier-1 rows | Distinct events | Candidate log loss | Elo log loss | Paired t | Candidate ECE | Elo ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| First 150 (primary) | 0 | 0 | — | — | — | — | — |
| Later rows | 0 | 0 | — | — | — | — | — |

**Verdict: PENDING.** The 150-row gate has not been reached. Production is unchanged.

## 2026-10-15 power review and prospective amendment

**Guard before amendment.** Running `research/asof_form_holdout.py` on the copied worker snapshot returned **0** decisive Tier-1 rows completed strictly after 2026-10-15T07:00:00Z (`eligible_rows: 0`, `verdict: PENDING`). This count is the proof that the following rule was registered before any post-freeze outcome was scored. The original first-150 rule above is superseded by this section; the frozen JSON, two weights, form scale, and cutoff are unchanged.

The hypothesis remains that the frozen Elo plus as-of form forecast improves per-series log loss over production Elo on identical future matches. Paired log loss (Elo minus candidate) is primary; Brier, accuracy, and ten-bin ECE are secondary. No model was fit or retuned here. For power planning only, the previously consulted 2025 and 2026 decisive Tier-1 differences were recomputed using the frozen weights:

| Previously consulted rows | n | Mean paired log-loss gain | Paired SD | Mean / SD |
| --- | ---: | ---: | ---: | ---: |
| 2025 | 504 | 0.004195 | 0.044800 | 0.09364 |
| 2026 | 618 | 0.004444 | 0.042110 | 0.10555 |
| Pooled | 1,122 | 0.004333 | 0.043319 | 0.10001 |

The power study resamples individual paired differences with replacement (50,000 simulations, seed 20261015). The full scenario uses the observed pooled differences; the half scenario subtracts half their mean from every difference; the zero scenario centers them at zero. The null therefore preserves the observed spread and shape. These are planning estimates from previously consulted data, not a new holdout result. **ECE is ignored in every power simulation**, so actual WIN probabilities can be lower.

| Single look at 150, t > 2 | Estimated probability |
| --- | ---: |
| Full observed effect | 19.014% |
| Half effect | 6.280% |
| Zero effect (false WIN before ECE) | 1.370% |

A fixed-seed bootstrap grid search estimates **779 rows** for 80% power under the full effect and **3,179 rows** under the half effect at the single-look t > 2 bar. These approximate sample sizes exceed the original 150-row gate substantially.

**Amended decision rule.** Use the first eligible rows ordered by UTC `completed_at`, then `match_id`, at cumulative looks of **150, 300, 450, and 600**. At look index *k* (1 through 4), WIN only when cumulative paired t is strictly greater than `2.145578186160249 × sqrt(4/k)` **and** candidate ECE is no worse than Elo ECE on those same rows. Check looks in order and retain an earlier terminal verdict. From the 300-row look onward, REJECTED for futility if cumulative t is zero or negative. If no WIN or futility decision occurs by the 600-row look, the verdict is NOT PROVEN. Below 150 rows and between looks, the verdict is PENDING. The scorer continues to report the original first-150 statistics and separate later-row statistics, alongside the reached look and its cumulative statistics. No production behavior changes automatically.

| Cumulative look | Registered t boundary |
| ---: | ---: |
| 150 | 4.291156372320498 |
| 300 | 3.034305769999690 |
| 450 | 2.477500286694018 |
| 600 | 2.145578186160249 |

The constant was chosen by zero-effect resampling with the registered futility stops to keep the chance of any false WIN across four looks no higher than the original one-look t > 2 chance (about 2.3% under an ideal t null; 1.37% in this empirical null). A separate fixed-seed 50,000-run check estimates **1.206%** overall false WIN before ECE. Estimated power before ECE is **63.114%** under the full effect and **16.704%** under the half effect. The rule, boundary constant, and four numeric thresholds are stored in `research/asof_form_holdout_design.json`. This 2026-10-15 amendment replaces the underpowered one-time 150-row decision while the guard count was zero; it does not turn the retrospective years into clean validation evidence. The prospective verdict remains **PENDING** on this snapshot.
