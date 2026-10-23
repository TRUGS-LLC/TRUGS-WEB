"""Compare generated Markdown folder metadata with CommonMark tokens."""

from itertools import product
import posixpath
import random
import string
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
import pytest

from trugs_web.map import map_folder
from trugs_web.markdown import read_markdown


def _reference(source):
    parser = MarkdownIt("commonmark")
    # This comparison measures syntax; mapping records addresses without fetching them.
    parser.validateLink = lambda address: True
    tokens = parser.parse(source)
    title = None
    links = []
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and title is None:
            title = " ".join(line.strip() for line in tokens[i + 1].content.split("\n"))
        for child in token.children or []:
            if child.type == "link_open":
                links.append(child.attrGet("href"))
            elif child.type == "image":
                links.append(child.attrGet("src"))
    return title, links


def _containers(source):
    yield "plain", source
    yield "quote", "\n".join("> " + line for line in source.split("\n"))
    yield "list", "- " + source.replace("\n", "\n  ")
    yield "ordered", "1. " + source.replace("\n", "\n   ")
    yield "nested", "> - " + source.replace("\n", "\n>   ")


def markdown_cases():
    targets = [
        r"a\&amp;b.md",
        "a&copy.md",
        "a&copy;.md",
        "a&#x28;b&#x29;.md",
        "a%.md",
        "a%2.md",
        "a[b].md",
        "bad\x7f.md",
        *["guide" + "(" * depth + "v2" + ")" * depth + ".md" for depth in range(7)],
        "guide(v2).md",
        "deep(v2(a)).md",
        r"guide\(v2\).md",
        "<guide(v2).md>",
        "guide%28v2%29.md",
        "<space name.md>",
        "<café.md>",
        "a&amp;b.md",
        "<a&#32;b.md>",
        "missing(v2).md",
        "https://example.org/a(b)",
        "<https://example.org/a b>",
        "#section",
        "",
    ]
    labels = ["Guide", "[nested] label", r"escaped\] label", "`code ]` label"]
    titles = ["", ' "A title"', " 'A title'", " (A title)"]
    contexts = [
        lambda s: s + "\n\n# Actual heading\n",
        lambda s: "# " + s + "\n\n# Later\n",
        lambda s: s + "\n    continuation\n===\n\n# Later\n",
    ]
    for i, (target, label, title, image, context) in enumerate(
        product(targets, labels, titles, ("", "!"), contexts)
    ):
        body = image + "[" + label + "](" + target + title + ")"
        yield f"inline-{i}", context(body)
    body = "# False heading\n[Guide](guide(v2).md)\nText\n===\n"
    wrappers = [
        ("backticks", "```python\n", "```\n"),
        ("tildes", "~~~~\n", "~~~~~\n"),
        ("comment", "<!--\n", "-->\n"),
        ("processing", "<?target\n", "?>\n"),
        ("declaration", "<!DOCTYPE\n", ">\n"),
        ("cdata", "<![CDATA[\n", "]]>\n"),
        *[
            (tag, f"<{tag}>\n", f"</{tag}>\n")
            for tag in (
                "div",
                "table",
                "script",
                "style",
                "pre",
                "textarea",
                "custom-tag",
            )
        ],
    ]
    for name, opening, closing in wrappers:
        for indent in ("", " ", "   "):
            source = (
                indent
                + opening
                + body
                + indent
                + closing
                + "\n# Actual heading\n[After](after.md)\n"
            )
            for container, wrapped in _containers(source):
                yield f"block-{name}-{len(indent)}-{container}", wrapped
            yield f"unclosed-{name}-{len(indent)}", indent + opening + body
    for name, wrapped in _containers(
        "    # Code\n    [Code](code.md)\n\n# Actual\n[After](after.md)\n"
    ):
        yield f"indented-{name}", wrapped
    for marker, length, indent, container in product(
        ("`", "~"), range(3, 8), ("", "   "), range(5)
    ):
        source = (
            indent
            + marker * length
            + "\n"
            + marker * (length - 1)
            + "\n"
            + body
            + indent
            + marker * (length + 1)
            + "\n# Actual\n[After](after.md)\n"
        )
        yield (
            f"fence-{marker}-{length}-{len(indent)}-{container}",
            list(_containers(source))[container][1],
        )
    for level, indent, ending in product(
        range(1, 8), ("", " ", "   ", "    ", "\t"), ("", " ###", "###")
    ):
        source = indent + "#" * level + " First" + ending + "\n\n# Later\n"
        yield f"atx-{level}-{len(indent)}-{ending}", source
    for underline, continuation, container in product(
        ("=", "===", "-", "---"),
        ("", "second\n", "    continuation\n", "\tcontinuation\n"),
        range(5),
    ):
        source = "First\n" + continuation + underline + "\n\n# Later\n"
        yield (
            f"setext-{underline}-{continuation!r}-{container}",
            list(_containers(source))[container][1],
        )
    for source in [
        r"\[No](missing.md)",
        "`[No](missing.md)`",
        "``[No](missing.md) ` ``",
        "<!--[No](missing.md)-->",
        '<span title="[No](missing.md)">[Yes](after.md)</span>',
        "[No](unbalanced(a.md)",
        "[No](a.md extra)",
        "[No](<bad\ntarget>)",
        "[Yes](a(b(c)).md) and [Next](after.md)",
        "[outer [inner](after.md)](missing.md)",
        "[Yes](after.md\n 'title')",
        "![image [inner](after.md)](guide(v2).md)",
        "[link ![image](guide(v2).md)](after.md)",
        "[Yes](after.md)<!--\n[No](missing.md)\n-->",
    ]:
        yield f"inline-boundary-{source!r}", source + "\n\n# Actual\n"

    pieces = [
        "paragraph [x](a(b).md)\n",
        "# Title [x](a.md)\n",
        "First\n    continuation\n===\n",
        "```\n# False\n[x](bad.md)\n```\n",
        "    # Code\n    [x](bad.md)\n",
        "<!--\n# False\n[x](bad.md)\n-->\n",
        "<div>\n# False\n[x](bad.md)\n</div>\n",
        "<custom>\n# False\n[x](bad.md)\n</custom>\n",
        "> First\ncontinuation\n",
        "- First\ncontinuation\n",
        "===\n",
        "---\n",
        "\n",
        "<span>[x](a.md)</span>\n",
        "2. Text\n",
        "- [x](a.md)\n",
        "> ```\n> # False\n",
        "- ```\n  # False\n",
    ]
    rng = random.Random(20261022)
    for i in range(3000):
        yield f"composition-{i}", "".join(rng.choices(pieces, k=3)) + "\n# Final\n"
    for prefix, continuation, underline in product(
        ("> ", "- ", "1. "), ("", "second\n"), ("===", "---")
    ):
        for restore in ("", "> " if prefix == "> " else " " * len(prefix)):
            yield (
                f"lazy-{prefix}-{continuation!r}-{underline}-{restore}",
                prefix + "First\n" + continuation + restore + underline + "\n# Later\n",
            )


