"""Why does Elo score worse on 2026 than 2025? Read the errors, don't tune.

    python -i scripts/diagnose_2026.py     # -i drops you into a Python prompt with `df`

`df` has one row per scored Tier-1 match in 2025 and 2026:

    year, event_name, team_a_name, team_b_name
    p          Elo's pre-match P(team A wins)
    y          1 if team A won
    loss       that match's log loss (lower is better; coin flip = 0.693)
    confidence |p - 0.5|: how sure Elo was
    upset      Elo's favourite lost
    prior_min  prior official matches of the LESS experienced team
    name_key   a team fell back to a name key (no vlr.gg team ID resolved)

The exercise: find which slice of 2026 carries the extra loss. Always compare
the same slice in 2025 -- a slice being bad in 2026 only matters if it wasn't
equally bad before.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from vct_quant import db
from vct_quant.features.build import elo_k, margin_signal, match_sequence
from vct_quant.features.ratings import compute_elo

con = db.connect(read_only=True)
try:
    seq = match_sequence(con)
    events = con.execute("SELECT match_id, event_name FROM match").df()
finally:
    con.close()

elo = pd.DataFrame(compute_elo(
    zip(seq.match_id, seq.team_a, seq.team_b, margin_signal(seq).to_numpy()),
    k=elo_k(seq.tier),
)[0])

# Prior official matches per team, counted BEFORE each match (cumcount starts at 0).
sides = pd.concat([
    pd.DataFrame({"row": seq.index, "team": seq.team_a, "side": "a"}),
    pd.DataFrame({"row": seq.index, "team": seq.team_b, "side": "b"}),
]).sort_values(["row", "side"])
sides["prior"] = sides.groupby("team").cumcount()
prior = sides.pivot(index="row", columns="side", values="prior")

df = seq.assign(
    p=elo.p_a_win.to_numpy(),
    prior_min=np.minimum(prior.a, prior.b),
    name_key=seq.team_a.str.startswith("name:") | seq.team_b.str.startswith("name:"),
).merge(events, on="match_id")
df = df[df.tier.eq(1) & df.score_a.ne(0.5) & df.year.isin([2025, 2026])]
df = df.assign(y=df.score_a)
p = df.p.clip(1e-15, 1 - 1e-15)
df = df.assign(
    loss=-(df.y * np.log(p) + (1 - df.y) * np.log(1 - p)),
    confidence=(df.p - 0.5).abs(),
    upset=(df.p > 0.5) != (df.y == 1),
)[["match_id", "year", "event_name", "team_a_name", "team_b_name",
   "p", "y", "loss", "confidence", "upset", "prior_min", "name_key"]]

print(df.groupby("year").loss.agg(["size", "mean"]))
