"""CLI smoke tests (AAA #2295 SP3) — covers SC-5 (cli exposes help) + the query/synthesize verbs."""

import pytest

from trugs_web.cli import build_parser, main
from trugs_web.crawler import Source
from trugs_web.graph_builder import TRUGSWebGraphBuilder


def test_version(capsys):
    assert main(["--version"]) == 0
    assert "trugs-web 2.0.0" in capsys.readouterr().out


def test_help_exits_zero(capsys):
    # bare invocation prints help and returns 0 (no verb)
    assert main([]) == 0
    assert "crawl" in capsys.readouterr().out


@pytest.mark.parametrize("verb", ["crawl", "build", "query", "synthesize"])
def test_each_verb_has_help(verb):
    # SC-5: every verb exposes --help (argparse raises SystemExit(0) on --help)
    parser = build_parser()
    with pytest.raises(SystemExit) as ei:
        parser.parse_args([verb, "--help"])
    assert ei.value.code == 0


@pytest.fixture
def built_graph(tmp_path):
    b = TRUGSWebGraphBuilder(name="cli-test", topic="acupuncture")
    b.add_source_node(
        Source(url="https://example.com/a", title="A", source_type="PAPER"),
        credibility=0.8,
    )
    b.add_source_node(
        Source(url="https://example.com/b", title="B", source_type="WEB_SOURCE"),
        credibility=0.6,
    )
    path = tmp_path / "g.trug.json"
    b.save(str(path))
    return str(path)


def test_query_verb(built_graph, capsys):
    assert main(["query", built_graph, "--q", "high credibility sources"]) == 0
    assert capsys.readouterr().out.strip()  # prints something


def test_synthesize_verb_writes_report(built_graph, tmp_path, capsys):
    out = tmp_path / "report.md"
    assert (
        main(
            [
                "synthesize",
                built_graph,
                "--q",
                "acupuncture evidence",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    assert out.exists() and out.read_text().strip()
