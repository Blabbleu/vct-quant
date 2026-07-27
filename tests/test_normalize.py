import pandas as pd

from vct_quant.etl.normalize import _duration_seconds, _pct, _unambiguous


def test_pct_strips_sign_and_rejects_out_of_range():
    out = _pct(pd.Series(["81%", " 26 %", "0%", "100%", "150%", None, "n/a"]))
    assert list(out[:4]) == [81.0, 26.0, 0.0, 100.0]
    # The schema CHECKs 0-100, so anything outside becomes NULL rather than
    # failing the insert.
    assert out[4:].isna().all()


def test_duration_handles_both_clock_formats():
    out = _duration_seconds(pd.Series(["1:02:40", "46:45", "", None, "abc"]))
    assert out[0] == 3760  # 1h 2m 40s
    assert out[1] == 2805  # 46m 45s
    assert out[2:].isna().all()


def test_unambiguous_drops_names_with_two_ids():
    # "Reused" carries two distinct vlr.gg IDs, so resolving it either way would
    # merge two different entities' histories.
    df = pd.DataFrame({
        "Team": ["Solo", "Reused", "Reused", "NoId", "Dupe", "Dupe"],
        "Team ID": [10.0, 20.0, 21.0, None, 30.0, 30.0],
    })
    out = _unambiguous(df, "Team", "Team ID")
    assert out == {"Solo": 10, "Dupe": 30}
    assert "Reused" not in out and "NoId" not in out


def test_unambiguous_ignores_nonpositive_ids():
    df = pd.DataFrame({"Player": ["a", "b"], "Player ID": [0.0, 5.0]})
    assert _unambiguous(df, "Player", "Player ID") == {"b": 5}
