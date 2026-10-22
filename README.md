# trugs-web

```trl
PROCESS map SHALL MAP MODULE folder TO RECORD graph.
PROCESS query SHALL RETURN DATA result FROM RECORD graph.
AGENT publisher MAY READ RESOURCE source.
```

Describe a folder as a TRUGS graph, query a graph, or propose a graph from web
sources. Version **2.1.0**, unreleased; Python 3.11 or later. Install the wheel
with your Python package installer. `trugs-tools>=2.4.0,<3.0.0` and
`trugs-store>=2.0.0,<3.0.0` are required. The commands below need no model key.

A **hub** is a publisher's graph of sources on a topic, with the sources' titles,
addresses and provenance bound to its words. A publisher uses the hub to read
sources, learn what changed, and answer questions with evidence. The intended
loop is to review changes, update the graph, then sign and publish it on the
publisher's site. Other publishers can refer to it. Signing, publisher pages,
refresh, review, ranking, assessments and the starter template are coming;
they are described in the [draft v0 format](SPEC/hub-format-v0.md).

This version supplies an **unsigned** [hub on semantic and executable graphs](hubs/semantic-and-executable-graphs/).
It states earlier systems' strengths and gaps and treats TRUGS as one part of the
history. Core TRL expresses the relations; bindings carry the source details.

## Try it offline

```bash
trugs-web --version
trugs-web demo
```

`demo` prints one JSON query result from the hub installed inside the package.
It needs no working files, web extras, network or model. `query` also runs offline.

From this repository's root, describe the [sample folder](examples/):

```bash
trugs-web map examples --out sample.trug.json
trugs-web query sample.trug.json --q "best sources"
trugs-web query sample.trug.json --q "best sources" --format text
trugs-web query hubs/semantic-and-executable-graphs/graph.trug.json --q "best sources"
trugs-web query example.trug.json --q "GraphRAG"
trugs-web synthesize example.trug.json --q "GraphRAG"
```

`map` writes a graph of folders (`MODULE`), files (`FILE`), links (`REFERENCES`)
and local imports (`DEPENDS_ON`). The graph validates and decompiles with
trugs-tools 2.4.0. Query's default is one JSON object matching
[schema/query-result.schema.json](schema/query-result.schema.json); `--format text`
prints a readable list. The schema also ships as package data. Queries reuse the
existing traversal: an ordinary phrase finds incoming sources for matching nodes;
`best sources` lists nodes at or above the credibility threshold (0.5 by default).
These are traversal results, not a web search or an assessment of truth.

## Describe your folder

Pass a folder to `trugs-web map`. Omit `--out` to print JSON. Choose an output
outside the folder being described, so the output cannot become its own input.
`--include-hidden` includes hidden folders; `.git` is always excluded. Hidden
files such as `.gitignore` are included. Each folder's `.gitignore` applies to
its subtree, including negation and slash-aware wildcards; ignored parent folders
are not traversed. No global ignore file or repository-local exclude file is read.

Paths are relative to the input root. Files carry extension, byte length and
SHA-256; folders carry the total included byte length and a digest of the sorted
child names, kinds and digests. No time or absolute root path is recorded.
Markdown's first ATX heading (`#` through `######`, followed by whitespace or
end of line) or setext heading (text underlined with `=` or `-`) is recorded.
Headings may have up to three leading spaces. Four-column indentation, including
tabs, is code; headings inside it or backtick/tilde code fences are skipped.
List and blockquote prefixes are handled before these checks.
Fences have at least three matching markers and close with at least the opening
length. HTML's title is also recorded. Markdown inline and
reference links and HTML `href`/`src` produce references. Addresses leaving the
folder are recorded without being fetched. Missing local targets have
`missing: true`. Existing excluded targets stay excluded. Symlinks are recorded
by their link text and never followed. Binary, undecodable and unsupported
import languages are listed in the root's `unread` field.

Python imports use the standard AST parser. Absolute modules resolve from the
input root or its `src/` folder; relative imports resolve from the file's folder.
Only existing included `.py` files or package `__init__.py` files get edges.
JavaScript and TypeScript use patterns for relative `import`, `require` and
`export ... from`. They can match a comment or string; they are not a full parser.
Resolution tries the literal file first, then `.js` to `.ts`/`.tsx`, `.jsx` to
`.tsx`, `.mjs` to `.mts`, or `.cjs` to `.cts`. Extensionless imports try `.ts`,
`.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.mts`, `.cts`, `.json`, then `index` with
those extensions. Package aliases and dynamic imports are not resolved.

## Crawl with consent

The optional `web` extra supplies httpx, beautifulsoup4 and lxml. `crawl` and
`build` list every seed host and ask for **yes** before any request. Declining,
end of input, or stdin without a terminal exits nonzero without a request.
`--yes` explicitly skips the prompt. Consent covers the seed hosts only;
`--allow-other-hosts` also permits hosts reached by links or redirects, including
robots.txt redirects. The prompt lists that flag and whether it is enabled.
Without it, external links and blocked page redirects are recorded but not fetched.

```bash
trugs-web crawl https://example.org --topic graphs
trugs-web build https://example.org --topic graphs --out web.trug.json
```

Answer **no** to try either command without contacting a host. Both then report
that crawling was declined and exit nonzero. After consent, `crawl` prints source
URLs; `build` crawls, extracts, resolves and scores a graph. Its default `mock`
provider returns canned entities for testing; it does not describe the page's
meaning. Use `map` for a folder. Real extraction uses the optional `llm` extra and
a configured provider key. Robots rules are checked with fail-open handling for
unavailable rules; consent boundaries still apply. The library's crawl functions
do not prompt: their caller must obtain consent and pass the host-scope option.

All commands have `--help`.

## Scope

This software does not include self-modifying TRUGS: graphs that change their
own structure while they run.

## License

Apache-2.0. [LICENSE](LICENSE) and [NOTICE](NOTICE) are preserved verbatim.
See [CHANGELOG.md](CHANGELOG.md) for changes and [ARCHITECTURE.md](ARCHITECTURE.md)
for the modules. Issues and contributions are welcome at
[TRUGS-LLC/TRUGS-WEB](https://github.com/TRUGS-LLC/TRUGS-WEB).
