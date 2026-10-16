"""Exact synthetic raw-map joins and point-in-time replay cases."""
import pandas as pd

from research.asof_economy import replay
from research.asof_economy_kaggle import build_economy, coverage


def matches():
    return pd.DataFrame([
        dict(match_id=mid, team_a="1", team_b="2", team_a_name="Red", team_b_name="Blue",
             maps_a=2, maps_b=0, tier=1, year=year, score_a=1.0)
        for mid, year in [(10, 2023), (20, 2023), (30, 2024), (40, 2025), (50, 2026)]
    ])


def raw():
    eco, ids = [], []
    for mid, year in [(10, 2023), (20, 2023), (30, 2024), (40, 2025), (50, 2026)]:
        for game, map_name, full, win, pistol in [(mid * 10 + 1, "Bind", 2, 1, 1),
                                                  (mid * 10 + 2, "Haven", 8, 6, 2)]:
            common = dict(year=year, Tournament="T", Stage="S", **{"Match Type": "Final",
                          "Match Name": f"Red vs Blue {mid}"}, Map=map_name)
            ids.append({**common, "Match ID": mid, "Game ID": game})
            for team in ("Red", "Blue"):
                eco.extend([{**common, "Team": team, "Type": "$$$ (won)",
                             "Initiated": full, "Won": win},
                            {**common, "Team": team, "Type": "Pistol Won",
                             "Initiated": None, "Won": pistol}])
    return pd.DataFrame(eco), pd.DataFrame(ids)


def test_duplicate_round_weighting_pistol_denominator_and_asof_isolation():
    e, ids = raw()
    # One literal repeat of a map row must not add its rounds.
    summary = e.iloc[[0]].copy()
    summary.loc[:, "Map"] = "All Maps"
    summary.loc[:, "Won"] = 99
    e = pd.concat([e, e.iloc[[0]], summary], ignore_index=True)
    economy, failures = build_economy(matches(), e, ids)
    assert failures.empty
    row = economy.loc[economy.match_id.eq(10) & economy.team_name.eq("Red")].iloc[0]
    assert row.full_buy_win_pct == 7 / 10
    assert row.pistol_win_pct == 3 / 4
    features, replay_failures = replay(matches(), economy)
    assert replay_failures.empty
    assert features.loc[0, "prior_economy_rows_a"] == 0
    assert pd.isna(features.loc[0, "full_buy_win_pct_a"])
    assert features.loc[1, "full_buy_win_pct_a"] == 7 / 10
    assert features.loc[1, "pistol_win_pct_b"] == 3 / 4
    assert features.loc[3, "prior_economy_rows_a"] == 3
    assert features.loc[3, "prior_economy_rows_b"] == 3
    c = coverage(matches(), features, failures)
    assert c.loc[c.year.eq(2025), "both_sides_3_prior_series"].item() == 1
    assert c.loc[c.year.eq(2024), "both_sides_3_prior_series"].item() == 0
    shorter, _ = replay(matches().iloc[:3], economy.loc[economy.match_id.lt(40)])
    pd.testing.assert_frame_equal(features.iloc[:3].reset_index(drop=True), shorter.reset_index(drop=True))


def test_failed_series_and_team_names_are_reported():
    e, ids = raw()
    no_bridge = e.iloc[[0]].copy()
    no_bridge.loc[:, "Match Name"] = "Unknown series"
    unknown_team = e.iloc[[0]].copy()
    unknown_team.loc[:, "Team"] = "Unknown team"
    economy, failures = build_economy(matches(), pd.concat([e, no_bridge, unknown_team]), ids)
    assert len(economy) == 10
    assert set(failures.reason) == {"no_id_bridge", "team_name_mismatch"}
    assert failures.loc[failures.reason.eq("team_name_mismatch"), "team_name"].tolist() == ["Unknown team"]
    features, _ = replay(matches(), economy)
    c = coverage(matches(), features, failures)
    assert c.loc[c.year.eq(2023), "failed_series"].item() == 1
    assert c.loc[c.year.eq(2023), "failed_team_names"].item() == 1


def test_zero_full_buy_initiated_has_no_rate():
    e, ids = raw()
    mask = e["Match Name"].eq("Red vs Blue 10") & e.Team.eq("Red") & e.Type.eq("$$$ (won)")
    e.loc[mask, "Initiated"] = 0
    e.loc[mask, "Won"] = 0
    economy, failures = build_economy(matches(), e, ids)
    assert failures.empty
    row = economy.loc[economy.match_id.eq(10) & economy.team_name.eq("Red")].iloc[0]
    assert pd.isna(row.full_buy_win_pct)
    assert row.pistol_win_pct == 3 / 4
