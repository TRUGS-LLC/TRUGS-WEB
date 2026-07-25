"""Standing dependency and emission contracts for trugs-web.

These turn three one-time fixes into checks that cannot silently regress:

* every declared substrate pin carries an upper bound;
* a declared substrate dependency is either imported or documented;
* the emitted graph declares the vocabularies it is validated against.
"""

import tomllib
from pathlib import Path

from trugs_web.crawler import Source
from trugs_web.graph_builder import TRUGSWebGraphBuilder

SUBSTRATE = {"trugs-tools", "trugs-store"}
DIST_TO_MODULE = {"trugs-tools": "trugs_tools", "trugs-store": "trugs_store"}
EXPECTED_VOCABULARIES = ["research_v1", "core_v2.0.0"]
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _dist_name(spec: str) -> str:
    return spec.split("[")[0].split(">")[0].split("<")[0].split("=")[0].strip()


def _declared_substrate() -> list[str]:
    data = tomllib.loads(PYPROJECT.read_text())
    return [
        d for d in data["project"].get("dependencies", []) if _dist_name(d) in SUBSTRATE
    ]


def test_substrate_pins_are_bounded():
    """Every declared substrate pin carries a version upper bound."""
    # Strip any environment marker first: `; python_version < "3.14"` also contains
    # "<" and would otherwise read as a version ceiling that isn't there.
    unbounded = [d for d in _declared_substrate() if "<" not in d.split(";")[0]]
    assert not unbounded, f"unbounded substrate pin(s): {unbounded}"


def test_no_undocumented_unused_substrate_dep():
    """A declared substrate dep is imported, or is named by an adjacent comment.

    The comment is required to name the distribution, which is what makes a
    deliberate declaration distinguishable from an accidental one. Whether the
    stated reason is a *good* one is a review judgement, not a test's.
    """
    src = PYPROJECT.read_text()
    root = PYPROJECT.parent
    sources = list((root / "src").rglob("*.py")) + list((root / "tests").rglob("*.py"))
    blob = "\n".join(p.read_text() for p in sources)
    lines = src.split("\n")

    for dep in _declared_substrate():
        dist = _dist_name(dep)
        module = DIST_TO_MODULE[dist]
        if f"import {module}" in blob or f"from {module}" in blob:
            continue
        idx = next(
            (
                i
                for i, ln in enumerate(lines)
                if dist in ln and not ln.strip().startswith("#")
            ),
            None,
        )
        assert idx is not None, f"{dist} is declared but its entry is not locatable"
        same = "#" in lines[idx] and dist in lines[idx].split("#", 1)[1].lower()
        above = (
            idx > 0
            and lines[idx - 1].strip().startswith("#")
            and dist in lines[idx - 1].lower()
        )
        assert same or above, f"{dist} is declared, unimported, and undocumented"


def test_emitted_graph_declares_and_validates_under_its_vocabularies():
    """The emitted graph declares its vocabularies and validates clean under them."""
    builder = TRUGSWebGraphBuilder(name="contract-graph", topic="dependency-contract")
    builder.add_source_node(
        Source(url="https://example.com/a", title="A", source_type="WEB_SOURCE"),
        credibility=0.7,
    )

    vocabularies = builder.graph["capabilities"]["vocabularies"]
    assert vocabularies == EXPECTED_VOCABULARIES, (
        f"emitted vocabularies {vocabularies!r} drift from {EXPECTED_VOCABULARIES!r}"
    )
    # No `core_v1.0.0 not in vocabularies` assertion here: the equality above
    # already implies it, so it could never fail. That the retired vocabulary
    # actually hard-rejects is verified against the substrate, not restated here.

    result = builder.validate()
    assert result.valid, f"emitted graph failed validation: {result.to_dict()}"
    assert result.errors == []
