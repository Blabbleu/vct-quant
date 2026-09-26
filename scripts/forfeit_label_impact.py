"""Read-only counterfactual: how do forfeit labels move Elo? (docs/forfeit-labels.md)

    python -m scripts.forfeit_label_impact

Variants (rule frozen in the doc before this ran):
  current      the DB as stored
  skip         drop completed matches with no scored map from the replay
               (either series score missing, or 0-0 with no stored winner)
  feed_winner  keep them, but label with the source feed's explicit winner

Scored on resolved 2025-2026 matches of each pool with a paired per-match
log-loss t (positive = variant better). Never writes the DB or the fixture
cache; not a production change.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.winner_integrity_audit import feed_winners
from vct_quant import db
from vct_quant.config import PROCESSED_DIR
from vct_quant.etl.entity_resolution import normalize_name
from vct_quant.features.build import elo_k, margin_signal, match_sequence, unscored_forfeit
from vct_quant.features.ratings import DEFAULT_BASE, compute_elo, expected_score


def unscored_mask(history: pd.DataFrame) -> pd.Series:
    """Same rows the opt-in `SKIP_UNSCORED_FORFEITS` flag drops from the replay."""
    return unscored_forfeit(history)


def feed_labels(history: pd.DataFrame, feed: pd.DataFrame) -> pd.Series:
    """Feed winner as a team-A label (1/0) for unscored rows whose names match."""
    out = pd.Series(np.nan, index=history.index)
    if feed.empty:
        return out
    by_id = feed.set_index("match_id")
    for i in history.index[unscored_mask(history)]:
        mid = int(history.at[i, "match_id"])
        if mid not in by_id.index:
            continue
        f = by_id.loc[mid]
        a = normalize_name(str(history.at[i, "team_a_name"]))
        b = normalize_name(str(history.at[i, "team_b_name"]))
        if {a, b} != {normalize_name(f.feed_name_1), normalize_name(f.feed_name_2)} or a == b:
            continue
        out[i] = 1.0 if normalize_name(f.feed_winner_name) == a else 0.0
    return out


def replay(history: pd.DataFrame, signal: pd.Series | None = None) -> tuple[pd.DataFrame, dict]:
    sig = margin_signal(history) if signal is None else signal
    rows, ratings = compute_elo(
        zip(history.match_id, history.team_a, history.team_b, sig.to_numpy()),
        k=elo_k(history.tier),
    )
    return pd.DataFrame(rows), ratings


def variants(history: pd.DataFrame, feed: pd.DataFrame) -> dict[str, tuple[pd.DataFrame, dict]]:
    history = history.reset_index(drop=True)
    skip = unscored_mask(history)
    labels = feed_labels(history, feed)
    fed = margin_signal(history).where(labels.isna(), labels)
    return {
        "current": replay(history),
        "skip": replay(history.loc[~skip].reset_index(drop=True)),
        "feed_winner": replay(history, fed),
    }


def per_match_loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def paired(history: pd.DataFrame, runs: dict, tier: int, years=(2025, 2026)) -> dict:
    """Paired comparisons on resolved matches that every variant scored."""
    eval_rows = history.loc[
        history.tier.eq(tier) & history.score_a.isin((0.0, 1.0))
        & ~unscored_mask(history)
        & (history.completed_at.dt.year.isin(years) | history.year.isin(years))
    ][["match_id", "score_a"]]
    base = eval_rows.merge(runs["current"][0][["match_id", "p_a_win"]], on="match_id")
    y = base.score_a.to_numpy(float)
    cur = per_match_loss(y, base.p_a_win.to_numpy(float))
    out = {"n": len(base), "current": float(cur.mean())}
    for name in ("skip", "feed_winner"):
        alt = base[["match_id"]].merge(runs[name][0][["match_id", "p_a_win"]],
                                       on="match_id", how="left", validate="one_to_one")
        la = per_match_loss(y, alt.p_a_win.to_numpy(float))
        d = cur - la
        sd = d.std(ddof=1)
        out[name] = float(la.mean())
        out[f"{name}_t"] = float(d.mean() / (sd / np.sqrt(len(d)))) if sd > 0 else None
        out[f"{name}_max_abs_dp"] = float(np.abs(base.p_a_win.to_numpy(float)
                                                 - alt.p_a_win.to_numpy(float)).max())
    return out


def fixture_deltas(fixtures: pd.DataFrame, runs: dict, tier: int) -> pd.DataFrame:
    """Cached upcoming fixtures of one pool: probability under each variant."""
    f = fixtures.loc[fixtures.tier.eq(tier)
                     & fixtures.team_a_name.str.casefold().ne("tbd")
                     & fixtures.team_b_name.str.casefold().ne("tbd")]
    rows = []
    for fx in f.itertuples(index=False):
        rec = {"match_id": fx.match_id, "a": fx.team_a_name, "b": fx.team_b_name}
        for name, (_, ratings) in runs.items():
            rec[name] = expected_score(ratings.get(fx.team_a_key, DEFAULT_BASE),
                                       ratings.get(fx.team_b_key, DEFAULT_BASE))
        rows.append(rec)
    return pd.DataFrame(rows)


def main() -> None:
    from vct_quant.etl.normalize import _archive_chronological_paths, _archived_feed_rows

    feed = feed_winners(_archive_chronological_paths("event_matches_*.json"), _archived_feed_rows)
    with db.connect(read_only=True) as con:
        official = match_sequence(con, tiers=(1, 2))
        gc = match_sequence(con, tiers=(3,))
    path = PROCESSED_DIR / "upcoming_tier1.parquet"
    fixtures = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    if not fixtures.empty and "tier" not in fixtures.columns:
        fixtures["tier"] = 1

    for label, history, tier in (("Tier 1 (official replay)", official, 1),
                                 ("Game Changers pool", gc, 3)):
        history = history.reset_index(drop=True)
        mask = unscored_mask(history)
        labels = feed_labels(history, feed)
        print(f"\n== {label}: {len(history)} matches in replay, "
              f"{int(mask.sum())} unscored (tier counts "
              f"{history.loc[mask, 'tier'].value_counts().to_dict()}), "
              f"{int(labels.notna().sum())} with a feed winner")
        runs = variants(history, feed)
        print("  2025-26 paired log loss:", paired(history, runs, tier))
        if not fixtures.empty:
            fd = fixture_deltas(fixtures, runs, tier)
            if not fd.empty:
                fd["skip_dp"] = (fd.skip - fd.current).abs()
                fd["feed_dp"] = (fd.feed_winner - fd.current).abs()
                print(f"  cached fixtures n={len(fd)}: max |dp| skip={fd.skip_dp.max():.6f} "
                      f"feed_winner={fd.feed_dp.max():.6f}")
                with pd.option_context("display.width", 200):
                    print(fd.sort_values("skip_dp", ascending=False).head(5).to_string(index=False))
        cur, skip = runs["current"][1], runs["skip"][1]
        moved = sorted(((k, cur.get(k, DEFAULT_BASE) - skip.get(k, DEFAULT_BASE))
                        for k in cur.keys() | skip.keys()), key=lambda kv: -abs(kv[1]))
        print("  largest final-rating changes (current - skip):",
              [(k, round(v, 2)) for k, v in moved[:6]])
    print("\nRead-only counterfactual; primary forecasts unchanged.")


if __name__ == "__main__":
    main()
