from pathlib import Path

from vct_quant.player_photos import _has_roster, clean_avatar_url, download, extract_roster, local_photo, local_photos


def test_download_streams_and_stops_once_avatar_exceeds_size_limit(tmp_path, monkeypatch):
    import requests

    class OversizedResponse:
        url = "https://owcdn.net/img/large.png"
        headers = {"content-type": "image/png"}

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            assert chunk_size > 0
            yield b"a" * (512 * 1024)
            yield b"b"
            raise AssertionError("must stop reading after crossing the limit")

        def close(self):
            pass

    calls = []
    def fake_get(url, **kwargs):
        calls.append(kwargs)
        return OversizedResponse()
    monkeypatch.setattr(requests, "get", fake_get)

    photos = {"42": {"avatar": "https://owcdn.net/img/large.png"}}
    assert download(photos, tmp_path) == 0
    assert calls[0]["stream"] is True
    assert list(tmp_path.iterdir()) == []


def test_avatar_url_allows_known_https_cdn_and_rejects_placeholder_or_other_hosts():
    assert clean_avatar_url("https://owcdn.net/img/abc123.png") == "https://owcdn.net/img/abc123.png"
    assert clean_avatar_url("https://www.vlr.gg/img/base/ph/sil.png") is None
    assert clean_avatar_url("http://owcdn.net/img/abc.png") is None
    assert clean_avatar_url("https://example.com/avatar.png") is None


def test_team_response_roster_shape_distinguishes_empty_roster_from_bad_payload():
    assert _has_roster({"data": {"segments": [{"roster": []}]}})
    assert _has_roster({"data": {"roster": []}})
    assert not _has_roster({"error": "temporary upstream failure"})
    assert not _has_roster({"data": {"segments": [{"error": "bad segment"}]}})


def test_extract_roster_keeps_only_positive_exact_player_ids_with_valid_avatar():
    payload = {"data": {"segments": [{"roster": [
        {"id": 42, "name": "Player", "avatar": "https://owcdn.net/img/a.png"},
        {"id": "0", "name": "Bad", "avatar": "https://owcdn.net/img/b.png"},
        {"id": 43, "name": "Placeholder", "avatar": "https://www.vlr.gg/img/base/ph/sil.png"},
    ]}]}}
    assert extract_roster(payload) == {"42": {"avatar": "https://owcdn.net/img/a.png", "handle": "Player"}}


def test_local_photo_uses_only_a_valid_cached_file(tmp_path: Path):
    photo_dir = tmp_path / "players"
    photo_dir.mkdir()
    (photo_dir / "42.webp").write_bytes(b"image")
    assert local_photo("42", {"42": {"file": "42.webp"}}, photo_dir) == "/players/42.webp"
    assert local_photo("../42", {"../42": {"file": "42.webp"}}, photo_dir) is None
    assert local_photo("42", {"42": {"file": "42.svg"}}, photo_dir) is None


def test_local_photos_reuses_a_supplied_cache_for_many_ids(tmp_path: Path):
    photo_dir = tmp_path / "players"
    photo_dir.mkdir()
    (photo_dir / "42.webp").write_bytes(b"image")
    (photo_dir / "43.png").write_bytes(b"image")
    assert local_photos([42, "43", 44],
                        {"42": {"file": "42.webp"}, "43": {"file": "43.png"}},
                        photo_dir) == {"42": "/players/42.webp", "43": "/players/43.png", "44": None}
