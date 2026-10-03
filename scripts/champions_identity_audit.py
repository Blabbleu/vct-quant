"""Read-only direct vlr.gg opener identity audit for pinned Champions entrants.

Run ``python scripts/champions_identity_audit.py``. Unlike a name lookup or an
API proxy response, the match page exposes both positional /team/<ID> links.
Never writes raw snapshots or changes production predictions. A current page
is corroboration, not a time-stamped pre-match archive.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

from vct_quant.event_bracket import load_bracket_spec


class MatchHeader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.divs: list[set[str]] = []
        self.canonical: str | None = None
        self.event_ids: list[int] = []
        self.teams: list[tuple[int, int, str]] = []
        self.current: tuple[int, int] | None = None
        self.title_depth: int | None = None
        self.name: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes: set[str] = set((attributes.get("class") or "").split())
        if tag == "link" and attributes.get("rel") == "canonical":
            if self.canonical is not None:
                raise ValueError("multiple canonical match URLs")
            self.canonical = attributes.get("href")
        if tag == "div":
            self.divs.append(classes)
            if self.current is not None and "wf-title-med" in classes:
                self.title_depth = len(self.divs)
        if tag == "a":
            href = attributes.get("href") or ""
            if "match-header-event" in classes:
                match = re.fullmatch(r"/event/([1-9][0-9]*)(?:/[^?]*)?", href)
                if match is None:
                    raise ValueError("unverified match header event")
                self.event_ids.append(int(match.group(1)))
            if "match-header-link" in classes and any("match-header-vs" in div for div in self.divs):
                sides = classes & {"mod-1", "mod-2"}
                match = re.fullmatch(r"/team/([1-9][0-9]*)(?:/[^?]*)?", href)
                if len(sides) != 1 or match is None or self.current is not None:
                    raise ValueError("invalid team link in match header")
                self.current = (int(next(iter(sides))[-1]), int(match.group(1)))
                self.name = []

    def handle_data(self, data: str) -> None:
        if self.title_depth is not None:
            self.name.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self.divs:
            if self.title_depth == len(self.divs):
                self.title_depth = None
            self.divs.pop()
        if tag == "a" and self.current is not None:
            side, team_id = self.current
            self.teams.append((side, team_id, " ".join(" ".join(self.name).split())))
            self.current = None
            self.name = []
            self.title_depth = None


def parse_match_page(html: str, match_id: int, event_id: int) -> list[tuple[int, str]]:
    parser = MatchHeader()
    parser.feed(html)
    parsed = urlparse(parser.canonical or "")
    if (parsed.scheme != "https" or parsed.netloc != "www.vlr.gg"
            or not parsed.path.startswith(f"/{match_id}/") or parsed.query
            or not parser.event_ids or set(parser.event_ids) != {event_id}
            or len(parser.teams) != 2 or [side for side, _, _ in parser.teams] != [1, 2]
            or parser.teams[0][1] == parser.teams[1][1]
            or not all(name for _, _, name in parser.teams)):
        raise ValueError(f"match {match_id} header identity incomplete or contradictory")
    return [(team_id, name) for _, team_id, name in parser.teams]


def verify_openers(spec: dict, pages: dict[int, str]) -> int:
    count = 0
    for group in spec["groups"].values():
        for key in ("opening_1", "opening_2"):
            slot = group[key]
            match_id = slot["match_id"]
            if match_id not in pages:
                raise ValueError(f"missing page for {match_id}")
            actual = parse_match_page(pages[match_id], match_id, spec["event_id"])
            expected = list(zip(slot["team_ids"], slot["teams"]))
            if actual != expected:
                raise ValueError(f"{match_id}: page identities {actual!r} differ from pinned {expected!r}")
            count += 1
    return count


def fetch_match_page(session: requests.Session, match_id: int) -> str:
    """Fetch only the exact trusted match URL with a bounded response body."""
    response = session.get(
        f"https://www.vlr.gg/{match_id}/", timeout=20,
        allow_redirects=False, stream=True,
    )
    try:
        if response.status_code in {301, 302, 303, 307, 308}:
            raise ValueError(f"{match_id}: redirect rejected")
        response.raise_for_status()
        parsed = urlparse(response.url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "www.vlr.gg"
            or not parsed.path.startswith(f"/{match_id}/")
        ):
            raise ValueError(f"{match_id}: returned a different match or host")

        max_bytes = 2 * 1024 * 1024
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except (TypeError, ValueError):
                declared_length = None
            if declared_length is not None and declared_length > max_bytes:
                raise ValueError(f"{match_id}: page response too large")

        body = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            if len(body) + len(chunk) > max_bytes:
                raise ValueError(f"{match_id}: page response too large")
            body.extend(chunk)
        return bytes(body).decode(response.encoding or "utf-8", errors="replace")
    finally:
        response.close()


def main() -> None:
    spec = load_bracket_spec(2766)
    pages: dict[int, str] = {}
    session = requests.Session()
    for group in spec["groups"].values():
        for key in ("opening_1", "opening_2"):
            match_id = group[key]["match_id"]
            pages[match_id] = fetch_match_page(session, match_id)
    count = verify_openers(spec, pages)
    print(f"{datetime.now(timezone.utc).isoformat()} direct vlr.gg pages: {count}/8 opener identities match pinned names, IDs and order")
    for group in spec["groups"].values():
        for key in ("opening_1", "opening_2"):
            match_id = group[key]["match_id"]
            print(f"  https://www.vlr.gg/{match_id}/ {parse_match_page(pages[match_id], match_id, 2766)}")


if __name__ == "__main__":
    main()
