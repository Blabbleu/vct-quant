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
