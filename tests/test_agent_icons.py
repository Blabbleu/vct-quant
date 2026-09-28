from vct_quant.agent_icons import _catalog, slug


def test_agent_slug_normalizes_alias_punctuation_and_bounds():
    assert slug("KAY/O") == "kayo"
    assert slug("Chamber") == "chamber"
    assert slug("A") is None
    assert slug("Agent With Spaces And Too Long") is None


def test_catalog_keeps_only_playable_https_official_icons():
    payload = {"data": [
        {"displayName": "KAY/O", "isPlayableCharacter": True,
         "displayIcon": "https://media.valorant-api.com/agents/kayo/displayicon.png"},
        {"displayName": "Miks", "isPlayableCharacter": True,
         "displayIcon": "https://media.valorant-api.com/agents/miks/displayicon.png"},
        {"displayName": "NotPlayable", "isPlayableCharacter": False,
         "displayIcon": "https://media.valorant-api.com/agents/no/displayicon.png"},
        {"displayName": "BadHost", "isPlayableCharacter": True,
         "displayIcon": "https://example.com/evil.png"},
        {"displayName": "BadScheme", "isPlayableCharacter": True,
         "displayIcon": "http://media.valorant-api.com/evil.png"},
    ]}
    assert _catalog(payload) == {
        "kayo": {"name": "KAY/O", "url": "https://media.valorant-api.com/agents/kayo/displayicon.png"},
        "miks": {"name": "Miks", "url": "https://media.valorant-api.com/agents/miks/displayicon.png"},
    }


def test_refresh_reuses_cached_icon_without_repeated_image_download(tmp_path):
    import json

    from vct_quant.agent_icons import refresh

    class Response:
        headers = {"content-type": "application/json"}
        content = b"catalog"

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{
                "displayName": "Miks", "isPlayableCharacter": True,
                "displayIcon": "https://media.valorant-api.com/agents/miks.png",
            }]}

    class Session:
        calls = []

        def get(self, url, **kwargs):
            self.calls.append(url)
            return Response()

    icon_dir = tmp_path / "agents"
    icon_dir.mkdir()
    (icon_dir / "miks.png").write_bytes(b"png")
    cache = tmp_path / "agent_icons.json"
    cache.write_text(json.dumps({"miks": {"file": "miks.png"}}), encoding="utf-8")
    session = Session()

    result = refresh(session=session, cache=cache, icon_dir=icon_dir)

    assert result["miks"]["file"] == "miks.png"
    assert len(session.calls) == 1  # catalog only; image is reused
