"""Describe a folder without executing its code or contacting its links."""

from __future__ import annotations

import ast
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
from urllib.parse import unquote, urlsplit

JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".json")
JS_IMPORT = re.compile(
    r"\b(?:import|export)\s+(?:[^;]*?\s+from\s*)?['\"](\.{1,2}/[^'\"]+)['\"]"
    r"|\brequire\s*\(\s*['\"](\.{1,2}/[^'\"]+)['\"]\s*\)"
)


# Git's named classes use ASCII character ranges, independent of Python's Unicode classes.
_POSIX_CLASSES = {
    "alnum": "a-zA-Z0-9",
    "alpha": "a-zA-Z",
    "blank": r" \t",
    "cntrl": r"\x00-\x1f\x7f",
    "digit": "0-9",
    "graph": r"\x21-\x7e",
    "lower": "a-z",
    "print": r"\x20-\x7e",
    "punct": r"\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e",
    "space": r" \t\r\n",
    "upper": "A-Z",
    "xdigit": "a-fA-F0-9",
}


def _bracket_class(pattern: str, start: int) -> tuple[str, int]:
    """Consume a whole bracket expression, including nested POSIX class tokens."""
    i = start + 1
    negate = i < len(pattern) and pattern[i] in "!^"
    if negate:
        i += 1
    first = i
    group = ""
    while i < len(pattern):
        char = pattern[i]
        if char == "]" and i != first:
            # Even negated classes cannot cross a path separator.
            return "(?!/)[" + ("^" if negate else "") + group + "]", i
        if char == "\\" and i + 1 < len(pattern):
            i += 1
            group += re.escape(pattern[i])
        elif pattern.startswith("[:", i):
            end = pattern.find(":]", i + 2)
            if end >= 0:
                name = pattern[i + 2 : end]
                if name not in _POSIX_CLASSES:
                    # Git rejects unknown named classes rather than matching them literally.
                    return "(?!)", end + 1
                group += _POSIX_CLASSES[name]
                i = end + 1
            else:
                group += r"\["
        elif char == "-":
            group += "-"
        else:
            group += re.escape(char)
        i += 1
    return r"\[", start


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _id(kind: str, value: str) -> str:
    return kind.lower() + "_" + _digest(value.encode())


def _wildmatch(pattern: str) -> str:
    """Git's slash-aware glob patterns, translated using only the standard library."""
    result = ""
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "\\" and i + 1 < len(pattern):
            i += 1
            result += re.escape(pattern[i])
        elif char == "*":
            end = i
            while end < len(pattern) and pattern[end] == "*":
                end += 1
            recursive = (
                end - i >= 2
                and (i == 0 or pattern[i - 1] == "/")
                and (end == len(pattern) or pattern[end] == "/")
            )
            if recursive and end < len(pattern):
                result += "(?:[^/]+/)*"
                end += 1
            else:
                result += ".*" if recursive else "[^/]*"
            i = end - 1
        elif char == "?":
            result += "[^/]"
        elif char == "[":
            group, i = _bracket_class(pattern, i)
            result += group
        else:
            result += re.escape(char)
        i += 1
    return result


class IgnoreRules:
    """Rules are inherited by a directory; ignored parents are never traversed."""

    def __init__(
        self, rules: list[tuple[str, re.Pattern[bytes], bool, bool]] | None = None
    ):
        self.rules = list(rules or [])

    def extend(self, directory: Path, relative: str) -> IgnoreRules:
        result = IgnoreRules(self.rules)
        ignore = directory / ".gitignore"
        if ignore.is_file() and not ignore.is_symlink():
            for raw in ignore.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                line = re.sub(r"(?<!\\) +$", "", raw)
                if not line or line.startswith("#"):
                    continue
                negate = line.startswith("!")
                if negate:
                    line = line[1:]
                directory_only = line.endswith("/")
                line = line.rstrip("/")
                anchored = "/" in line
                line = line.lstrip("/")
                # Escaped leading #/! and spaces are literal characters.
                if line:
                    prefix = "" if anchored else "(?:.*/)?"
                    result.rules.append(
                        (
                            relative,
                            # Git matches filesystem bytes, including in negated classes.
                            re.compile(os.fsencode(prefix + _wildmatch(line) + "$")),
                            negate,
                            directory_only,
                        )
                    )
        return result

    def ignored(self, path: str, is_dir: bool) -> bool:
        ignored = False
        for base, pattern, negate, directory_only in self.rules:
            prefix = "" if base == "." else base + "/"
            if path.startswith(prefix) and (is_dir or not directory_only):
                if pattern.fullmatch(os.fsencode(path[len(prefix) :])):
                    ignored = not negate
        return ignored


