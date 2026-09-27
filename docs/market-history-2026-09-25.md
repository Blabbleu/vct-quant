# Market snapshot diagnostic (2026-09-25)

`python scripts/market_history.py` uses the existing append-only
`data/processed/prediction_log.parquet`; no new collection or production model
change is needed. Market quotes are sampled when `vct update` runs (nominally
every two hours). The first and last logged liquid quotes are **not** exchange
opening and closing prices. The script prints the lag of the last observation
relative to scheduled start; a long lag is not evidence about the closing line.

Protocol: select forecasts recorded before their then-scheduled start, with
`0 < p_market_a < 1` and observed bid/ask spread at most 0.10; require two
distinct timestamps for the same vlr.gg match, same team-key orientation and
same Polymarket slug. Join the recorded team A to a completed match by ID
(or by name only if no ID). Compare market against Elo on the *same snapshot*
with per-series log loss and paired t. Report all pairs and a **fixed** subgroup
where absolute Elo–market gap is at least 0.10 at each snapshot. This is a
diagnostic, not a model-selection or live-log tuning rule. The latest observed
quote must be within 24 hours of start before it can even serve as a practical
near-close proxy; no such inference is made by the script automatically.

On the 2026-09-25 dev snapshot: 84 logged rows / 12 distinct matches; 82
rows / 11 matches have a market price. Only 3 completed series have two
liquid pre-match observations. First and latest sampled quotes are identical
for those series: Elo log loss 0.5528, market 0.7588, paired t +0.87 in Elo's
favor. The median lag of the latest snapshot is **133.7 hours** (range
12.7–136.7), so this is emphatically **not a closing-line comparison**.
Only one series shows >=10 percentage points of model–market disagreement;
no subgroup paired statistic is available. Re-run after more live results;
do not infer a market edge from three matches.

## Refreshed snapshot (2026-09-27)

The same read-only diagnostic now finds 7 played series with two liquid,
pre-scheduled-start snapshots. The latest observation is a median 0.7 hours
before scheduled start (range 0.2–136.7h); the wide maximum means these remain
sampled quotes, not verified closing prices. First-snapshot Elo log loss is
0.5867 versus market 0.5647 (paired t=-0.18); latest-snapshot Elo is 0.5888
versus market 0.5469 (t=-0.32). In the fixed >=10pp disagreement subgroup,
first is Elo 0.6756 vs market 0.6650 (n=4, t=-0.05), latest is Elo 0.6916 vs
market 0.6373 (n=4, t=-0.22). None of these small samples establishes a
reliable advantage; positive t favors Elo. No outcomes or settings were tuned.
