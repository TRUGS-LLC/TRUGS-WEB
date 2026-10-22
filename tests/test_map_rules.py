"""Compare generated ignore rules with Git and exercise Markdown heading boundaries."""

import itertools
import os
from pathlib import PurePosixPath
import subprocess

import pytest

from trugs_web.map import map_folder


def ignore_patterns():
    patterns = ["", "# comment", "!", "/", "//", "\\", "[", "[]", "[!]"]
    # Odd/even backslashes, escaped spaces followed by more spaces, and CRLF.
    patterns += [
        "foo" + "\\" * escapes + " " * spaces
        for escapes in range(7)
        for spaces in range(4)
    ]
    patterns += ["a\rb", "a\tb", "a\vb", "a\fb", "a.txt\r", "\ufeffa.txt"]
    # Every printable escape, including characters which do not need escaping.
    patterns += [
        prefix + "\\" + chr(char) + suffix
        for char in range(32, 127)
        for prefix, suffix in (("", ".txt"), ("literal", ".txt"))
    ]
    tokens = ("a", "*", "?", "**", "***", "a*", "*a", "a?", "?a", "a**", "**a")
    patterns += [
        prefix + token + suffix
        for token in tokens
        for prefix in ("", "/", "x/", "**/", "a/**/", "a/")
        for suffix in ("", "/", "/b", "/**", "/**/b", "\\/b")
    ]
    atoms = ("a", "z", "-", "b", "\\-", "[", "]", "[:digit:]", "[:bad:]", "\\]", "\\[")
    patterns += ["[" + a + b + "].txt" for a, b in itertools.product(atoms, repeat=2)]
    endpoints = ("a", "b", "z", "0", "9", "-", "\\-", "\\]", "[:digit:]")
    patterns += [
        "[" + negation + a + "-" + b + "].txt"
        for a, b in itertools.product(endpoints, repeat=2)
        for negation in ("", "!", "^")
    ]
    patterns += [
        "[" + negation + "[:" + name + ":]].txt"
        for name in (
            "alnum",
            "alpha",
            "blank",
            "cntrl",
            "digit",
            "graph",
            "lower",
            "print",
            "punct",
            "space",
            "upper",
            "xdigit",
            "unknown",
        )
        for negation in ("", "!", "^")
    ]
    patterns += [
        "[a-b-c].txt",
        "[z-a-b].txt",
        "[a-].txt",
        "[-a].txt",
        "[]a].txt",
        "[!a].txt",
        "[é].txt",
        "[!é].txt",
        "a[",
        "a[]",
        "a[[:digit:]",
    ]
    patterns += [
        "**\\/b",
        "/**\\/b",
        "x/**\\/b",
        "**/**\\/b",
        "a/**/**\\/b",
        "a/**\\/b",
        "***\\/b",
        "/***\\/b",
        "x/***\\/b",
        "**/***\\/b",
        "a/**/***\\/b",
        "a/***\\/b",
        "****/**\\/x",
        "***\\/*",
        "*****\\/[!a]?*",
        "**\\/**",
        "***\\/x?",
        "***\\/x**",
        "**\\/*",
        "**\\/[!a]",
        "****\\/\\****",
        "/***\\/ab",
        "***\\/b[!a]****",
        "***\\/[!a]/",
        "*****\\/b",
        "***\\/**",
        "*****\\/***",
        "**\\/***x/",
        "***\\/b[!a]*****x*",
    ]
    return list(dict.fromkeys(patterns))


def ignore_paths():
    names = [chr(char) + ".txt" for char in range(1, 128) if chr(char) != "/"]
    names += [
        "literal" + chr(char) + ".txt" for char in range(32, 127) if chr(char) != "/"
    ]
    names += ["é.txt", "٣.txt", "😀.txt", "a\rb", "a\tb", "a\vb", "a\fb", "a[", "a[]"]
    names += [
        "foo" + "\\" * escapes + " " * spaces
        for escapes in range(4)
        for spaces in range(3)
    ]
    names += [
        prefix + name
        for prefix in ("a/", "a/x/", "a/x/y/", "x/", "x/a/", "x/a/x/", "x/a/x/y/", "z/")
        for name in ("b", "a.txt", "b.txt", "1.txt", "a\nb.txt", "keep.txt")
    ]
    names += ["b", "aa", "ab", "ba", "xa", "a.txt", "keep.txt", "a\nb.txt"]
    return sorted(set(names))


def assert_git_parity(root, paths):
    # Compare directory nodes and ignore files as well as the generated file names.
    paths = sorted(
        set(paths)
        | {
            str(parent)
            for path in paths
            for parent in PurePosixPath(path).parents
            if str(parent) != "."
        }
        | {".gitignore"}
        | ({"a/.gitignore"} if (root / "a/.gitignore").exists() else set())
        | {"empty", "a/empty", "x/empty"}
    )
    for name in ("empty", "a/empty", "x/empty"):
        (root / name).mkdir(exist_ok=True)
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.excludesFile=/dev/null",
            "-C",
            str(root),
            "check-ignore",
            "--no-index",
            "-z",
            "--stdin",
        ],
        input=b"\0".join(os.fsencode("./" + path) for path in paths) + b"\0",
        capture_output=True,
    )
    assert result.returncode in {0, 1}, result.stderr
    ignored = {os.fsdecode(path[2:]) for path in result.stdout.split(b"\0") if path}
    included = {
        node["properties"]["path"]
        for node in map_folder(root, include_hidden=True)["nodes"]
        if "path" in node["properties"]
    }
    assert set(paths) - included == ignored


