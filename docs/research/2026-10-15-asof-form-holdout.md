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
