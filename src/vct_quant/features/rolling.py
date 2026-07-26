"""Rolling/windowed form features (map winrates, recent player ratings, H2H).

Leakage rule for every function in this module: a feature for a match may only
aggregate rows strictly BEFORE that match's start time. Prefer shifted rolling
windows (e.g. groupby + shift(1) before rolling) over post-hoc filtering.
"""
from __future__ import annotations

# TODO: team_map_winrate(df, window), player_recent_rating(df, n_maps),
#       head_to_head_record(df) — implement once ETL lands canonical tables.
