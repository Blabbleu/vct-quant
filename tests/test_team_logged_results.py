"""A team page lists its own finished logged fixtures, oriented to that team."""
import math

import pytest

from vct_quant.results_list import team_logged_results


def result_row(match_id, a_id, b_id, p_a, winner="a", status="verified", tier=1,
               maps=(2, 1), scheduled="2026-09-24T12:00:00+00:00", market=None):
    ok = status == "verified"
    loss = None
    if ok:
        loss = -math.log(p_a if winner == "a" else 1 - p_a)
    return {
        "match_id": match_id, "tier": tier, "event": "Champions", "series": "Group C",
        "best_of": 3, "scheduled_at": scheduled, "forecast_at": "2026-09-24T10:00:00+00:00",
        "team_a": f"T{a_id}", "team_b": f"T{b_id}", "team_a_key": str(a_id), "team_b_key": str(b_id),
        "team_a_id": a_id, "team_b_id": b_id, "p_a": p_a, "market_a": market,
        "url": f"https://www.vlr.gg/{match_id}",
        "result": {"status": status, "reason": None if ok else "pairing mismatch",
                   "winner": winner if ok else None,
                   "maps_a": maps[0] if ok else None, "maps_b": maps[1] if ok else None},
        "log_loss": loss, "favourite_won": None if not ok else (p_a > .5) == (winner == "a"),
    }


def test_orients_to_the_team_on_either_side():
    rows = [result_row(1, 42, 9, .7, winner="a", maps=(2, 0)),
            result_row(2, 8, 42, .6, winner="a", maps=(2, 1), market=.55)]
    out = team_logged_results(rows, 42)
    by_id = {r["match_id"]: r for r in out["rows"]}
    assert by_id[1]["p_win"] == pytest.approx(.7)
    assert by_id[1]["won"] is True and (by_id[1]["maps_for"], by_id[1]["maps_against"]) == (2, 0)
    assert by_id[1]["opponent"] == "T9" and by_id[1]["opponent_id"] == 9
    assert by_id[2]["p_win"] == pytest.approx(.4)
    assert by_id[2]["market_win"] == pytest.approx(.45)
    assert by_id[2]["won"] is False and (by_id[2]["maps_for"], by_id[2]["maps_against"]) == (1, 2)
    assert by_id[2]["log_loss"] == pytest.approx(-math.log(.6))


def test_only_exact_numeric_id_and_tier1():
    rows = [result_row(1, 42, 9, .7),
            result_row(3, 420, 9, .7),     # different ID sharing a prefix
            result_row(4, 42, 9, .7, tier=3),  # Game Changers pool is separate
            {**result_row(5, 42, 9, .7), "team_a_id": None}]  # unresolved name key
    out = team_logged_results(rows, 42)
    assert [r["match_id"] for r in out["rows"]] == [1]


def test_unverified_rows_listed_but_unscored():
    rows = [result_row(1, 42, 9, .7, status="unverified")]
    out = team_logged_results(rows, 42)
    row = out["rows"][0]
    assert row["status"] == "unverified" and row["reason"] == "pairing mismatch"
    assert row["won"] is None and row["maps_for"] is None and row["log_loss"] is None
    assert out["summary"] == {"verified": 0, "unverified": 1, "wins": 0, "model_calls": 0,
                              "model_had_team_favoured": 0, "model_right": 0, "log_loss": None}


def test_summary_counts_model_calls_from_team_side():
    rows = [result_row(1, 42, 9, .7, winner="a"),    # favoured, won -> right
            result_row(2, 8, 42, .7, winner="a"),    # underdog (0.3), lost -> right
            result_row(3, 42, 7, .6, winner="b"),    # favoured, lost -> wrong
            result_row(4, 42, 6, .5, winner="a")]    # coin flip: no call
    out = team_logged_results(rows, 42)
    s = out["summary"]
    assert s["verified"] == 4 and s["wins"] == 2
    assert s["model_calls"] == 3
    assert s["model_had_team_favoured"] == 2
    assert s["model_right"] == 2
    expected = (-math.log(.7) - math.log(.7) - math.log(.4) - math.log(.5)) / 4
    assert s["log_loss"] == pytest.approx(expected)


def test_keeps_input_order_newest_first_and_limit():
    rows = [result_row(i, 42, 9, .6, scheduled=f"2026-09-{10 + i:02d}T12:00:00+00:00")
            for i in range(1, 6)]
    rows.sort(key=lambda r: r["scheduled_at"], reverse=True)
    out = team_logged_results(rows, 42, limit=3)
    assert [r["match_id"] for r in out["rows"]] == [5, 4, 3]
    assert out["summary"]["verified"] == 5


def test_empty():
    out = team_logged_results([], 42)
    assert out["rows"] == [] and out["summary"]["verified"] == 0
