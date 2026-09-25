import json

import pytest

from vct_quant.ingest import vlrgg
from vct_quant.etl import normalize


def test_save_raw_preserves_same_second_retries_and_detail_replay(tmp_path, monkeypatch):
    """A poisoned response must not replace the last valid archived detail."""
    class Clock:
        @staticmethod
        def now(tz):
            from datetime import datetime, timezone
            return datetime(2026, 9, 25, 7, 30, tzinfo=timezone.utc)

    monkeypatch.setattr(vlrgg, "datetime", Clock)
    monkeypatch.setattr(vlrgg, "RAW_VLRGG_DIR", tmp_path)
    monkeypatch.setattr(normalize, "RAW_VLRGG_DIR", tmp_path)
    good = {"status": "success", "data": {"status": 200, "segments": [
        {"match_id": "44", "teams": [], "maps": []}
    ]}}
    poison = {"status": "error", "data": {"status": 503, "segments": None}}
    first = vlrgg.save_raw(good, "match_details_44")
    second = vlrgg.save_raw(poison, "match_details_44")
    assert first != second
    assert json.loads(first.read_text()) == good
    assert json.loads(second.read_text()) == poison
    with pytest.warns(UserWarning, match="Skipping invalid archived detail"):
        assert normalize._vlrgg_match_details() == good["data"]["segments"]