class _HTML(HTMLParser):
    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.title: list[str] = []
        self.in_title = False
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        self.links.extend(
            value for key, value in attrs if key in {"href", "src"} and value
        )

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)


def _python_targets(text: str, path: str, files: set[str]) -> set[str]:
    tree = ast.parse(text)
    targets: set[str] = set()
    parent = posixpath.dirname(path)

    def resolve(base: str) -> None:
        for candidate in (base + ".py", base + "/__init__.py"):
            if candidate in files:
                targets.add(candidate)
                break

    for item in ast.walk(tree):
        if isinstance(item, ast.Import):
            for alias in item.names:
                for prefix in ("", "src/"):
                    resolve(prefix + alias.name.replace(".", "/"))
        elif isinstance(item, ast.ImportFrom):
            module = (item.module or "").replace(".", "/")
            if item.level:
                base = parent
                for _ in range(item.level - 1):
                    base = posixpath.dirname(base)
                bases = [posixpath.join(base, module).rstrip("/")]
            else:
                bases = [module, "src/" + module]
            for base in bases:
                if module:
                    resolve(base)
                for alias in item.names:
                    if alias.name != "*":
                        resolve(posixpath.join(base, alias.name))
    return targets


def _js_target(path: str, specifier: str, files: set[str]) -> str | None:
    base = posixpath.normpath(posixpath.join(posixpath.dirname(path), specifier))
    candidates = [base]
    suffix = PurePosixPath(base).suffix
    substitutions = {
        ".js": (".ts", ".tsx"),
        ".jsx": (".tsx",),
        ".mjs": (".mts",),
        ".cjs": (".cts",),
    }
    if suffix in substitutions:
        candidates.extend(base[: -len(suffix)] + ext for ext in substitutions[suffix])
    if not suffix:
        candidates.extend(base + ext for ext in JS_EXTENSIONS)
    candidates.extend(base + "/index" + ext for ext in JS_EXTENSIONS)
    return next((candidate for candidate in candidates if candidate in files), None)