def punctuation_escape_cases():
    """Compose escapes with every character boundary of link/image syntax."""
    yield "escape-image-marker", "# Example\n[\\![inner](real.md)](absent.md)\n"
    titles = ("", ' "title"', " 'title'", " (title)")
    templates = []
    for image, target, title in product(("", "!"), ("after.md", "<after.md>"), titles):
        templates.append(f"{image}[label]({target}{title})")
    for outer, inner, title in product(("", "!"), ("", "!"), titles):
        templates.append(f"{outer}[{inner}[inner](after.md{title})](absent.md{title})")
    for n, template in enumerate(templates):
        # All 32 ASCII punctuation escapes, before/inside/after every opener,
        # label, closer, bare/angle destination and quoted/parenthesized title.
        # Nested templates exercise all four link/image combinations as well.
        for char, position in product(string.punctuation, range(len(template) + 1)):
            source = template[:position] + "\\" + char + template[position:]
            yield f"escape-insert-{n}-{ord(char)}-{position}", source + "\n\n# Actual\n"
        for position, char in enumerate(template):
            if char not in string.punctuation:
                continue
            # Escape the delimiter itself, including odd/even runs of literal
            # backslashes, rather than only adding a literal beside a delimiter.
            for count in range(6):
                source = template[:position] + "\\" * count + template[position:]
                yield (
                    f"escape-delimiter-{n}-{position}-{count}",
                    source + "\n\n# Actual\n",
                )


