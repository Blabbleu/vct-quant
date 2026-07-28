from vct_quant.ingest import vlrgg


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
