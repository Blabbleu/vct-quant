"""Direct source-page IDs must corroborate bracket entrants, not just names."""
import pytest

from scripts.champions_identity_audit import parse_match_page, verify_openers


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
