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
        {"displayName": "BadPort", "isPlayableCharacter": True,
         "displayIcon": "https://media.valorant-api.com:8443/evil.png"},
        {"displayName": "BadUserInfo", "isPlayableCharacter": True,
         "displayIcon": "https://attacker@media.valorant-api.com/evil.png"},
        {"displayName": "MalformedAuthority", "isPlayableCharacter": True,
         "displayIcon": "https://[::1/evil.png"},
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

        def iter_content(self, chunk_size):
            import json
            assert chunk_size == 64 * 1024
            yield json.dumps(self.json()).encode()

        def close(self):
            pass

    class Session:
        calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return Response()

    icon_dir = tmp_path / "agents"
    icon_dir.mkdir()
    (icon_dir / "miks.png").write_bytes(b"x" * 600_000)
    cache = tmp_path / "agent_icons.json"
    cache.write_text(json.dumps({"miks": {"file": "miks.png"}}), encoding="utf-8")
    session = Session()

    result = refresh(session=session, cache=cache, icon_dir=icon_dir)

    assert result["miks"]["file"] == "miks.png"
    assert len(session.calls) == 1  # catalog only; image is reused
    assert session.calls[0][1]["allow_redirects"] is False


def test_refresh_rejects_oversized_catalog_without_buffering(tmp_path):
    import pytest

    from vct_quant.agent_icons import MAX_CATALOG_BYTES, refresh

    class Response:
        headers = {"content-type": "application/json"}
        url = "https://valorant-api.com/v1/agents?isPlayableCharacter=true"

        def __init__(self):
            self.closed = False

        @property
        def content(self):
            raise AssertionError("catalog body must be streamed, not buffered")

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            assert chunk_size == 64 * 1024
            yield b"x" * MAX_CATALOG_BYTES
            yield b"x"

        def close(self):
            self.closed = True

    class Session:
        def __init__(self):
            self.response = Response()

        def get(self, url, **kwargs):
            assert kwargs["stream"] is True
            assert kwargs["allow_redirects"] is False
            return self.response

    session = Session()
    with pytest.raises(ValueError, match="catalog exceeds"):
        refresh(session=session, cache=tmp_path / "catalog.json", icon_dir=tmp_path / "agents")
    assert session.response.closed
    assert not (tmp_path / "catalog.json").exists()


def test_refresh_streams_and_rejects_oversized_image_without_buffering(tmp_path):
    from vct_quant.agent_icons import MAX_BYTES, refresh

    class Response:
        def __init__(self, url, *, catalog=False):
            self.url = url
            self.catalog = catalog
            self.headers = ({"content-type": "application/json"} if catalog else
                            {"content-type": "image/png"})
            self.closed = False

        @property
        def content(self):
            assert self.catalog, "image body must be streamed, not buffered"
            return b"catalog"

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{
                "displayName": "Miks", "isPlayableCharacter": True,
                "displayIcon": "https://media.valorant-api.com/agents/miks.png",
            }]}

        def iter_content(self, chunk_size):
            assert chunk_size == 64 * 1024
            if self.catalog:
                import json
                yield json.dumps({"data": [{
                    "displayName": "Miks", "isPlayableCharacter": True,
                    "displayIcon": "https://media.valorant-api.com/agents/miks.png",
                }]}).encode()
            else:
                yield b"x" * (MAX_BYTES + 1)

        def close(self):
            self.closed = True

    class Session:
        def __init__(self):
            self.calls = []
            self.responses = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            response = Response(url, catalog=(url.endswith("isPlayableCharacter=true")))
            self.responses.append(response)
            return response

    session = Session()
    cache = tmp_path / "agent_icons.json"
    icon_dir = tmp_path / "agents"

    result = refresh(session=session, cache=cache, icon_dir=icon_dir)

    assert "file" not in result["miks"]
    assert not (icon_dir / "miks.png").exists()
    assert session.calls[1][1]["stream"] is True
    assert session.calls[1][1]["allow_redirects"] is False
    assert all(response.closed for response in session.responses[1:])


def test_refresh_writes_image_larger_than_legacy_limit(tmp_path):
    import json

    from vct_quant.agent_icons import refresh

    size = 600_000

    class Response:
        def __init__(self, url, *, catalog=False):
            self.url = url
            self.catalog = catalog
            self.headers = {"content-type": "application/json" if catalog else "image/png"}

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            assert chunk_size == 64 * 1024
            if self.catalog:
                yield json.dumps({"data": [{
                    "displayName": "Miks", "isPlayableCharacter": True,
                    "displayIcon": "https://media.valorant-api.com/agents/miks.png",
                }]}).encode()
            else:
                yield b"x" * size

        def close(self):
            pass

    class Session:
        def get(self, url, **kwargs):
            return Response(url, catalog=url.endswith("isPlayableCharacter=true"))

    icon_dir = tmp_path / "agents"
    result = refresh(session=Session(), cache=tmp_path / "agent_icons.json", icon_dir=icon_dir)

    assert result["miks"]["file"] == "miks.png"
    assert (icon_dir / "miks.png").stat().st_size == size


def test_refresh_rejects_image_response_with_untrusted_authority(tmp_path):
    from vct_quant.agent_icons import refresh

    class Response:
        def __init__(self, url, *, catalog=False):
            self.url = url
            self.headers = {"content-type": "application/json" if catalog else "image/png"}

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            if self.headers["content-type"] == "application/json":
                import json
                yield json.dumps({"data": [{
                    "displayName": "Miks", "isPlayableCharacter": True,
                    "displayIcon": "https://media.valorant-api.com/agents/miks.png",
                }]}).encode()
            else:
                yield b"image-bytes"

        def close(self):
            pass

    class Session:
        def get(self, url, **kwargs):
            if url.endswith("isPlayableCharacter=true"):
                return Response(url, catalog=True)
            return Response("https://user@media.valorant-api.com:8443/agents/miks.png")

    icon_dir = tmp_path / "agents"
    result = refresh(session=Session(), cache=tmp_path / "catalog.json", icon_dir=icon_dir)

    assert "file" not in result["miks"]
    assert not (icon_dir / "miks.png").exists()
