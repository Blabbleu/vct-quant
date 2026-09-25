import json

import duckdb
import numpy as np
import pandas as pd

from vct_quant import db
from vct_quant.etl import normalize
from vct_quant.features.build import predict_upcoming
from vct_quant.models import shadow


def _history():
    # Team 1 beats 2 repeatedly; team 3 only ever appears in Tier 2 (weight 0).
    return pd.DataFrame({
        "match_id": [1, 2, 3, 4],
        "tier": [1, 1, 1, 2],
        "team_a": ["1", "1", "2", "3"],
        "team_b": ["2", "2", "1", "1"],
        "maps_a": [2, 2, 0, 2],
        "maps_b": [0, 1, 2, 0],
        "score_a": [1.0, 1.0, 0.0, 1.0],
    })


def test_ensemble_is_logit_blend_of_its_components():
    from vct_quant.features.ratings import expected_score

    history = _history()
    fixtures = pd.DataFrame({"team_a_key": ["1"], "team_b_key": ["2"]})
    z = 0.0
    for k, w in shadow.ENSEMBLE:
        ratings = shadow._replay(history, k)
        p = expected_score(ratings["1"], ratings["2"])
        z += w * np.log(p / (1 - p))
    expected = 1 / (1 + np.exp(-z))

    got = shadow.ensemble_probability(fixtures, history).iloc[0]

    assert got > 0.5
    assert abs(got - expected) < 1e-12


def test_ensemble_ignores_tier_two_results():
    history = _history()
    fixtures = pd.DataFrame({"team_a_key": ["3"], "team_b_key": ["new"]})
    # Team 3's only result is Tier 2, which moves no rating: it is still 1500.
    assert abs(shadow.ensemble_probability(fixtures, history).iloc[0] - 0.5) < 1e-12


def test_fit_shrink_recovers_overconfidence():
    rng = np.random.default_rng(0)
    true_p = rng.uniform(0.2, 0.8, 4000)
    y = (rng.uniform(size=true_p.size) < true_p).astype(float)
    z = np.log(true_p / (1 - true_p))
    overconfident = 1 / (1 + np.exp(-2.0 * z))  # needs a = 0.5 to undo

    a = shadow.fit_shrink(y, overconfident)

    assert 0.4 <= a <= 0.6
    assert shadow.fit_shrink(np.array([]), np.array([])) == 1.0


def test_calibration_uses_only_the_trailing_scored_tier_one_window(monkeypatch):
    monkeypatch.setattr(shadow, "CALIBRATION_WINDOW", 2)
    seen = {}
    monkeypatch.setattr(shadow, "fit_shrink", lambda y, p: seen.update(y=list(y), p=list(p)) or 1.0)
    history = pd.DataFrame({
        "tier": [1, 1, 2, 1, 1],
        "score_a": [1.0, 0.0, 1.0, 0.5, 1.0],
    })
    shadow.calibration_a(history, np.array([0.1, 0.2, 0.3, 0.4, 0.5]))
    # Tier-2 row and the Bo2 draw are excluded; the last two scored remain.
    assert seen == {"y": [0.0, 1.0], "p": [0.2, 0.5]}


def test_predict_upcoming_logs_shadows_for_official_pool_only():
    history = _history()
    fixtures = pd.DataFrame({"team_a_key": ["1"], "team_b_key": ["2"]})

    official = predict_upcoming(fixtures, history)
    gc = predict_upcoming(fixtures, history.assign(tier=3))

    assert official.p_team_a_win_ensemble.between(0, 1).all()
    assert official.p_team_a_win_calibrated.between(0, 1).all()
    assert "p_team_a_win_ensemble" not in gc


def test_unresolved_team_targets_pick_latest_unharvested_tier_one_match(tmp_path, monkeypatch):
    monkeypatch.setattr(normalize, "RAW_VLRGG_DIR", tmp_path)
    con = duckdb.connect()
    db.init_db(con)
    con.execute("INSERT INTO event (event_id, name, tier) VALUES (1, 'VCT', 1), (2, 'Challengers', 2)")
    rows = [
        # (match_id, event_id, team_number, team_id, team_name)
        (10, 1, 1, None, "NRG"), (10, 1, 2, 5, "G2 Esports"),
        (11, 1, 1, None, "NRG"), (11, 1, 2, 5, "G2 Esports"),        # NRG's latest -> 11
        (12, 1, 1, None, "ENVY"), (12, 1, 2, 5, "G2 Esports"),       # already harvested
        (13, 1, 1, None, "TBD"), (13, 1, 2, None, "TBD"),            # placeholder
        (14, 2, 1, None, "Some T2 Team"), (14, 2, 2, 5, "G2 Esports"),  # Tier 2: skipped
    ]
    for match_id, event_id in {(r[0], r[1]) for r in rows}:
        con.execute(f"INSERT INTO match (match_id, event_id, status) VALUES ({match_id}, {event_id}, 'completed')")
    con.execute("INSERT INTO team (team_id, name) VALUES (5, 'G2 Esports')")
    for match_id, _, number, team_id, name in rows:
        con.execute("INSERT INTO match_team (match_id, team_number, team_id, team_name) VALUES (?, ?, ?, ?)",
                    [match_id, number, team_id, name])
    (tmp_path / "match_details_12_20260924T000000Z.json").write_text(json.dumps({"data": {
        "match_id": "12", "teams": [], "maps": [],
    }}))
    (tmp_path / "match_details_11_20260924T000000Z.json").write_text(json.dumps({
        "status": "error", "data": {"segments": None},
    }))

    import pytest
    with pytest.warns(UserWarning, match="match_details_11_"):
        assert normalize.unresolved_team_detail_targets(con) == [11]
