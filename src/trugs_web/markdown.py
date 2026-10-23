"""Read folder metadata from Markdown without executing or rendering it."""

from __future__ import annotations

from html import unescape
import re
import string
from urllib.parse import quote, urlsplit, urlunsplit


_BLOCK_TAGS = (
    "address article aside base basefont blockquote body caption center col colgroup "
    "dd details dialog dir div dl dt fieldset figcaption figure footer form frame "
    "frameset h1 h2 h3 h4 h5 h6 head header hr html iframe legend li link main menu "
    "menuitem nav noframes ol optgroup option p param search section summary table "
    "tbody td tfoot th thead title tr track ul"
).split()
_TAG = (
    r"</?[A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z_:][\w.:-]*"
    r"(?:\s*=\s*(?:[^\s\"'=<>`]+|'[^']*'|\"[^\"]*\"))?)*\s*/?>"
)
_THEMATIC = re.compile(r" {0,3}(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,})$")


def _html_start(line: str, paragraph: bool) -> tuple[bool, str]:
    """CommonMark's seven HTML-block starts, and their terminator (empty = blank)."""
    if raw := re.match(r" {0,3}<(script|pre|style|textarea)(?=[\s>]|$)", line, re.I):
        return True, r"</" + raw[1] + r"\s*>"
    for opening, closing in (("<!--", "-->"), ("<?", r"\?>"), ("<![CDATA[", r"\]\]>")):
        if (
            line.lstrip(" ").startswith(opening)
            and len(line) - len(line.lstrip(" ")) < 4
        ):
            return True, closing
    if re.match(r" {0,3}<![A-Z]", line):
        return True, ">"
    if re.match(r" {0,3}</?(?:" + "|".join(_BLOCK_TAGS) + r")(?=[\s/>]|$)", line, re.I):
        return True, ""
    if not paragraph and re.fullmatch(r" {0,3}" + _TAG + r"[ \t]*", line):
        return True, ""
    return False, ""


def _blocks(text: str) -> list[tuple[str, str]]:
    """Keep inline-bearing paragraphs/headings; discard code and HTML blocks."""
    blocks: list[tuple[str, str]] = []
    paragraph: list[str] = []
    paragraph_quotes = 0
    paragraph_indent = 0
    fence = ""
    fence_length = 0
    block_quotes = 0
    block_indent = 0
    html = False
    html_end = ""
    quote_depth = 0
    list_indents: list[int] = []

    def flush(kind: str = "paragraph") -> None:
        if paragraph:
            blocks.append((kind, "\n".join(paragraph)))
            paragraph.clear()

    for line in (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\0", "\ufffd")
        .split("\n")
    ):
        line = line.expandtabs(4)
        if fence or html:
            content = line
            in_container = True
            for _ in range(block_quotes):
                prefix = re.match(r" {0,3}> ?", content)
                if not prefix:
                    in_container = False
                    break
                content = content[prefix.end() :]
            if (
                content.strip()
                and len(content) - len(content.lstrip(" ")) < block_indent
            ):
                in_container = False
            if in_container:
                content = content[block_indent:]
                if fence:
                    if re.fullmatch(
                        r" {0,3}" + fence + "{" + str(fence_length) + r",}[ \t]*",
                        content,
                    ):
                        fence = ""
                    continue
                if html_end:
                    if re.search(html_end, content, re.I):
                        html = False
                    continue
                if content.strip():
                    continue
                html = False
            else:
                fence = ""
                html = False
        quotes = 0
        while prefix := re.match(r" {0,3}> ?", line):
            quotes += 1
            line = line[prefix.end() :]
        if quotes != quote_depth and (not paragraph or quotes > paragraph_quotes):
            flush()
            list_indents = []
        quote_depth = quotes
        indent = len(line) - len(line.lstrip(" "))
        lazy = bool(paragraph) and (
            quotes < paragraph_quotes or indent < paragraph_indent
        )
        if line.strip() and not lazy:
            while list_indents and indent < list_indents[-1]:
                list_indents.pop()
        consumed = next(
            (width for width in reversed(list_indents) if width <= indent), 0
        )
        line = line[consumed:]
        while (
            not _THEMATIC.fullmatch(line)
            and not (paragraph and re.fullmatch(r" {0,3}(?:=+|-+)[ \t]*", line))
            and (item := re.match(r" {0,3}(?:[-+*]|\d{1,9}[.)])( +|$)", line))
        ):
            # Only a nonempty bullet or an ordered list starting at 1 interrupts text.
            if paragraph and (
                not line[item.end() :].strip() or re.match(r" {0,3}(?!1[.)])\d", line)
            ):
                break
            width = (
                item.end() - max(0, len(item[1]) - 1)
                if len(item[1]) > 4
                else item.end()
            )
            consumed += width
            list_indents.append(consumed)
            flush()
            lazy = False
            line = line[width:]
        if not line.strip():
            flush()
            continue
        # Indentation does not interrupt an open paragraph (including a setext title).
        if line.startswith("    "):
            if paragraph:
                paragraph.append(line.strip())
            continue
        opening = re.match(r" {0,3}(`{3,}|~{3,})(.*)$", line)
        if opening and (opening[1][0] == "~" or "`" not in opening[2]):
            flush()
            list_indents = [width for width in list_indents if width <= consumed]
            fence, fence_length = opening[1][0], len(opening[1])
            block_quotes, block_indent = quote_depth, consumed
            continue
        html, html_end = _html_start(line, bool(paragraph))
        if html:
            flush()
            list_indents = [width for width in list_indents if width <= consumed]
            block_quotes, block_indent = quote_depth, consumed
            if html_end and re.search(html_end, line, re.I):
                html = False
            continue
        atx = re.match(r" {0,3}#{1,6}(?:[ \t]+(.*)|$)", line)
        if atx:
            flush()
            list_indents = [width for width in list_indents if width <= consumed]
            blocks.append(
                ("heading", re.sub(r"(?:^|[ \t]+)#+[ \t]*$", "", atx[1] or "").strip())
            )
        elif paragraph and not lazy and re.fullmatch(r" {0,3}(?:=+|-+)[ \t]*", line):
            flush("heading")
        elif _THEMATIC.fullmatch(line):
            flush()
            list_indents = [width for width in list_indents if width <= consumed]
        else:
            if not paragraph:
                paragraph_quotes, paragraph_indent = quotes, consumed
            paragraph.append(line.strip())
    flush()
    return blocks