def test_save_raw_three_same_second_snapshots_sort_in_fetch_order(tmp_path, monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            from datetime import datetime, timezone
            return datetime(2026, 9, 25, 7, 30, tzinfo=timezone.utc)

    monkeypatch.setattr(vlrgg, "datetime", Clock)
    monkeypatch.setattr(vlrgg, "RAW_VLRGG_DIR", tmp_path)
    paths = [vlrgg.save_raw({"n": n}, "events_page001") for n in range(3)]
    assert paths == sorted(paths)
    assert [json.loads(p.read_text())["n"] for p in paths] == list(range(3))


def test_get_respects_retry_after(monkeypatch):
    class Response:
        def __init__(self, status, headers=None):
            self.status_code = status
            self.headers = headers or {}

        def raise_for_status(self):
            assert self.status_code == 200

        def json(self):
            return {"status": "success"}

    responses = iter([Response(429, {"Retry-After": "2"}), Response(200)])
    sleeps = []
    monkeypatch.setattr(vlrgg._session, "get", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(vlrgg.time, "sleep", sleeps.append)

    assert vlrgg._get("/test") == {"status": "success"}
    assert sleeps == [3.0, vlrgg.REQUEST_DELAY_S]


@pytest.mark.parametrize("fetch,args", [
    ("fetch_events", (1,)),
    ("fetch_match_results", ()),
    ("fetch_upcoming_matches", ()),
    ("fetch_event_matches", (2766,)),
])
@pytest.mark.parametrize("bad", [
    {"status": "error", "data": {"segments": []}},
    {"status": "success", "data": {"status": 503, "segments": []}},
    {"status": "success", "data": {"status": 200}},
    {"status": "success", "data": {"status": 200, "segments": {}}},
    {"status": "success", "data": {"status": 200, "segments": [None]}},
])
def test_ingest_rejects_http_200_error_payload_after_archiving(monkeypatch, fetch, args, bad):
    saved = []
    monkeypatch.setattr(vlrgg, "_get", lambda *a, **kw: bad)
    monkeypatch.setattr(vlrgg, "save_raw", lambda payload, name: saved.append((payload, name)))
    with pytest.raises(ValueError, match="invalid .* feed"):
        getattr(vlrgg, fetch)(*args)
    assert saved and saved[0][0] is bad


@pytest.mark.parametrize("fetch,args", [
    ("fetch_events", (1,)),
    ("fetch_match_results", ()),
    ("fetch_upcoming_matches", ()),
    ("fetch_event_matches", (2766,)),
])
def test_ingest_accepts_valid_empty_feed(monkeypatch, fetch, args):
    payload = {"status": "success", "data": {"status": 200, "segments": []}}
    monkeypatch.setattr(vlrgg, "_get", lambda *a, **kw: payload)
    assert getattr(vlrgg, fetch)(*args, save=False) is payload


@pytest.mark.parametrize("bad", [
    {"status": "error", "data": {"segments": []}},
    {"status": "success", "data": {"status": 503, "segments": []}},
    {"status": "success", "data": {"status": 200, "segments": None}},
    {"status": "success", "data": {"status": 200, "segments": [{"match_id": "45"}]}},
    {"status": "success", "data": {"status": 200, "segments": [{"match_id": "44"}]}},
])
def test_detail_rejects_http_200_poison_after_archiving(monkeypatch, bad):
    saved = []
    monkeypatch.setattr(vlrgg, "_get", lambda *a, **kw: bad)
    monkeypatch.setattr(vlrgg, "save_raw", lambda payload, name: saved.append((payload, name)))
    with pytest.raises(ValueError, match="invalid match_details_44 feed"):
        vlrgg.fetch_match_details(44)
    assert saved == [(bad, "match_details_44")]


@pytest.mark.parametrize("detail", [
    {"match_id": "44", "teams": [None], "maps": []},
    {"match_id": "44", "teams": [], "maps": [None]},
    {"match_id": "44", "teams": [], "maps": [{"score": None}]},
    {"match_id": "44", "teams": [], "maps": [{"players": {"team1": [None]}}]},
    {"match_id": "44", "teams": [], "maps": [{"players": {"team1": None}}]},
])
def test_detail_rejects_nested_poison_before_loading(monkeypatch, detail):
    payload = {"status": "success", "data": {"status": 200, "segments": [detail]}}
    saved = []
    monkeypatch.setattr(vlrgg, "_get", lambda *a, **kw: payload)
    monkeypatch.setattr(vlrgg, "save_raw", lambda data, name: saved.append(data))
    with pytest.raises(ValueError, match="invalid match_details_44 feed"):
        vlrgg.fetch_match_details(44)
    assert saved == [payload]


@pytest.mark.parametrize("fetch,args,segment", [
    ("fetch_events", (1,), {"event_id": "12"}),
    ("fetch_event_matches", (12,), {"match_id": "44", "status": "Completed", "team1": None, "team2": {"name": "B", "score": "0"}, "date": "Fri, September 25, 2026", "event_series": "Final"}),
    ("fetch_upcoming_matches", (), {"match_event": "Valorant Champions 2026"}),
])
def test_ingest_rejects_structurally_incomplete_rows_after_archiving(monkeypatch, fetch, args, segment):
    payload = {"status": "success", "data": {"status": 200, "segments": [segment]}}
    saved = []
    monkeypatch.setattr(vlrgg, "_get", lambda *a, **kw: payload)
    monkeypatch.setattr(vlrgg, "save_raw", lambda data, name: saved.append(data))
    with pytest.raises(ValueError, match="invalid .* feed"):
        getattr(vlrgg, fetch)(*args)
    assert saved == [payload]


@pytest.mark.parametrize("change", [
    {"match_page": "not-a-match"},
    {"match_page": "0/invalid"},
    {"match_page": None},
    {"team1": None},
    {"team2": {"name": "B"}},
    {"match_series": None},
    {"unix_timestamp": None},
])
def test_upcoming_rejects_unusable_rows_before_forecasting(monkeypatch, change):
    row = {"match_event": "Valorant Champions 2026", "unix_timestamp": "TBD",
           "match_page": "44/fixture", "match_series": "Upper Final",
           "team1": "A", "team2": "B", "time_until_match": "TBD"}
    row.update(change)
    payload = {"status": "success", "data": {"status": 200, "segments": [row]}}
    saved = []
    monkeypatch.setattr(vlrgg, "_get", lambda *a, **kw: payload)
    monkeypatch.setattr(vlrgg, "save_raw", lambda data, name: saved.append(data))
    with pytest.raises(ValueError, match="invalid match_upcoming feed"):
        vlrgg.fetch_upcoming_matches()
    assert saved == [payload]


def test_upcoming_rejects_duplicate_match_ids_before_forecasting(monkeypatch):
    row = {"match_event": "Valorant Champions 2026", "unix_timestamp": "2026-09-25 09:00:00",
           "match_page": "44/fixture", "match_series": "Upper Final", "team1": "A",
           "team2": "B", "time_until_match": "1h"}
    payload = {"status": "success", "data": {"status": 200, "segments": [row, {**row, "match_page": "44/other-slug"}]}}
    monkeypatch.setattr(vlrgg, "_get", lambda *a, **kw: payload)
    with pytest.raises(ValueError, match="invalid match_upcoming feed"):
        vlrgg.fetch_upcoming_matches(save=False)


@pytest.mark.parametrize("fetch,args,row,id_field", [
    ("fetch_events", (1,), {"event_id": "12", "title": "VCT 2026: Champions",
     "status": "upcoming", "region": "International", "dates": "Sep 1—30",
     "prize": "", "thumb": "", "url_path": "/event/12"}, "event_id"),
    ("fetch_event_matches", (12,), {"match_id": "44", "date": "Fri, September 25, 2026",
     "status": "Completed", "event_series": "Final",
     "team1": {"name": "A", "score": "2"},
     "team2": {"name": "B", "score": "1"}}, "match_id"),
])
def test_event_feeds_reject_zero_and_duplicate_ids_before_replay(monkeypatch, fetch, args, row, id_field):
    saved = []
    monkeypatch.setattr(vlrgg, "save_raw", lambda payload, name: saved.append(payload))
    for rows in ([{**row, id_field: "0"}],
                 [row, {**row, id_field: row[id_field]}]):
        payload = {"status": "success", "data": {"status": 200, "segments": rows}}
        monkeypatch.setattr(vlrgg, "_get", lambda *a, **kw: payload)
        with pytest.raises(ValueError, match="invalid .* feed"):
            getattr(vlrgg, fetch)(*args)
        assert saved[-1] is payload


def test_detail_accepts_valid_v2_payload(monkeypatch):
    payload = {"status": "success", "data": {"status": 200, "segments": [
        {"match_id": "44", "teams": [], "maps": []}
    ]}}
    monkeypatch.setattr(vlrgg, "_get", lambda *a, **kw: payload)
    assert vlrgg.fetch_match_details(44, save=False) is payload
