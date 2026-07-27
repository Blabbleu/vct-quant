import pytest

from vct_quant.etl.entity_resolution import normalize_name, vlr_id_from_url


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.vlr.gg/team/2593/fnatic", 2593),
        ("/player/9/tenz", 9),
        ("event/1188/champions-2023", 1188),
        # Match URLs have no typed segment — the ID is bare.
        ("https://www.vlr.gg/716578/gentle-mates-gc-vs-giantx-gc", 716578),
        # The vlrggapi upcoming feed omits the host entirely.
        ("715113/contra-vs-bestia-vcl-26-latin-america", 715113),
        ("not a url at all", None),
        ("", None),
    ],
)
def test_vlr_id_from_url(url, expected):
    assert vlr_id_from_url(url) == expected


def test_normalize_name():
    assert normalize_name("  Paper   Rex ") == "paper rex"