@pytest.mark.parametrize("pattern", ignore_patterns())
def test_generated_gitignore_parity(pattern, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    paths = ignore_paths()
    for name in paths:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("data")
    (root / ".gitignore").write_bytes((pattern + "\n").encode())
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    assert_git_parity(root, paths)


@pytest.mark.parametrize(
    ("rules", "nested"),
    [
        ("*.txt\n!keep.txt\n", ""),
        ("*\n!a/\n!a/**\n", ""),
        ("a/\n!a/keep.txt\n", "!keep.txt\n"),
        ("a/*\n!a/keep.txt\n", ""),
        ("a/**\n!a/x/keep.txt\n", ""),
        ("a/**\n!a/x/\n!a/x/keep.txt\n", ""),
        ("*.txt\n", "!keep.txt\n"),
        ("*.txt\n", "!*.txt\nb.txt\n"),
        ("*.txt\n", "!/a.txt\n"),
        ("/*\n!/a\n/a/*\n!/a/x\n", ""),
        ("b/\n", ""),
        ("a/\n!a/\n", "*.txt\n!keep.txt\n"),
    ],
)
def test_gitignore_order_and_directory_scope(rules, nested, tmp_path):
    paths = ignore_paths()
    for name in paths:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("data")
    (tmp_path / ".gitignore").write_text(rules)
    (tmp_path / "a/.gitignore").write_text(nested)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert_git_parity(tmp_path, paths)


def test_descending_range_cli(tmp_path, capsys):
    from trugs_web.cli import main

    (tmp_path / ".gitignore").write_text("[z-a].txt\n")
    for name in ("z.txt", "a.txt"):
        (tmp_path / name).write_text("data")
    assert main(["map", str(tmp_path)]) == 0
    assert '"path": "a.txt"' in capsys.readouterr().out


@pytest.mark.parametrize(
    ("source", "title"),
    [
        ("First heading\n=============\n\n## Second heading\n", "First heading"),
        ("```python\n# Example comment\n```\n\n# Actual heading\n", "Actual heading"),
        ("~~~python\n# Comment\n~~~\n# Actual\n", "Actual"),
        ("````python\n```\n# Comment\n`````\n# Actual\n", "Actual"),
        ("~~~~~\n~~~~\n# Comment\n~~~~~~\n# Actual\n", "Actual"),
        ("```\n~~~\n# Comment\n~~~\n```\n# Actual\n", "Actual"),
        ("~~~\n```\n# Comment\n```\n~~~\n# Actual\n", "Actual"),
        ("   ```py\n# Comment\n   ````  \n# Actual\n", "Actual"),
        ("```\n    ```\n# Comment\n```\n# Actual\n", "Actual"),
        ("```\n``` trailing text\n# Comment\n```\n# Actual\n", "Actual"),
        ("```\nFalse heading\n===\n```\nReal\n---\n", "Real"),
        ("    # Comment\n\n# Actual\n", "Actual"),
        ("\t# Comment\n\n# Actual\n", "Actual"),
        ("  \t# Comment\n# Actual\n", "Actual"),
        ("    False heading\n    ===\nReal\n===\n", "Real"),
        ("First line\nsecond line\n---\n# Later\n", "First line second line"),
        ("   First\n   ===   \n", "First"),
        ("### First ### \n# Later\n", "First"),
        ("### First###\n# Later\n", "First###"),
        ("   ###### First\n# Later\n", "First"),
        ("#\tFirst\n", "First"),
        ("####### Not heading\n#Actual\n\n# Real\n", "Real"),
        ("#\n# Later\n", ""),
        ("# ###\n# Later\n", ""),
        ("No heading\n", None),
        ("```\n# Unclosed\n", None),
        ("~~~\nTitle\n===\n", None),
        ("    # Only code\n", None),
        ("---\n# Real\n", "Real"),
        ("> ```\n> # Comment\n> ```\n# Real\n", "Real"),
        ("> ~~~~\n> # Comment\n> ~~~~~\n# Real\n", "Real"),
        ("> ```\n> # Comment\n# Real\n", "Real"),
        ("- ```\n  # Comment\n  ```\n# Real\n", "Real"),
        ("- ```\n  # Comment\n# Real\n", "Real"),
        ("1. ~~~~\n   # Comment\n   ~~~~~\n# Real\n", "Real"),
        ("- item\n  - ```\n    # Comment\n    ```\n# Real\n", "Real"),
        ("> - ```\n>   # Comment\n>   ```\n# Real\n", "Real"),
        ("```\n> ```\n# Comment\n```\n# Real\n", "Real"),
        ("> # First\n# Later\n", "First"),
        ("- # First\n# Later\n", "First"),
        ("- First\n  ---\n# Later\n", "First"),
        ("- item\n      # Code comment\n# Real\n", "Real"),
    ],
)
def test_first_markdown_heading(source, title, tmp_path):
    (tmp_path / "README.md").write_text(source)
    props = next(
        node["properties"]
        for node in map_folder(tmp_path)["nodes"]
        if node["properties"]["path"] == "README.md"
    )
    assert props.get("title") == title


@pytest.mark.parametrize("marker", ["`", "~"])
@pytest.mark.parametrize("length", range(3, 11))
@pytest.mark.parametrize("indent", ["", "   "])
def test_markdown_fence_lengths(marker, length, indent, tmp_path):
    # A shorter run cannot close the fence; an equally long or longer run can.
    for extra in (0, 2):
        source = (
            indent
            + marker * length
            + "\n"
            + marker * (length - 1)
            + "\n# Code comment\n"
            + "False heading\n===\n"
            + indent
            + marker * (length + extra)
            + " \t\n"
            + "First heading\n---\n# Later\n"
        )
        test_first_markdown_heading(source, "First heading", tmp_path)
