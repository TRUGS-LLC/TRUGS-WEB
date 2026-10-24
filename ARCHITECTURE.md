# Architecture

`folder.trug.json` indexes the package. This document describes its behavior.

`cli.py` routes `map`, `query`, `demo`, `crawl`, `build` and `synthesize`.
The map, query, demo and report paths work offline. The command line obtains
consent before calling either web path. The library leaves consent to its caller.

`map.py` reads folder contents with standard-library parsers and ignore matching.
It records relative paths, content digests, links and local import edges. It
validates and decompiles the core graph before returning it. It never follows
symlinks or fetches a linked resource.

`crawler.py` keeps discovered links and checks each HTTP request, including each
redirect, against the seed hosts unless the caller allows other hosts. Robots
rules are cached during a discovery run; unavailable rules fail open, within
that host boundary. Batches can run in parallel. Delay and retry options do not
constitute a per-domain rate guarantee.

`graph_builder.py` retains the discover, extract, resolve, score pipeline.
`extractor.py`, `resolver.py`, `credibility.py` and `weight/` retain their existing
roles. Mock extraction returns canned content and is intended for testing.
Model extraction and HTTP parsing use optional extras. `_safety.py` provides
logging, retry and credential helpers; its standalone cost guard must be used
explicitly by a caller that needs a budget.

`query/loader.py` and `query/traverse.py` load and traverse existing graphs.
`query/output.py` projects traversal dataclasses into the JSON Schema shape or a
readable text list; it does not alter traversal or assign new rankings.
`query/synthesize.py` retains markdown report generation.

`data/` inside the installed package holds the sample folder, unsigned prior-art
hub and query schema. `demo` reads only that installed hub. The top-level
`examples/`, `hubs/` and `schema/` copies are checked for equality with package
data by the test suite. The draft in `SPEC/` describes future hub services;
none of those services are implied by the core sample.

Graph validation uses trugs-tools 2.4.0 per graph. The query JSON Schema is checked
as a schema, independently of the graph validator. Every fenced TRL example is
compiled, validated and tested for a stable round trip after normalisation.
