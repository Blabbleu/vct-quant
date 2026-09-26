# Live holdout grading integrity

The CLI grader (`scripts/grade_predictions.py`) and desk `graded_log()` use the
same read-only `live_grading.graded_forecasts` gate. The latest forecast strictly
before the **earliest scheduled start ever logged for that match** is eligible
only if the Match Center's `load_result` verifies **both** canonical sides,
decisive series score and winner flags, and completion date. A later feed
reschedule cannot rehabilitate a forecast made after the original announced
kickoff; an earlier eligible call is kept instead. A canonical reschedule
cannot make a result eligible when it completed before the *selected forecast's*
logged scheduled day. Conflicting rows at the same latest timestamp are withheld
instead of picking an arbitrary pairing. Invalid probabilities and post-cutoff
samples are excluded. `/results` and team-page logged calls use the same
conservative cutoff and completion-day check, and withhold conflicting ties.
No prediction-log, DB, primary forecast or shadow parameter is changed.

Previously the grader and desk joined to **one** matching team by ID *or* name,
without verifying the other team, the series score, or the completion date. A
changed opponent or scoreless forfeit could enter the only prospective holdout.
The `/results` page already used the stricter result verification; the shared
grade gate now follows it. Synthetic DuckDB regression: side 1 matches but
opponent ID/name differs; both grader and desk withhold it. A conflicting
latest-timestamp pairing and a stale logged schedule are unit-covered.

On the Sep 26 dev snapshot, the CLI still grades 6 forecasts (log loss 0.5837,
Brier 0.1966), with 14 pre-scheduled-start fixtures. All six graded IDs match
`/results`' verified set exactly. The walk-forward backtest remains n=1,678.
The Sep 26 08:49Z dev snapshot has 185 logged rows/14 fixtures and one
fixture with two scheduled times (753459); the conservative cutoff changes zero
selected latest calls. The six graded IDs and six `/results` verified IDs still
match. Synthetic reschedule tests show a post-original-kickoff row excluded even
when it precedes its new schedule, and a result completed before the logged day
withheld from the descriptive tally. This is still **integrity**, not a model
improvement or a new holdout estimate.

Caveats: the earliest *logged* start is not necessarily the actual kickoff or
the first announced schedule (logging may have started late); a reliable
actual-start source is needed. The conservative rule can discard legitimate
postponed-match forecasts. The gate uses `load_result` per finished fixture, which does separate read-only
DB queries per fixture; batch reads may matter as the log grows. Live scoring
has always mixed the two rating pools in the headline CLI/desk aggregate; the
per-tier breakdown should be used for pool-specific interpretation.