def _unescape(text: str) -> str:
    # Decode in one pass: an escaped ampersand cannot begin an entity.
    pattern = (
        r"\\([" + re.escape(string.punctuation) + r"])"
        r"|&(?:#[xX][0-9a-fA-F]{1,6}|#[0-9]{1,7}|[A-Za-z][A-Za-z0-9]{1,31});"
    )
    return re.sub(
        pattern, lambda match: match[1] if match[1] else unescape(match[0]), text
    )


def _address(text: str) -> str:
    text = _unescape(text)
    # CommonMark destinations use percent-encoded URLs, with international hostnames.
    try:
        parts = urlsplit(text)
        if parts.hostname and parts.scheme.lower() in {"", "http", "https", "mailto"}:
            host = parts.hostname
            if any(ord(c) > 127 for c in host):
                text = urlunsplit(
                    parts._replace(
                        netloc=parts.netloc.replace(host, host.encode("idna").decode())
                    )
                )
    except ValueError:
        pass
    text = re.sub(r"%(?![0-9a-fA-F]{2})", "%25", text)
    return quote(text, safe=";/?:@&=+$,-_.!~*'()#%")


def _destination(text: str, start: int) -> tuple[str, int] | None:
    """Read an angle destination or a bare destination with balanced parentheses."""
    i = start
    angle = i < len(text) and text[i] == "<"
    if angle:
        i += 1
        start = i
    depth = 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text) and text[i + 1] in string.punctuation:
            i += 2
            continue
        if angle:
            if char == ">":
                return _address(text[start:i]), i + 1
            if char in "<\n":
                return None
        else:
            if ord(char) < 33 or ord(char) == 127:
                break
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
        i += 1
    if angle or depth:
        return None
    return _address(text[start:i]), i


def _inline_target(text: str, start: int) -> tuple[str, int] | None:
    i = start
    while i < len(text) and text[i] in " \t\n":
        i += 1
    target = _destination(text, i)
    if target is None:
        return None
    address, end = target
    i = end
    while i < len(text) and text[i] in " \t\n":
        i += 1
    if i > end and i < len(text) and text[i] in "\"'(":
        close = ")" if text[i] == "(" else text[i]
        i += 1
        while i < len(text) and text[i] != close:
            if text[i] == "\\" and i + 1 < len(text):
                i += 1
            elif close == ")" and text[i] == "(":
                return None
            i += 1
        if i == len(text):
            return None
        i += 1
        while i < len(text) and text[i] in " \t\n":
            i += 1
    if i < len(text) and text[i] == ")":
        return address, i + 1
    return None


def _links(text: str) -> list[str]:
    """Scan brackets while excluding escapes, code spans, and inline HTML tokens."""
    links: list[str] = []
    brackets: list[tuple[bool, bool, int]] = []  # image, active, first nested link
    i = 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text) and text[i + 1] in string.punctuation:
            i += 2
            continue
        if char == "`":
            run = re.match(r"`+", text[i:])
            assert run is not None
            end = i + len(run[0])
            closer = re.search(r"(?<!`)" + run[0] + r"(?!`)", text[end:])
            i = end + closer.end() if closer else end
            continue
        if char == "<":
            token = re.match(
                r"<!--[\s\S]*?-->|<\?[\s\S]*?\?>|<!\[CDATA\[[\s\S]*?\]\]>|<![A-Z][^>]*>|"
                + _TAG,
                text[i:],
            )
            if token:
                i += token.end()
                continue
        # Recognize image openers while scanning, after escape/code/HTML handling.
        # A raw preceding ! may have been consumed as an escaped literal.
        if char == "!" and text[i + 1 : i + 2] == "[":
            brackets.append((True, True, len(links)))
            i += 2
            continue
        if char == "[":
            brackets.append((False, True, len(links)))
        elif char == "]" and brackets:
            image, active, nested = brackets.pop()
            target = (
                _inline_target(text, i + 2)
                if active and text[i + 1 : i + 2] == "("
                else None
            )
            if target:
                address, i = target
                if image:
                    del links[nested:]
                links.append(address)
                if not image:
                    brackets = [
                        (img, flag and img, index) for img, flag, index in brackets
                    ]
                continue
        i += 1
    return links


def read_markdown(text: str) -> tuple[str | None, list[str]]:
    """Return the first heading's source text and the declared Markdown references."""
    title = None
    links: list[str] = []
    for kind, content in _blocks(text):
        if kind == "heading" and title is None:
            title = " ".join(line.strip() for line in content.split("\n"))
        # Keep recording reference-definition targets as well as inline links.
        lines = content.split("\n")
        while lines and (definition := re.match(r"^\[[^\]]+\]:[ \t]*(.*)$", lines[0])):
            target = _destination(definition[1], 0)
            if not target or not target[0]:
                break
            links.append(target[0])
            lines.pop(0)
        links.extend(_links("\n".join(lines)))
    return title, links
