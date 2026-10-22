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
    """Parse byte members before emitting regex: Git also accepts descending ranges."""
    i = start + 1
    negate = i < len(pattern) and pattern[i] in "!^"
    if negate:
        i += 1
    first = i
    members: set[int] = set()
    previous: int | None = None
    while i < len(pattern):
        char = pattern[i]
        if char == "]" and i != first:
            if negate:
                members = set(range(256)) - members
            members.discard(ord("/"))
            group = "".join(r"\x%02x" % byte for byte in sorted(members))
            return ("[" + group + "]" if group else "(?!)"), i
        if char == "\\" and i + 1 < len(pattern):
            i += 1
            previous = ord(pattern[i])
            members.add(previous)
        elif (
            char == "-"
            and previous is not None
            and i + 1 < len(pattern)
            and pattern[i + 1] != "]"
        ):
            i += 1
            if pattern[i] == "\\":
                i += 1
                if i == len(pattern):
                    return "(?!)", i - 1
            # The preceding literal remains a member even if this range is descending.
            members.update(range(previous, ord(pattern[i]) + 1))
            previous = None
        elif pattern.startswith("[:", i):
            end = pattern.find(":]", i + 2)
            if end >= 0:
                name = pattern[i + 2 : end]
                if name not in _POSIX_CLASSES:
                    # Git rejects unknown named classes rather than matching them literally.
                    return "(?!)", end + 1
                members.update(
                    byte
                    for byte in range(256)
                    if re.fullmatch("[" + _POSIX_CLASSES[name] + "]", chr(byte))
                )
                previous = None
                i = end + 1
            else:
                previous = ord(char)
                members.add(previous)
        else:
            previous = ord(char)
            members.add(previous)
        i += 1
    # An unterminated bracket expression never matches in Git.
    return "(?!)", len(pattern) - 1


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _id(kind: str, value: str) -> str:
    return kind.lower() + "_" + _digest(value.encode())


def _wildmatch(raw: bytes) -> bytes:
    """Git's slash-aware glob patterns, translated using only the standard library."""
    pattern = raw.decode("latin1")
    result = ""
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "\\":
            i += 1
            if i == len(pattern):
                result += "(?!)"
                break
            result += re.escape(pattern[i])
        elif char == "*":
            end = i
            while end < len(pattern) and pattern[end] == "*":
                end += 1
            recursive = (
                end - i >= 2
                and (i == 0 or pattern[i - 1] == "/")
                and (
                    end == len(pattern)
                    or pattern[end] == "/"
                    or pattern.startswith(r"\/", end)
                )
            )
            if recursive and end < len(pattern):
                # An escaped separator permits crossing slashes but still consumes one.
                if pattern[end] == "\\":
                    result += ".*/"
                    end += 2
                else:
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
    return result.encode("latin1")


def _ignore_line(raw: bytes) -> bytes:
    """Keep escaped spaces; discard only the unescaped trailing spaces."""
    end = 0
    i = 0
    while i < len(raw):
        if raw[i] == ord("\\") and i + 1 < len(raw):
            i += 2
            end = i
        else:
            if raw[i] != ord(" "):
                end = i + 1
            i += 1
    return raw[:end]


def _markdown_title(text: str) -> str | None:
    """First ATX or setext heading outside fenced or four-column-indented code."""
    fence = ""
    fence_length = 0
    fence_quotes = 0
    fence_indent = 0
    quote_depth = 0
    list_indents: list[int] = []
    paragraph: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = line.expandtabs(4)
        if fence:
            content = line
            in_container = True
            for _ in range(fence_quotes):
                quote = re.match(r" {0,3}> ?", content)
                if not quote:
                    in_container = False
                    break
                content = content[quote.end() :]
            if (
                content.strip()
                and len(content) - len(content.lstrip(" ")) < fence_indent
            ):
                in_container = False
            if in_container:
                content = content[fence_indent:]
                if re.fullmatch(
                    r" {0,3}" + fence + "{" + str(fence_length) + r",}[ \t]*", content
                ):
                    fence = ""
                continue
            # Leaving a list or quote ends its unclosed fenced block too.
            fence = ""
            paragraph = []
        quotes = 0
        while quote := re.match(r" {0,3}> ?", line):
            quotes += 1
            line = line[quote.end() :]
        if quotes != quote_depth:
            paragraph = []
            list_indents = []
        quote_depth = quotes
        indent = len(line) - len(line.lstrip(" "))
        if line.strip():
            while list_indents and indent < list_indents[-1]:
                list_indents.pop()
        consumed = list_indents[-1] if list_indents else 0
        line = line[consumed:]
        while item := re.match(r" {0,3}(?:[-+*]|\d{1,9}[.)])( +|$)", line):
            # More than four spaces after a marker leave indented code in the item.
            width = (
                item.end() - max(0, len(item[1]) - 1)
                if len(item[1]) > 4
                else item.end()
            )
            consumed += width
            list_indents.append(consumed)
            paragraph = []
            line = line[width:]
        opening = re.match(r" {0,3}(`{3,}|~{3,})(.*)$", line)
        if opening and (opening[1][0] == "~" or "`" not in opening[2]):
            fence = opening[1][0]
            fence_length = len(opening[1])
            fence_quotes = quote_depth
            fence_indent = consumed
            paragraph = []
            continue
        if not line.strip() or line.startswith("    "):
            paragraph = []
            continue
        atx = re.match(r" {0,3}#{1,6}(?:[ \t]+(.*)|$)", line)
        if atx:
            return re.sub(r"(?:^|[ \t]+)#+[ \t]*$", "", atx[1] or "").strip()
        if paragraph and re.fullmatch(r" {0,3}(?:=+|-+)[ \t]*", line):
            return " ".join(paragraph)
        # A thematic break or another block cannot supply a setext title.
        if re.match(r" {0,3}(?:>|[-+*][ \t]|\d+[.)][ \t])", line) or re.fullmatch(
            r" {0,3}(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,}|=+)", line
        ):
            paragraph = []
        else:
            paragraph.append(line.strip())
    return None


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
            for raw in ignore.read_bytes().removeprefix(b"\xef\xbb\xbf").split(b"\n"):
                line = _ignore_line(raw.removesuffix(b"\r"))
                if not line or line.startswith(b"#"):
                    continue
                negate = line.startswith(b"!")
                if negate:
                    line = line[1:]
                directory_only = line.endswith(b"/")
                if directory_only:
                    line = line[:-1]
                anchored = b"/" in line
                line = line.removeprefix(b"/")
                # Escaped leading #/! and spaces are literal characters.
                if line:
                    prefix = b"" if anchored else b"(?:.*/)?"
                    result.rules.append(
                        (
                            relative,
                            # Git matches filesystem bytes, including in negated classes.
                            re.compile(prefix + _wildmatch(line), re.DOTALL),
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
            title = _markdown_title(text)
            if title is not None:
                props["title"] = title
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
