import numpy as np
import pandas as pd

from vct_quant.features.build import elo_k, margin_signal, predict_upcoming
from vct_quant.features.carryover import carryover_elo, carryover_probability
from vct_quant.features.ratings import compute_elo

P = [f"p{i}" for i in range(15)]


def _history():
    # "old" beats "rival" twice with players p0-p4, then the whole roster
    # reappears as "new" (a rebrand). "t2" is a Tier-2-only team.
    return pd.DataFrame({
        "match_id": [1, 2, 3, 4, 5],
        "tier": [1, 1, 2, 1, 1],
        "team_a": ["old", "old", "t2", "new", "mixed"],
        "team_b": ["rival", "rival", "rival", "rival", "rival"],
        "maps_a": [2, 2, 2, 2, 2],
        "maps_b": [0, 0, 0, 1, 1],
        "score_a": [1.0, 1.0, 1.0, 1.0, 1.0],
    })


def _rosters():
    rival = frozenset(P[5:10])
    return {
        (1, 1): frozenset(P[0:5]), (1, 2): rival,
        (2, 1): frozenset(P[0:5]), (2, 2): rival,
        (3, 1): frozenset(P[10:15]), (3, 2): rival,
        (4, 1): frozenset(P[0:5]), (4, 2): rival,
        # Two of old's players plus three unknowns: below the 3-of-5 bar.
        (5, 1): frozenset(P[0:2] + ["x", "y", "z"]), (5, 2): rival,
    }


def test_without_rosters_it_is_exactly_production_elo():
    h = _history()
    p, _, inherited = carryover_elo(h, {})
    rows, _ = compute_elo(zip(h.match_id, h.team_a, h.team_b, margin_signal(h)), k=elo_k(h.tier))
    t1 = h.tier.eq(1).to_numpy()
    assert np.allclose(p[t1], np.array([r["p_a_win"] for r in rows])[t1])
    assert np.isnan(p[~t1]).all()
    assert inherited == []


def test_rebrand_inherits_the_source_rating_and_partial_overlap_does_not():
    h = _history()
    _, state_off, _ = carryover_elo(h.iloc[:2], {})
    p, _, inherited = carryover_elo(h, _rosters())
    # Match 4: "new" starts where "old" left off, so it is favoured.
    # Match 5: "mixed" shares only 2 players with anyone, so it starts at 1500.
    assert inherited == [(4, "new", "old")]
    assert p[3] > 0.5
    assert state_off.rating["old"] > 1500


def test_en_bloc_rule_blocks_inheriting_from_a_team_that_kept_playing():
    h = pd.DataFrame({
        "match_id": [1, 2, 3], "tier": [1, 1, 1],
        "team_a": ["old", "old", "new"], "team_b": ["rival"] * 3,
        "maps_a": [2, 2, 2], "maps_b": [0, 0, 0], "score_a": [1.0] * 3,
    })
    rival = frozenset(P[5:10])
    rosters = {
        (1, 1): frozenset(P[0:5]), (1, 2): rival,
        # old replaces three players, then the three leavers join "new".
        (2, 1): frozenset(P[0:2] + P[10:13]), (2, 2): rival,
        (3, 1): frozenset(P[2:5] + ["a", "b"]), (3, 2): rival,
    }
    assert carryover_elo(h, rosters)[2] == []
    assert carryover_elo(h, rosters, en_bloc=False)[2] == [(3, "new", "old")]


def test_upcoming_fixture_uses_the_new_teams_latest_lineup():
    # "new" has only played Tier 2 (e.g. an open qualifier) with old's roster.
    h = _history().iloc[:2]
    h = pd.concat([h, pd.DataFrame({
        "match_id": [6], "tier": [2], "team_a": ["new"], "team_b": ["t2"],
        "maps_a": [2], "maps_b": [0], "score_a": [1.0]})], ignore_index=True)
    rosters = {**{k: v for k, v in _rosters().items() if k[0] <= 2},
               (6, 1): frozenset(P[0:5]), (6, 2): frozenset(P[10:15])}
    fixtures = pd.DataFrame({"team_a_key": ["new", "t2"], "team_b_key": ["rival", "rival"]})

    out = carryover_probability(fixtures, h, rosters)

    assert out.p_team_a_win_carryover.iloc[0] > 0.5
    assert out.carryover_from_a.iloc[0] == "old"
    assert pd.isna(out.carryover_from_a.iloc[1])
    assert abs(out.p_team_a_win_carryover.iloc[1] - predict_upcoming(fixtures, h).p_team_a_win.iloc[1]) < 1e-12


def test_predict_upcoming_logs_carryover_equal_to_elo_without_rosters():
    h = _history()
    fixtures = pd.DataFrame({"team_a_key": ["old", "brand_new"], "team_b_key": ["rival", "rival"]})
    out = predict_upcoming(fixtures, h)
    assert np.allclose(out.p_team_a_win_carryover, out.p_team_a_win)


def test_live_prediction_loads_rosters_without_changing_primary(monkeypatch):
    from vct_quant.features import build

    h = _history().iloc[:2]
    h = pd.concat([h, pd.DataFrame({
        "match_id": [6], "tier": [2], "team_a": ["new"], "team_b": ["t2"],
        "maps_a": [2], "maps_b": [0], "score_a": [1.0]})], ignore_index=True)
    rosters = {**{key: value for key, value in _rosters().items() if key[0] <= 2},
               (6, 1): frozenset(P[0:5])}
    monkeypatch.setattr(build, "match_sequence", lambda **kwargs: h)
    monkeypatch.setattr(build, "load_rosters", lambda: rosters)
    fixtures = pd.DataFrame({"team_a_key": ["new"], "team_b_key": ["rival"], "tier": [1]})
    primary = predict_upcoming(fixtures, h)
    live = predict_upcoming(fixtures)
    assert live.p_team_a_win.iloc[0] == primary.p_team_a_win.iloc[0]
    assert live.p_team_a_win_carryover.iloc[0] > live.p_team_a_win.iloc[0]
    assert live.carryover_from_a.iloc[0] == "old"


def test_gc_prediction_excludes_official_carryover(monkeypatch):
    from vct_quant.features import build

    h = _history().iloc[:2].assign(tier=3)
    monkeypatch.setattr(build, "match_sequence", lambda **kwargs: h)
    fixtures = pd.DataFrame({"team_a_key": ["old"], "team_b_key": ["rival"], "tier": [3]})
    out = predict_upcoming(fixtures)
    assert "p_team_a_win_carryover" not in out
