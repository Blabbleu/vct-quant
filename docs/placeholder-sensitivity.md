# Completed/TBD placeholder sensitivity (read-only)

**Decision rule frozen before scoring retrospective 2025–26 Tier-1 rows.**
Compare the current Elo replay with a replay excluding exactly match IDs 10802
(Kaggle) and 97028 (event), which are labeled completed but have a TBD side.
Do not retune K or any other parameter. Score only the same genuinely resolved
Tier-1 match IDs in 2025–26, after both excluded IDs, with known binary winners.
Report n, paired per-match log-loss difference (current minus exclusion), paired
t, and maximum probability delta. Positive t favors exclusion. This is a
retrospective **data-correction diagnostic**, not an untouched holdout or a
promotion test: years through 2026 have already informed model selection. An
improvement is not grounds to change primary forecasts without a separate
approval. A worsening also cannot make a fabricated result valid; reconcile the
upstream match identities before proposing any correction. Never edit the live
DB or the live prediction log for this audit.

The fixed exclusion set comes from `scripts/placeholder_audit.py`; it is not
chosen by the comparison's score. Current additive DB state can differ from a
clean rebuild, so only claim a counterfactual on this snapshot.

## Snapshot result (2026-09-25)

`python -m scripts.placeholder_scoring` on the refreshed dev DB snapshot:
2025–26 n=1,096 resolved Tier-1 matches, current log loss 0.658685279,
excluding both 0.658685307, paired t=−0.076 (positive favors exclusion),
max absolute probability delta 0.000025730. Exclusion is fractionally worse;
this is far below meaningful forecast resolution. The placeholder rows remain
invalid source evidence, but there is no retrospective performance rationale
for a production primary-scope change. Do not edit the live DB; defer any
correction to a separate data-provenance review and approval.
