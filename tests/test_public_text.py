"""Keep numbered internal workflow labels out of the repository's public text."""

from pathlib import Path
import re
import subprocess

import pytest


INTERNAL_LABEL = re.compile(
    r"\b(?:(?:SC|PC|phase)[\s_-]*\d+[a-z]?|"
    r"(?:success|performance|acceptance)[\s_-]+criteri(?:on|a)[\s_-]*\d+[a-z]?)\b",
    re.IGNORECASE,
)


@pytest.mark.parametrize("prefix", ["SC", "PC", "Phase", "success criterion"])
@pytest.mark.parametrize("separator", ["-", "_", " ", ""])
def test_numbered_workflow_label_detection(prefix, separator):
    label = separator.join((prefix, "8"))
    assert INTERNAL_LABEL.search(label)
    assert INTERNAL_LABEL.search(label.lower())
    assert INTERNAL_LABEL.search(label.upper())


@pytest.mark.parametrize(
    "text",
    ["SHA-256", "GPT-4", "deferred_phase2/", "phase matching", "query criteria"],
)
def test_public_terms_are_not_workflow_labels(text):
    assert not INTERNAL_LABEL.search(text)


def test_public_files_have_no_numbered_workflow_labels():
    root = Path(__file__).resolve().parents[1]
    names = (
        subprocess.check_output(
            ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=root
        )
        .decode()
        .split("\0")
    )
    hits = []
    for name in sorted(set(names) - {""}):
        text = (root / name).read_bytes().decode("utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            if INTERNAL_LABEL.search(line):
                hits.append(f"{name}:{number}: {line}")
    assert not hits, "Numbered workflow labels in public text:\n" + "\n".join(hits)
