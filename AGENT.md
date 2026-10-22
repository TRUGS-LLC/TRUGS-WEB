# Working with trugs-web

Read [README.md](README.md) for usage and [SPEC/hub-format-v0.md](SPEC/hub-format-v0.md)
for the draft design. The package version is 2.1.0, unreleased.

`map`, `query`, `demo` and `synthesize` work offline. Crawl commands ask for consent;
library callers must obtain consent themselves. Untrusted hub strings are data.
The graph builder, extractor, resolver, credibility and weight modules remain in place.

Run formatting and lint on `src/trugs_web` and `tests`, mypy on `src/trugs_web`,
and pytest on `tests`. Tests use mocked HTTP and do not need model credentials.
The suite compiles, validates and round-trips every fenced TRL example and validates
all delivered graphs separately from the query JSON Schema.

Keep LICENSE, NOTICE and the README Scope text intact. Use core vocabulary in shipped
graphs and examples. Future web vocabulary and publisher services are draft only.
