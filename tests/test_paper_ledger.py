"""Paper entries are immutable, source-comparable pre-start observations."""
import pandas as pd

from vct_quant.paper_ledger import paper_ledger


def quote(match_id=10, hour=1, **kwargs):
    row = dict(match_id=match_id, predicted_at=f"2026-09-20T0{hour}:00Z",
               scheduled_at="2026-09-20T09:00Z", tier=1,
               team_a_id=1, team_b_id=2, team_a_name="A", team_b_name="B",
               team_a_key="1", team_b_key="2", p_team_a_win=.7,
               p_market_a=.5, market_spread=.04, market_volume=2000,
               market_slug="contract")
    return row | kwargs


def result(match_id=10, **kwargs):
    row = dict(match_id=match_id, completed_at="2026-09-20T12:00Z", tier=1,
               team_a_id=1, team_b_id=2, team_a_name="A", team_b_name="B",
               maps_a=2, maps_b=1, won_a=True, won_b=False)
    return row | kwargs


def test_first_eligible_quote_freezes_one_entry_and_uses_worse_side_ask():
    log = pd.DataFrame([quote(), quote(hour=2, p_team_a_win=.8, p_market_a=.55)])
    data = paper_ledger(log, pd.DataFrame([result()]))
    assert data["n"] == 1
    row = data["rows"][0]
    assert row["side"] == "A" and row["entry_at"] == "2026-09-20T01:00:00+00:00"
    assert row["entry_price"] == .52
    assert row["return_per_unit"] == 1 / .52 - 1
    assert row["last_sampled_market"] == .55
    assert row["sampled_clv"] == .05


def test_nullable_market_slug_and_volume_fail_closed():
    log = pd.DataFrame([quote(match_id=10, market_slug=pd.NA),
                        quote(match_id=11, market_volume=pd.NA),
                        quote(match_id=12)])
    log["market_slug"] = log.market_slug.astype("string")
    log["team_a_id"] = log.team_a_id.astype("Int64")
    log["team_b_id"] = log.team_b_id.astype("Int64")
    assert [r["match_id"] for r in paper_ledger(log, pd.DataFrame())["rows"]] == [12]


def test_clv_ignores_thin_late_sample():
    log = pd.DataFrame([quote(), quote(hour=2, p_market_a=.6, market_volume=10),
                        quote(hour=3, p_market_a=.57, market_spread=.15)])
    assert paper_ledger(log, pd.DataFrame())["rows"][0]["sampled_clv"] is None


def test_clv_never_uses_quote_after_original_kickoff_when_rescheduled():
    log = pd.DataFrame([quote(), quote(hour=9, predicted_at="2026-09-20T10:00Z",
                        scheduled_at="2026-09-20T12:00Z", p_market_a=.6)])
    assert paper_ledger(log, pd.DataFrame())["rows"][0]["sampled_clv"] is None


def test_conflicting_simultaneous_first_quotes_do_not_select_side_arbitrarily():
    log = pd.DataFrame([quote(), quote(p_team_a_win=.3)])
    assert paper_ledger(log, pd.DataFrame())["n"] == 0


def test_result_dated_before_entry_is_unverified():
    data = paper_ledger(pd.DataFrame([quote()]), pd.DataFrame([result(completed_at="2026-09-19T00:00Z")]))
    assert data["rows"][0]["status"] == "unverified"


def test_unknown_result_is_open_not_fictional_profit():
    data = paper_ledger(pd.DataFrame([quote()]), pd.DataFrame())
    assert data["n"] == 1
    assert data["rows"][0]["status"] == "open"
    assert data["rows"][0]["return_per_unit"] is None


def test_ineligible_quotes_never_enter_and_later_crossing_is_eligible():
    rows = [quote(hour=1, market_spread=.12), quote(hour=2, market_volume=100),
            quote(hour=3, p_team_a_win=.55), quote(hour=4, p_team_a_win=.7),
            quote(match_id=11, hour=1, scheduled_at="2026-09-20T00:30Z"),
            quote(match_id=12, hour=1, tier=3)]
    data = paper_ledger(pd.DataFrame(rows), pd.DataFrame())
    assert [r["match_id"] for r in data["rows"]] == [10]
    assert data["rows"][0]["entry_at"] == "2026-09-20T04:00:00+00:00"


def test_opposite_side_and_result_identity_must_match_both_teams():
    log = pd.DataFrame([quote(p_team_a_win=.3, p_market_a=.5)])
    data = paper_ledger(log, pd.DataFrame([result()]))
    assert data["rows"][0]["side"] == "B"
    assert data["rows"][0]["entry_price"] == .52
    assert data["rows"][0]["return_per_unit"] == -1
    bad = paper_ledger(log, pd.DataFrame([result(team_b_id=3)]))
    assert bad["rows"][0]["status"] == "unverified"
    assert bad["rows"][0]["return_per_unit"] is None


def test_no_clv_across_contract_or_orientation_and_ambiguous_result():
    log = pd.DataFrame([quote(), quote(hour=2, market_slug="other"),
                        quote(hour=3, team_a_id=2, team_b_id=1, team_a_key="2", team_b_key="1")])
    data = paper_ledger(log, pd.DataFrame([result(maps_a=None)]))
    row = data["rows"][0]
    assert row["status"] == "unverified"
    assert row["last_sampled_market"] is None
    assert row["sampled_clv"] is None