def nested_link_image_cases():
    """Compose links and images through two nested label levels."""
    yield (
        "linked-image-with-link-alt",
        "# Example\n[![image [inner](real.md)](image.png)](guide.md)\n",
    )
    titles = ("", ' "title"', " 'title'", " (title)")
    for n, (markers, angles, target_titles) in enumerate(
        product(
            product(("", "!"), repeat=3),
            product((False, True), repeat=3),
            product(titles, repeat=3),
        )
    ):
        source = "inner"
        for depth, (marker, angle, title) in enumerate(
            zip(markers, angles, target_titles)
        ):
            target = ("real.md", "image.png", "guide.md")[depth]
            if angle:
                target = "<" + target + ">"
            source = f"{marker}[label {source}]({target}{title})"
        for context, wrapped in _containers(source):
            yield f"nested-{n}-{context}", wrapped + "\n\n# Actual\n"
        yield f"nested-{n}-heading", "# " + source + "\n"
    # Failed image targets must leave ordinary nested-link rejection in force;
    # literal punctuation must not create image openers or bracket boundaries.
    for n, (markers, alt, ending) in enumerate(
        product(
            product(("", "!"), repeat=3),
            ("inner", r"\!inner", r"inner\]", "`inner ]`", "<span>inner</span>"),
            ("(after.md)", "(absent.md)", "(broken target)", "", r"\(real.md)"),
        )
    ):
        inner, middle, outer = markers
        source = f"{outer}[{middle}[{inner}[{alt}](real.md)]{ending}](guide.md)"
        yield f"nested-boundary-{n}", source + "\n\n# Actual\n"


CASES = (
    list(markdown_cases())
    + list(punctuation_escape_cases())
    + list(nested_link_image_cases())
)


@pytest.mark.parametrize(("case", "source"), CASES, ids=[case for case, _ in CASES])
def test_generated_markdown_matches_commonmark(case, source, tmp_path):
    expected_title, expected_links = _reference(source)
    title, links = read_markdown(source)
    assert title == expected_title, (case, source)
    assert sorted(links) == sorted(expected_links), (case, source)
    for name in (
        "guide(v2).md",
        "deep(v2(a)).md",
        "space name.md",
        "café.md",
        "a&b.md",
        "a b.md",
        "after.md",
        "real.md",
        "image.png",
        "guide.md",
    ):
        (tmp_path / name).write_text("")
    (tmp_path / "README.md").write_text(source)
    graph = map_folder(tmp_path)
    props = {node["id"]: node["properties"] for node in graph["nodes"]}
    entry = next(p for p in props.values() if p.get("path") == "README.md")
    assert entry.get("title") == expected_title
    actual = {
        props[edge["to_id"]].get("path", props[edge["to_id"]].get("address"))
        for edge in graph["edges"]
        if edge["relation"] == "REFERENCES"
    }
    expected = set()
    expected_missing = set()
    for address in expected_links:
        parts = urlsplit(address)
        if parts.scheme or parts.netloc or parts.path.startswith("/"):
            expected.add(address)
            continue
        path = posixpath.normpath(unquote(parts.path)) if parts.path else "README.md"
        expected.add(path)
        if not (tmp_path / path).exists():
            expected_missing.add(path)
    assert actual == expected
    missing = {p["path"] for p in props.values() if p.get("missing")}
    assert missing == expected_missing
