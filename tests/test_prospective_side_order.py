from datetime import datetime, timezone

import pandas as pd

from scripts.prospective_side_order import audit_orientation


def _log(match_id, a, b, at="2026-09-25T08:00:00Z", start="2026-09-26T09:00:00Z", tier=3):
    return dict(match_id=match_id, team_a_key=a, team_b_key=b,
                predicted_at=at, scheduled_at=start, tier=tier)


def _canonical(match_id, a_id, a_name, b_id, b_name, status="completed", day="2026-09-26"):
    return [dict(match_id=match_id, team_number=n, team_id=tid, team_name=name,
                 status=status, completed_at=day)
            for n, (tid, name) in enumerate(((a_id, a_name), (b_id, b_name)), 1)]


def test_strictly_prestart_log_orientation_matches_both_canonical_sides():
    log = pd.DataFrame([_log(1, "name:old a", "22"), _log(2, "33", "44")])
    teams = pd.DataFrame(_canonical(1, 11, "Old A", 22, "B") +
                         _canonical(2, 44, "B", 33, "A"))
    out = audit_orientation(log, teams)
    assert out["by_tier"]["3"] == {"logged_prestart": 2, "changed_prestart_order": 0,
                                  "same": 1, "flipped": 1,
                                  "unmatched": 0, "ambiguous": 0, "pending": 0,
                                  "stale_start": 0}
    assert out["issues"] == [{"match_id": 2, "tier": 3, "orientation": "flipped"}]


def test_never_uses_a_poststart_or_missing_time_snapshot_even_if_result_agrees():
    log = pd.DataFrame([
        _log(1, "11", "22", at="2026-09-26T09:00:00Z"),
        _log(2, "33", "44", at="not a timestamp"),
    ])
    teams = pd.DataFrame(_canonical(1, 11, "A", 22, "B") +
                         _canonical(2, 33, "C", 44, "D"))
    assert audit_orientation(log, teams) == {"by_tier": {}, "issues": []}


def test_picks_latest_prestart_orientation_and_does_not_use_later_log_row():
    log = pd.DataFrame([
        _log(1, "11", "22", at="2026-09-26T07:00:00Z"),
        _log(1, "22", "11", at="2026-09-26T08:00:00Z"),
        _log(1, "11", "22", at="2026-09-26T10:00:00Z"),
    ])
    out = audit_orientation(log, pd.DataFrame(_canonical(1, 11, "A", 22, "B")))
    assert out["by_tier"]["3"]["flipped"] == 1
    assert out["by_tier"]["3"]["logged_prestart"] == 1


def test_ambiguous_names_and_incomplete_canonical_pairs_are_not_claimed_same():
    log = pd.DataFrame([_log(1, "name:a", "name:a"),
                        _log(2, "33", "44"), _log(3, "55", "66")])
    teams = pd.DataFrame(_canonical(1, 11, "A", 22, "A") +
                         _canonical(2, 33, "C", 44, "D")[:1] +
                         _canonical(3, 55, "E", 66, "F", status="scheduled"))
    out = audit_orientation(log, teams)
    assert out["by_tier"]["3"]["ambiguous"] == 2
    assert out["by_tier"]["3"]["pending"] == 1


def test_missing_identity_and_rescheduled_match_are_not_evidence():
    log = pd.DataFrame([_log(1, "11", "22"), _log(2, "33", "44")])
    teams = pd.DataFrame(_canonical(1, 11, "A", 23, "B") +
                         _canonical(2, 33, "C", 44, "D", day="2026-09-24"))
    out = audit_orientation(log, teams)
    assert out["by_tier"]["3"]["unmatched"] == 1
    assert out["by_tier"]["3"]["stale_start"] == 1


def test_prestart_order_reversal_is_flagged_even_if_last_row_matches():
    log = pd.DataFrame([
        _log(1, "22", "11", at="2026-09-26T07:00:00Z"),
        _log(1, "11", "22", at="2026-09-26T08:00:00Z"),
    ])
    out = audit_orientation(log, pd.DataFrame(_canonical(1, 11, "A", 22, "B")))
    assert out["by_tier"]["3"]["changed_prestart_order"] == 1
    assert out["by_tier"]["3"]["same"] == 1
    assert {"match_id": 1, "tier": 3, "orientation": "changed_prestart_order"} in out["issues"]


def test_name_key_upgrade_is_not_mistaken_for_order_reversal():
    log = pd.DataFrame([
        _log(1, "name:old a", "name:b", at="2026-09-26T07:00:00Z"),
        _log(1, "11", "22", at="2026-09-26T08:00:00Z"),
    ])
    out = audit_orientation(log, pd.DataFrame(_canonical(1, 11, "Old A", 22, "B")))
    assert out["by_tier"]["3"]["changed_prestart_order"] == 0
    assert out["by_tier"]["3"]["same"] == 1


def test_pool_counts_stay_separate():
    log = pd.DataFrame([_log(1, "11", "22", tier=1), _log(2, "33", "44", tier=3)])
    teams = pd.DataFrame(_canonical(1, 11, "A", 22, "B") +
                         _canonical(2, 33, "C", 44, "D"))
    out = audit_orientation(log, teams)
    assert out["by_tier"]["1"]["same"] == 1
    assert out["by_tier"]["3"]["same"] == 1
