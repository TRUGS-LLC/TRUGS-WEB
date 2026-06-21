"""T1.11 — graph-validation end-to-end (AAA #2295 SP2).

Closes the SC-4 grep-only gap and makes INVARIANT-2 (every emitted passive_trug validates)
explicit: build a TRUG with TRUGSWebGraphBuilder, prove `trugs_tools.validator.validate_trug`
is actually invoked on the emitted graph, and assert the result is VALID.
"""

import pytest

from trugs_web.crawler import Source
from trugs_web.graph_builder import TRUGSWebGraphBuilder


@pytest.mark.graph_validation_e2e
def test_builder_validate_invokes_validator_and_passes(monkeypatch):
    # Spy on the commons validator (graph_builder.validate() lazily imports it).
    import trugs_tools.validator as v

    calls = []
    real = v.validate_trug

    def spy(graph, *args, **kwargs):
        calls.append(graph)
        return real(graph, *args, **kwargs)

    monkeypatch.setattr(v, "validate_trug", spy)

    builder = TRUGSWebGraphBuilder(name="e2e-graph", topic="testing")
    builder.add_source_node(
        Source(url="https://example.com/a", title="A", source_type="WEB_SOURCE"),
        credibility=0.7,
    )

    result = builder.validate()

    # (1) the commons validator was actually called on the emitted graph (not just imported)
    assert calls, (
        "builder.validate() did not invoke trugs_tools.validator.validate_trug"
    )
    assert calls[0] is builder.graph
    # (2) the emitted passive TRUG is VALID
    assert result.valid, f"emitted TRUG failed validation: {result.to_dict()}"
    assert result.errors == []


@pytest.mark.graph_validation_e2e
def test_emitted_graph_has_passive_trug_envelope():
    """The emitted graph carries the structural envelope tg validate expects."""
    builder = TRUGSWebGraphBuilder(name="e2e-2", topic="testing")
    builder.add_source_node(
        Source(url="https://example.com/b", source_type="WEB_SOURCE")
    )
    graph = builder.graph
    for key in ("name", "version", "nodes", "edges", "dimensions"):
        assert key in graph, f"emitted TRUG missing envelope key: {key}"
    assert builder.validate().valid
