"""Folder description, content invariance and ignore compatibility."""

import json
import os
import shutil
import subprocess

import pytest
from trugs_tools.trl import decompile
from trugs_tools.validator import validate_trug

from trugs_web.map import map_folder


@pytest.fixture
def folder(tmp_path):
    files = {
        ".gitignore": "*.log\n/only-root.txt\ncache/\n!cache/keep.txt\n**/generated/**\n*.tmp\n!keep.tmp\nfile[0-9].txt\nspace\\ name.txt\n\\#literal\n\\!literal\n",
        "README.md": "# Folder title\n[page](web/index.html) [bad](absent.md) [external](https://example.org/x)\n[ref][id]\n[id]: web/index.html\n",
        "web/index.html": '<title>Page title</title><a href="../README.md">Home</a><img src="image.bin">',
        "web/image.bin": b"\x00\xff\x01",
        "broken.txt": b"\xff\xfe",
        "other.rs": "use another;",
        "main.py": "import helper\nfrom pkg import item\n",
        "helper.py": "value = 1\n",
        "pkg/__init__.py": "",
        "pkg/item.py": "from . import next\n",
        "pkg/next.py": "",
        "app.ts": "import { a } from './a';\nconst b = require('./b');\nexport { c } from './parts/c';\nimport './effect.js';\nimport x from 'external';\nimport y from './missing';\n",
        "a.tsx": "",
        "b.js": "",
        "parts/c/index.ts": "",
        "effect.ts": "",
        "skipped.log": "",
        "only-root.txt": "",
        "cache/keep.txt": "",
        "nested/only-root.txt": "",
        "nested/generated/a.py": "",
        "nested/.gitignore": "*.skip\n!keep.skip\n/root.txt\n",
        "nested/a.skip": "",
        "nested/keep.skip": "",
        "nested/root.txt": "",
        "nested/more/root.txt": "",
        "discard.tmp": "",
        "keep.tmp": "",
        "file3.txt": "",
        "filex.txt": "",
        "space name.txt": "",
        "#literal": "",
        "!literal": "",
        ".hidden/file.py": "",
        ".visible": "",
    }
    root = tmp_path / "folder"
    for path, data in files.items():
        dest = root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data if isinstance(data, bytes) else data.encode())
    return root


def by_path(graph):
    return {
        n["properties"]["path"]: n for n in graph["nodes"] if "path" in n["properties"]
    }


def edge_paths(graph, relation):
    names = {
        n["id"]: n["properties"].get("path", n["properties"].get("address"))
        for n in graph["nodes"]
    }
    return {
        (names[e["from_id"]], names[e["to_id"]])
        for e in graph["edges"]
        if e["relation"] == relation
    }


def test_table_and_core_output(folder):
    graph = map_folder(folder)
    assert validate_trug(graph).valid
    assert decompile(graph)
    nodes = by_path(graph)
    assert nodes["README.md"]["properties"]["title"] == "Folder title"
    assert nodes["web/index.html"]["properties"]["title"] == "Page title"
    assert nodes["web/image.bin"]["properties"]["size"] == 3
    assert len(nodes["web/image.bin"]["properties"]["sha256"]) == 64
    assert nodes["absent.md"]["properties"]["missing"] is True
    assert ".hidden" not in nodes and ".visible" in nodes
    assert ".hidden/file.py" in by_path(map_folder(folder, include_hidden=True))
    assert edge_paths(graph, "DEPENDS_ON") == {
        ("main.py", "helper.py"),
        ("main.py", "pkg/__init__.py"),
        ("main.py", "pkg/item.py"),
        ("pkg/item.py", "pkg/next.py"),
        ("app.ts", "a.tsx"),
        ("app.ts", "b.js"),
        ("app.ts", "parts/c/index.ts"),
        ("app.ts", "effect.ts"),
    }
    assert edge_paths(graph, "REFERENCES") == {
        ("README.md", "web/index.html"),
        ("README.md", "absent.md"),
        ("README.md", "https://example.org/x"),
        ("web/index.html", "README.md"),
        ("web/index.html", "web/image.bin"),
    }
    unread = {
        item["path"]: item["reason"] for item in nodes["."]["properties"]["unread"]
    }
    assert unread["web/image.bin"] == "binary"
    assert unread["broken.txt"] == "undecodable"
    assert unread["other.rs"] == "imports not read"
    for node in graph["nodes"]:
        for child in node["contains"]:
            assert (
                next(n for n in graph["nodes"] if n["id"] == child)["parent_id"]
                == node["id"]
            )


def test_gitignore_matches_git(folder):
    subprocess.run(["git", "init", "-q", str(folder)], check=True)
    paths = sorted(
        str(p.relative_to(folder))
        for p in folder.rglob("*")
        if p.is_file() and ".git" not in p.parts
    )
    result = subprocess.run(
        ["git", "-C", str(folder), "check-ignore", "--no-index", "--stdin"],
        input="\n".join(paths) + "\n",
        text=True,
        capture_output=True,
    )
    assert result.returncode in {0, 1}
    expected = set(paths) - set(result.stdout.splitlines())
    actual = {
        p
        for p, n in by_path(map_folder(folder, include_hidden=True)).items()
        if n["type"] == "FILE" and not n["properties"].get("missing")
    }
    assert actual == expected


def test_stable_across_runs_times_and_locations(folder, tmp_path):
    original = json.dumps(map_folder(folder), sort_keys=True)
    assert json.dumps(map_folder(folder), sort_keys=True) == original
    for path in folder.rglob("*"):
        os.utime(path, (1000000000, 1000000000))
    assert json.dumps(map_folder(folder), sort_keys=True) == original
    moved = tmp_path / "relocated"
    shutil.copytree(folder, moved)
    assert json.dumps(map_folder(moved), sort_keys=True) == original
    (moved / "helper.py").write_text("changed = True\n")
    assert json.dumps(map_folder(moved), sort_keys=True) != original


def test_symlink_does_not_read_target(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to("../absent")
    graph = map_folder(root)
    node = by_path(graph)["link"]
    assert node["properties"]["kind"] == "symlink"
    assert graph["nodes"][0]["properties"]["unread"] == [
        {"path": "link", "reason": "symlink"}
    ]


def test_output_cannot_become_its_own_input(folder, capsys):
    from trugs_web.cli import main

    assert main(["map", str(folder), "--out", str(folder / "map.trug.json")]) == 1
    assert "outside" in capsys.readouterr().err
