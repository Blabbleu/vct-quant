import json

from scripts.veto_source_audit import archived_audit, live_audit, parse_full_veto, segment


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

