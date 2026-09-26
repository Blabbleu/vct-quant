"""Finished logged fixtures list: last pre-start forecast beside a verified result."""
import math

import pandas as pd
import pytest

from vct_quant.results_list import finished_results


def row(match_id, predicted, scheduled="2026-09-24T12:00Z", a="10", b="20", p=0.6,
        market=None, spread=None, volume=None, tier=1, a_name="Alpha", b_name="Bravo"):
    return {"match_id": match_id, "predicted_at": pd.Timestamp(predicted, tz="UTC") if "Z" not in predicted
            else pd.Timestamp(predicted), "scheduled_at": pd.Timestamp(scheduled),
            "tier": tier, "event_name": "Valorant Champions 2026", "event_series": "Group A",
            "best_of": 3, "team_a_key": a, "team_b_key": b, "team_a_name": a_name,
            "team_b_name": b_name, "vlr_url": f"https://www.vlr.gg/{match_id}/x",
            "p_team_a_win": p, "p_market_a": market, "market_spread": spread,
            "market_volume": volume, "market_slug": pd.NA if market is None else "slug"}


def verified(winner="a", maps_a=2, maps_b=1, completed="2026-09-24"):
    return {"status": "verified", "reason": None, "winner": winner, "maps_a": maps_a,
            "maps_b": maps_b, "maps": [], "maps_complete": False, "pre_start_winner_p": None,
            "completed_on": completed, "source_url": "u", "as_of": None}


def fake_loader(results):
    calls = []

    def load(match_id, a, b, p):
        calls.append((match_id, a, b, p))
        return results.get(match_id)
    load.calls = calls
    return load


def test_uses_last_pre_start_forecast_and_skips_unfinished():
    log = pd.DataFrame([
        row(1, "2026-09-24T09:00Z", p=0.55),
        row(1, "2026-09-24T11:00Z", p=0.62),
        row(1, "2026-09-24T13:00Z", p=0.99),   # after start: never the graded forecast
        row(2, "2026-09-24T09:00Z"),           # not finished: loader returns None
    ])
    load = fake_loader({1: verified()})
    out = finished_results(log, load)
    assert [r["match_id"] for r in out["rows"]] == [1]
    first = out["rows"][0]
    assert first["p_a"] == pytest.approx(0.62)
    assert first["forecast_at"].startswith("2026-09-24T11:00")
    assert (1, "10", "20", pytest.approx(0.62)) in load.calls
    assert first["log_loss"] == pytest.approx(-math.log(0.62))
    assert first["favourite_won"] is True
    assert out["verified"] == 1 and out["unverified"] == 0


def test_match_logged_only_after_start_is_excluded():
    log = pd.DataFrame([row(3, "2026-09-24T13:00Z")])
    load = fake_loader({3: verified()})
    assert finished_results(log, load)["rows"] == []
    assert load.calls == []


def test_unverified_result_carries_no_score_or_loss():
    log = pd.DataFrame([row(4, "2026-09-24T09:00Z")])
    bad = {**verified(), "status": "unverified", "reason": "teams do not match the forecast pairing",
           "winner": None, "maps_a": None, "maps_b": None}
    out = finished_results(log, fake_loader({4: bad}))
    r = out["rows"][0]
    assert r["result"]["status"] == "unverified" and r["log_loss"] is None
    assert r["favourite_won"] is None
    assert out["verified"] == 0 and out["unverified"] == 1


def test_loss_and_favourite_are_scored_for_side_b_winner():
    log = pd.DataFrame([row(5, "2026-09-24T09:00Z", p=0.7)])
    r = finished_results(log, fake_loader({5: verified("b", 0, 2)}))["rows"][0]
    assert r["log_loss"] == pytest.approx(-math.log(0.3))
    assert r["favourite_won"] is False


def test_coin_flip_has_no_favourite():
    log = pd.DataFrame([row(6, "2026-09-24T09:00Z", p=0.5)])
    r = finished_results(log, fake_loader({6: verified()}))["rows"][0]
    assert r["favourite_won"] is None


def test_market_shown_only_when_liquid_on_the_same_row():
    log = pd.DataFrame([
        row(7, "2026-09-24T09:00Z", market=0.4, spread=0.04, volume=5000),
        row(8, "2026-09-24T09:00Z", market=0.4, spread=0.15, volume=5000),
        row(9, "2026-09-24T09:00Z", market=0.4, spread=0.04, volume=10),
    ])
    out = finished_results(log, fake_loader({7: verified(), 8: verified(), 9: verified()}))
    market = {r["match_id"]: r["market_a"] for r in out["rows"]}
    assert market == {7: pytest.approx(0.4), 8: None, 9: None}


def test_latest_orientation_wins_and_rows_sort_newest_first():
    log = pd.DataFrame([
        row(10, "2026-09-20T09:00Z", scheduled="2026-09-20T12:00Z"),
        row(11, "2026-09-22T08:00Z", scheduled="2026-09-22T12:00Z", a="20", b="10", p=0.3),
        row(11, "2026-09-22T09:00Z", scheduled="2026-09-22T12:00Z", a="10", b="20", p=0.7),
    ])
    out = finished_results(log, fake_loader({10: verified(completed="2026-09-20"),
                                             11: verified(completed="2026-09-22")}))
    assert [r["match_id"] for r in out["rows"]] == [11, 10]
    assert out["rows"][0]["team_a_key"] == "10" and out["rows"][0]["p_a"] == pytest.approx(0.7)


def test_tier_is_labelled_and_game_changers_kept_separate():
    log = pd.DataFrame([row(12, "2026-09-24T09:00Z", tier=3)])
    out = finished_results(log, fake_loader({12: verified()}))
    assert out["rows"][0]["tier"] == 3
    assert out["by_tier"] == {"3": {"verified": 1, "favourite_won": 1, "log_loss": pytest.approx(-math.log(0.6))}}


def test_empty_log():
    out = finished_results(pd.DataFrame(), fake_loader({}))
    assert out["rows"] == [] and out["verified"] == 0 and out["by_tier"] == {}
