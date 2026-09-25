import json
import sys
from datetime import datetime, timedelta, timezone

import pytest
import requests

from scripts.veto_source_audit import archived_audit, live_audit, main, parse_full_veto, segment


BO3 = ("A ban Breeze; B ban Lotus; A pick Haven; B pick Ascent; "
       "A ban Sunset; B ban Split; Summit remains")
BO5 = ("NRG ban Split; LOUD ban Ascent; NRG pick Abyss; LOUD pick Sunset; "
       "NRG pick Summit; LOUD pick Haven; Lotus remains")


def test_parse_full_veto_bo3_bo5():
    assert parse_full_veto(BO3) == {"best_of": 3, "picks": ["Haven", "Ascent"], "decider": "Summit"}
    assert parse_full_veto(BO5) == {"best_of": 5, "picks": ["Abyss", "Sunset", "Summit", "Haven"], "decider": "Lotus"}


def test_parse_full_veto_rejects_incomplete_and_duplicate_maps():
    assert parse_full_veto("") is None
    assert parse_full_veto("VOD Unavaliable") is None
    assert parse_full_veto(BO3.replace("Summit remains", "Haven remains")) is None
    assert parse_full_veto(BO3.replace("; Summit remains", "")) is None
    assert parse_full_veto(BO3.replace("A pick Haven", "A pick ")) is None


def test_archived_audit_counts_final_and_unusable_veto_separately(tmp_path):
    payloads = [
        {"data": {"segments": [{"status": "final", "map_vetos": BO3}]}},
        {"data": {"segments": [{"status": "final", "map_vetos": "VOD Unavaliable"}]}},
        {"data": {"segments": [{"status": "3h 00m", "map_vetos": ""}]}},
    ]
    for i, payload in enumerate(payloads):
        (tmp_path / f"match_details_{i}_20260925T050000Z.json").write_text(json.dumps(payload))
    counts = archived_audit(tmp_path)
    assert counts == {"detail_snapshots": 3, "final": 2, "nonempty_veto": 2,
                      "full_veto": 1, "incomplete_or_placeholder": 1}
    assert segment({"data": {"segments": []}}) is None


def test_live_audit_counts_empty_full_and_api_errors_separately(monkeypatch):
    class Response:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    class Session:
        def get(self, url, *, params, timeout):
            if params == {"q": "upcoming"}:
                return Response({"data": {"segments": [
                    {"match_page": f"{i}/fixture", "unix_timestamp": "2099-01-01 00:00:00"}
                    for i in range(3)
                ]}})
            details = [
                {"data": {"segments": [{"status": "scheduled", "map_vetos": "",
                                        "maps": [{"map_name": "TBD"}]}]}},
                {"data": {"segments": [{"status": "scheduled", "map_vetos": BO3,
                                        "maps": []}]}},
                {"data": {"segments": []}},
            ]
            return Response(details[int(params["match_id"])])

    monkeypatch.setattr("scripts.veto_source_audit.requests.Session", Session)
    counts, lines = live_audit("http://example.test", 3)
    assert counts == {"prestart_attempts": 3, "successful_prestart": 2,
                      "full_prestart_veto": 1, "empty_prestart_veto": 1,
                      "partial_or_other_prestart_veto": 0, "api_errors": 1}
    assert len(lines) == 3
    assert "full_veto=True" in lines[1]


def test_live_audit_reports_unavailable_feed_without_claiming_zero_vetos(monkeypatch):
    class Session:
        def get(self, url, *, params, timeout):
            raise requests.HTTPError("503 Service Unavailable")

    monkeypatch.setattr("scripts.veto_source_audit.requests.Session", Session)
    counts, lines = live_audit("http://example.test", 8)
    assert counts == {"feed_api_errors": 1}
    assert "unavailable" in lines[0].lower()
    assert "503" in lines[0]


def test_live_cli_exits_nonzero_when_feed_unavailable(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("scripts.veto_source_audit.RAW_VLRGG_DIR", tmp_path)
    monkeypatch.setattr("scripts.veto_source_audit.live_audit", lambda base, limit, within_hours=None: (
        {"feed_api_errors": 1}, ["Upcoming feed unavailable: 503"]
    ))
    monkeypatch.setattr(sys, "argv", ["veto_source_audit.py", "--live"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert "feed_api_errors" in capsys.readouterr().out


def test_live_audit_near_start_window_filters_and_orders_before_limiting(monkeypatch):
    now = datetime.now(timezone.utc)
    starts = [now + timedelta(hours=2), now + timedelta(minutes=30), now + timedelta(minutes=10)]
    class Response:
        def __init__(self, data):
            self.data = data
        def raise_for_status(self):
            pass
        def json(self):
            return self.data
    class Session:
        def get(self, url, *, params, timeout):
            if params == {"q": "upcoming"}:
                return Response({"data": {"segments": [
                    {"match_page": f"{i}/fixture", "unix_timestamp": when.strftime("%Y-%m-%d %H:%M:%S")}
                    for i, when in enumerate(starts)
                ]}})
            return Response({"data": {"segments": [{"status": "scheduled", "map_vetos": "", "maps": []}]}})
    monkeypatch.setattr("scripts.veto_source_audit.requests.Session", Session)
    counts, lines = live_audit("http://example.test", 2, within_hours=1)
    assert counts["successful_prestart"] == 2
    assert counts["outside_window"] == 1
    assert counts["window_eligible"] == 2
    assert [line.split(":", 1)[0] for line in lines] == ["2", "1"]

