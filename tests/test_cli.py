import sys

from vct_quant import cli
from vct_quant.etl import normalize


def test_load_vlrgg_dispatches_to_loader(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["vct", "load-vlrgg"])
    monkeypatch.setattr(normalize, "load_vlrgg_match_results", lambda: "loaded")

    cli.main()

    assert capsys.readouterr().out.strip() == "loaded"


def test_load_vlrgg_details_dispatches_to_loader(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["vct", "load-vlrgg-details"])
    monkeypatch.setattr(normalize, "load_vlrgg_match_details", lambda: "loaded details")

    cli.main()

    assert capsys.readouterr().out.strip() == "loaded details"