def map_folder(folder: str | Path, *, include_hidden: bool = False) -> dict:
    """Return a content-derived CORE graph; symlinks are recorded, never followed."""
    root = Path(folder).resolve()
    if not root.is_dir():
        raise ValueError("map needs a folder")
    nodes: dict[str, dict] = {}
    texts: dict[str, str] = {}
    unread: list[dict] = []

    def node(path: str, kind: str, properties: dict, parent: str | None) -> dict:
        entry: dict = {
            "id": _id(kind, path),
            "type": kind,
            "properties": properties,
            "parent_id": _id("MODULE", parent) if parent is not None else None,
            "contains": [],
            "metric_level": "BASE_" + kind,
            "dimension": "system",
        }
        nodes[path] = entry
        if parent is not None:
            nodes[parent]["contains"].append(entry["id"])
        return entry

    def walk(
        directory: Path, relative: str, inherited: IgnoreRules, parent: str | None
    ) -> None:
        current = node(
            relative,
            "MODULE",
            {"path": relative, "name": relative, "kind": "folder"},
            parent,
        )
        rules = inherited.extend(directory, relative)
        content = []
        size = 0
        for child in sorted(directory.iterdir(), key=lambda p: p.name):
            path = child.name if relative == "." else relative + "/" + child.name
            is_dir = child.is_dir() and not child.is_symlink()
            if (
                child.name == ".git"
                or (is_dir and child.name.startswith(".") and not include_hidden)
                or rules.ignored(path, is_dir)
            ):
                continue
            if is_dir:
                walk(child, path, rules, relative)
            else:
                data = (
                    os.readlink(child).encode()
                    if child.is_symlink()
                    else child.read_bytes()
                )
                kind = child.suffix.lower().lstrip(".") or "text"
                props = {
                    "path": path,
                    "name": path,
                    "kind": kind,
                    "size": len(data),
                    "sha256": _digest(data),
                }
                node(path, "FILE", props, relative)
                reason = ""
                if child.is_symlink():
                    reason = "symlink"
                    props["kind"] = "symlink"
                elif b"\0" in data:
                    reason = "binary"
                else:
                    try:
                        texts[path] = data.decode("utf-8")
                    except UnicodeDecodeError:
                        reason = "undecodable"
                if reason:
                    unread.append({"path": path, "reason": reason})
                elif kind not in {
                    "py",
                    "js",
                    "jsx",
                    "ts",
                    "tsx",
                    "mjs",
                    "cjs",
                    "mts",
                    "cts",
                    "md",
                    "markdown",
                    "html",
                    "htm",
                }:
                    unread.append({"path": path, "reason": "imports not read"})
            props = nodes[path]["properties"]
            size += props["size"]
            content.append([child.name, props["kind"], props["sha256"]])
        current["properties"].update(
            size=size,
            sha256=_digest(
                json.dumps(content, ensure_ascii=True, separators=(",", ":")).encode()
            ),
        )

    walk(root, ".", IgnoreRules(), None)
    files = {path for path, entry in nodes.items() if entry["type"] == "FILE"}
    edges: set[tuple[str, str, str]] = set()
    resources: dict[str, dict] = {}

    def reference(source: str, address: str) -> None:
        parts = urlsplit(address)
        if parts.scheme or parts.netloc or parts.path.startswith("/"):
            external = address
        else:
            target = (
                posixpath.normpath(
                    posixpath.join(posixpath.dirname(source), unquote(parts.path))
                )
                if parts.path
                else source
            )
            if target == ".." or target.startswith("../"):
                external = address
            else:
                if target not in nodes:
                    # Existing excluded files stay excluded, including through links.
                    if (root / target).exists():
                        return
                    node(
                        target,
                        "FILE",
                        {
                            "path": target,
                            "name": target,
                            "kind": "missing",
                            "missing": True,
                        },
                        None,
                    )
                edges.add((nodes[source]["id"], nodes[target]["id"], "REFERENCES"))
                return
        resource_id = _id("RESOURCE", external)
        resources[resource_id] = {
            "id": resource_id,
            "type": "RESOURCE",
            "properties": {"address": external},
            "parent_id": None,
            "contains": [],
            "metric_level": "BASE_RESOURCE",
            "dimension": "system",
        }
        edges.add((nodes[source]["id"], resource_id, "REFERENCES"))

    for path, text in sorted(texts.items()):
        props = nodes[path]["properties"]
        kind = props["kind"]
        if kind in {"md", "markdown"}:
            title = re.search(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", text, re.M)
            if title:
                props["title"] = title.group(1)
            for match in re.finditer(
                r"!?\[[^\]]*\]\(\s*(<[^>]*>|[^\s)]+)(?:\s+[^)]*)?\)|^ {0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)",
                text,
                re.M,
            ):
                reference(path, (match.group(1) or match.group(2)).strip("<>"))
        elif kind in {"html", "htm"}:
            html = _HTML(text)
            if html.title:
                props["title"] = "".join(html.title).strip()
            for address in html.links:
                reference(path, address)
        elif kind == "py":
            try:
                targets = _python_targets(text, path, files)
            except SyntaxError:
                unread.append({"path": path, "reason": "Python syntax"})
                targets = set()
            for target in targets:
                edges.add((nodes[path]["id"], nodes[target]["id"], "DEPENDS_ON"))
        elif "." + kind in JS_EXTENSIONS and kind != "json":
            # Patterns deliberately do not claim to be a JavaScript parser.
            for match in JS_IMPORT.finditer(text):
                js_target = _js_target(path, match.group(1) or match.group(2), files)
                if js_target:
                    edges.add((nodes[path]["id"], nodes[js_target]["id"], "DEPENDS_ON"))
    nodes["."]["properties"]["unread"] = sorted(
        unread, key=lambda item: (item["path"], item["reason"])
    )
    graph = {
        "name": "folder",
        "version": "1.0.0",
        "type": "PROJECT",
        "dimension": "system",
        "dimensions": {"system": {"description": "Folder contents and references"}},
        "nodes": [nodes[path] for path in sorted(nodes)]
        + [resources[key] for key in sorted(resources)],
        "edges": [
            {"from_id": source, "to_id": target, "relation": relation}
            for source, target, relation in sorted(edges)
        ],
    }
    from trugs_tools.validator import validate_trug
    from trugs_tools.trl import decompile

    result = validate_trug(graph)
    if not result.valid:
        raise ValueError("Folder graph failed validation: " + str(result.errors))
    decompile(graph)
    return graph
