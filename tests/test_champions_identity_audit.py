"""Direct source-page IDs must corroborate bracket entrants, not just names."""
import pytest

from scripts.champions_identity_audit import fetch_match_page, parse_match_page, verify_openers


def page(match_id=753444, event_id=2766, teams=((120, "100 Thieves"), (14, "T1"))):
    return f'''<link rel="canonical" href="https://www.vlr.gg/{match_id}/opener">
    <a href="/event/{event_id}/event/group-stage" class="match-header-event">Champions</a>
    <div class="match-header-vs">
    <a class="match-header-link wf-link-hover mod-1" href="/team/{teams[0][0]}/slug"><div class="wf-title-med">{teams[0][1]}</div></a>
    <a class="match-header-link wf-link-hover mod-2" href="/team/{teams[1][0]}/slug"><div class="wf-title-med mod-single">{teams[1][1]}</div></a>
    </div>
    <a class="match-header-link mod-1" href="/team/999/other">Unrelated</a>'''


def test_parse_direct_match_header_and_ignore_other_links():
    assert parse_match_page(page(), 753444, 2766) == [(120, "100 Thieves"), (14, "T1")]


@pytest.mark.parametrize("html", [
    page(match_id=123), page(event_id=123),
    page(teams=((120, "100 Thieves"), (120, "T1"))),
    page().replace('mod-2" href="/team/14/', 'mod-1" href="/team/14/'),
    page().replace('href="/team/14/slug"', 'href="/team/TBD/slug"'),
    page().replace('class="match-header-event"', 'class="not-an-event"'),
    page().replace('rel="canonical"', 'rel="alternate"'),
])
def test_parse_rejects_unverified_identity(html):
    with pytest.raises(ValueError):
        parse_match_page(html, 753444, 2766)


def test_verify_openers_requires_positional_names_and_ids():
    spec = {"event_id": 2766, "groups": {"A": {
        "opening_1": {"match_id": 753444, "teams": ["100 Thieves", "T1"], "team_ids": [120, 14]},
        "opening_2": {"match_id": 753445, "teams": ["JD Gaming", "FUT Esports"], "team_ids": [13576, 1184]},
    }}}
    second = page(753445, teams=((13576, "JD Gaming"), (1184, "FUT Esports")))
    assert verify_openers(spec, {753444: page(), 753445: second}) == 2
    with pytest.raises(ValueError, match="753444"):
        verify_openers(spec, {753444: page(teams=((14, "T1"), (120, "100 Thieves"))), 753445: second})
    with pytest.raises(ValueError, match="753444"):
        verify_openers(spec, {753444: page(teams=((120, "100 Thieves"), (15, "T1"))), 753445: second})
    with pytest.raises(ValueError, match="missing"):
        verify_openers(spec, {753444: page()})


def test_fetch_match_page_disables_redirects_and_returns_verified_response():
    class Response:
        url = "https://www.vlr.gg/753444/opener"
        status_code = 200
        headers = {"Content-Length": "9"}
        encoding = "utf-8"
        closed = False

        def iter_content(self, chunk_size):
            assert chunk_size == 65536
            yield b"page html"

        def close(self):
            self.closed = True

        def raise_for_status(self):
            pass

    class Session:
        def get(self, url, **kwargs):
            assert url == "https://www.vlr.gg/753444/"
            assert kwargs["allow_redirects"] is False
            assert kwargs["stream"] is True
            return response

    response = Response()
    assert fetch_match_page(Session(), 753444) == "page html"
    assert response.closed


def test_fetch_match_page_rejects_declared_oversize_before_reading():
    class Response:
        url = "https://www.vlr.gg/753444/"
        status_code = 200
        headers = {"Content-Length": "2097153"}

        def iter_content(self, chunk_size):
            raise AssertionError("oversized response must not be read")

        def close(self):
            self.closed = True

        def raise_for_status(self):
            pass

    class Session:
        def get(self, url, **kwargs):
            return response

    response = Response()
    response.closed = False
    with pytest.raises(ValueError, match="too large"):
        fetch_match_page(Session(), 753444)
    assert response.closed


def test_fetch_match_page_rejects_oversize_stream_without_content_length():
    class Response:
        url = "https://www.vlr.gg/753444/"
        status_code = 200
        headers = {}
        closed = False

        def iter_content(self, chunk_size):
            yield b"x" * 65536
            yield b"y" * (2 * 1024 * 1024)
            raise AssertionError("must stop at first oversized chunk")

        def close(self):
            self.closed = True

        def raise_for_status(self):
            pass

    class Session:
        def get(self, url, **kwargs):
            return response

    response = Response()
    with pytest.raises(ValueError, match="too large"):
        fetch_match_page(Session(), 753444)
    assert response.closed


@pytest.mark.parametrize("status_code", [300, 302, 304, 305, 307, 308])
def test_fetch_match_page_rejects_redirect_status(status_code):
    class Response:
        url = "https://attacker.example/"
        text = ""

        def __init__(self):
            self.status_code = status_code

        def close(self):
            pass

        def raise_for_status(self):
            raise AssertionError("redirect should be rejected before status handling")

    class Session:
        def get(self, url, **kwargs):
            assert kwargs["allow_redirects"] is False
            return Response()

    with pytest.raises(ValueError, match="redirect"):
        fetch_match_page(Session(), 753444)
