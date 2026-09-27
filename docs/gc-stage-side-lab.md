# Game Changers stage-specific side-advantage diagnostic

## Status and frozen protocol (2026-09-27, before candidate test loss)

This is a retrospective research diagnostic, not a clean holdout: GC results
through 2026 have already been examined in `docs/gc-side-advantage.md` and
`docs/gc-ensemble-lab.md`. No result from this experiment may be described as
independent confirmation or used to retune the live log.

### Question

Does the existing fixed side-1 advantage (h=30 at K=192) vary between upper
bracket, lower bracket, and other GC stages? `match.event_series` contains
values such as `Upper Quarterfinals`, `Lower Round 1`, `Group A`, and
`Round Robin`. A separate side bias by bracket stage is plausible from
bracket seeding, but flexible stage offsets can overfit.

### Frozen data and classifier

Use the production GC `match_sequence(tiers=(3,))`, margin signal, continuous
chronological replay, and K=192. Join `match.event_series` by match ID. Classify
case-insensitive strings containing `upper` as upper, containing `lower` as
lower, and every other or empty value as `other`. This literal classifier is
fixed; do not hand-correct labels after scoring. Decisive matches only
(`score_a != 0.5`).

### Selection and decision

Tune stage-specific offsets on matches dated through 2024 only. Search each of
the three stages on h in {0, 10, ..., 60}; h enters both pre-match probability
and Elo update, as in `gc_side_lab`. Use the Cartesian grid and choose the
lowest mean training log loss; ties prefer lower total absolute deviation from
30, then lexicographic (upper, lower, other). Compare with the fixed h=30
reference on the same matches. No edge extension and no further tuning.

Score the selected tuple once on 2025-26 against the fixed h=30 reference.
Propose an experimental shadow-only candidate iff paired per-match t >= +2.0
and mean loss improves in each of 2025 and 2026. Otherwise reject and retain
the current A74 fixed-h shadow. Report sample counts by stage/year, overall and
year log loss/Brier/paired t, and the selected tune loss. Any passing result is
retrospective only; before implementation or production enablement it still
requires a separate approval and prospective live grading. No Tier-1/2 or
primary forecast changes are in scope.

## Result (dev snapshot, 2026-09-27)

`vctdev python scripts/gc_stage_side_lab.py` completed. `match_sequence`
contained 11,702 GC matches and no missing `event_series`; the decisive
selection/test counts are 5,779 / 5,678. Tune selected (upper h=30, lower h=0,
other h=30), versus fixed h=30 in every bucket: tune log loss 0.589304 vs
0.589714. Test 2025-26: fixed 0.599429, candidate 0.599900, paired t=-1.10;
Brier 0.207904 -> 0.208143. 2025: 0.598388 -> 0.598721 (t=-0.61); 2026:
0.600872 -> 0.601534 (t=-0.97). Candidate is worse overall and in both years;
**reject**. Test stage counts: upper 868 (459/409 in 2025/26), lower 714
(376/338), other 4,096 (2,463/1,633). These are retrospective data already
consulted in prior GC work, not independent confirmation. No new shadow,
primary forecast, log, or production flag.

Implementation: `scripts/gc_stage_side_lab.py`; 4 unit tests cover stage parsing,
fixed-h replay parity, tie-breaking, and paired-t sign. The classifier and
selection rule remain frozen above.
