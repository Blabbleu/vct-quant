import json

from vct_quant import logos


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_clean_url_rejects_placeholder_and_non_https():
    assert logos.clean_url("//owcdn.net/img/a.png") == "https://owcdn.net/img/a.png"
    assert logos.clean_url("/img/x.png") == "https://www.vlr.gg/img/x.png"
    assert logos.clean_url("https://www.vlr.gg/img/vlr/tmp/vlr.png") is None
    assert logos.clean_url("http://evil.test/a.png") is None
    assert logos.clean_url("javascript:alert(1)") is None
    assert logos.clean_url(None) is None


def test_harvest_prefers_newest_snapshot_and_team_pages(tmp_path):
    _write(tmp_path / "match_details_20260101T000000Z.json", {"data": {"segments": [{"teams": [
        {"id": "1", "name": "Alpha", "logo": "https://owcdn.net/img/old.png"},
        {"id": "2", "name": "Bravo", "logo": "https://www.vlr.gg/img/vlr/tmp/vlr.png"},
    ]}]}})
    _write(tmp_path / "match_details_20260201T000000Z.json", {"data": {"segments": [{"teams": [
        {"id": "1", "name": "Alpha", "logo": "https://owcdn.net/img/new.png"},
    ]}]}})
    _write(tmp_path / "team_3_20260101T000000Z.json",
           {"data": {"segments": [{"id": "3", "name": "Charlie", "logo": "//owcdn.net/img/c.png"}]}})
    (tmp_path / "match_details_bad.json").write_text("{not json", encoding="utf-8")

    found = logos.harvest(tmp_path)

    assert found["1"]["logo"] == "https://owcdn.net/img/new.png"
    assert "2" not in found  # placeholder is not a logo
    assert found["3"]["logo"] == "https://owcdn.net/img/c.png"


def test_load_logos_is_empty_without_cache_and_drops_bad_entries(tmp_path):
    assert logos.load_logos(tmp_path / "missing.json") == {}
    path = tmp_path / "team_logos.json"
    _write(path, {"1": {"logo": "https://owcdn.net/img/a.png"}, "x": {"logo": "https://owcdn.net/b.png"},
                  "2": {"logo": "http://insecure/a.png"}, "3": "nope"})
    assert logos.load_logos(path) == {"1": "https://owcdn.net/img/a.png"}


def test_load_logos_prefers_local_copy(tmp_path):
    (tmp_path / "logos").mkdir()
    (tmp_path / "logos" / "7.png").write_bytes(b"png")
    path = tmp_path / "team_logos.json"
    _write(path, {"7": {"logo": "https://owcdn.net/img/a.png", "file": "7.png"},
                  "8": {"logo": "https://owcdn.net/img/b.png", "file": "8.png"},
                  "9": {"logo": "https://owcdn.net/img/c.png", "file": "../../etc/passwd"}})
    assert logos.load_logos(path, tmp_path / "logos") == {
        "7": "/logos/7.png",
        "8": "https://owcdn.net/img/b.png",  # file missing on disk: fall back to source
        "9": "https://owcdn.net/img/c.png",  # unsafe name ignored
    }


def test_tags_come_from_team_pages_and_are_not_erased_by_empty_tags(tmp_path):
    _write(tmp_path / "team_624_20260101T000000Z.json",
           {"data": {"segments": [{"id": "624", "name": "Paper Rex", "tag": "PRX",
                                   "logo": "https://owcdn.net/img/p.png"}]}})
    _write(tmp_path / "match_details_20260301T000000Z.json", {"data": {"segments": [{"teams": [
        {"id": "624", "name": "Paper Rex", "tag": "", "logo": "https://owcdn.net/img/p2.png"},
        {"id": "9", "name": "Weird", "tag": "<script>", "logo": ""},
    ]}]}})
    found = logos.harvest(tmp_path)
    assert found["624"]["tag"] == "PRX"
    assert "9" not in found

    cache = tmp_path / "team_logos.json"
    _write(cache, {"624": {"tag": "PRX"}, "7": {"tag": "toolongtag"}, "8": {"tag": ""}})
    assert logos.load_tags(cache) == {"624": "PRX"}


def test_clean_tag():
    assert logos.clean_tag(" PRX ") == "PRX"
    assert logos.clean_tag("T1") == "T1"
    assert logos.clean_tag("FUT.") == "FUT."
    assert logos.clean_tag("") is None
    assert logos.clean_tag("a b") is None
    assert logos.clean_tag("ABCDEFG") is None
