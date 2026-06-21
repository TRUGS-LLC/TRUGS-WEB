"""trugs-web command-line interface (AAA #2295 SP3).

trugs-web is a ONE-WAY, passive web-to-TRUG builder: it crawls sources and emits passive
TRUGS graphs for querying. It never closes the self-developing loop (the reserved patent
mechanism). API keys are read from the environment (ANTHROPIC_API_KEY / OPENAI_API_KEY).

Verbs:
  crawl       discover sources from seed URLs (no LLM)
  build       crawl + extract + resolve + score → a passive TRUG graph
  query       traverse a built graph and print findings
  synthesize  traverse a built graph and render a markdown report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from ._safety import get_logger

logger = get_logger()

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trugs-web",
        description="Crawl web sources and build passive TRUGS knowledge graphs "
        "(one-way; never closes the self-developing loop).",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="verb", metavar="{crawl,build,query,synthesize}")

    p_crawl = sub.add_parser(
        "crawl",
        help="discover sources from seed URLs (no LLM)",
        epilog="example: trugs-web crawl https://example.com --topic acupuncture",
    )
    p_crawl.add_argument("seed_urls", nargs="+", help="seed URL(s) to crawl")
    p_crawl.add_argument("--topic", default="", help="topic hint")
    p_crawl.add_argument(
        "--max-sources", type=int, default=20, help="max sources to discover"
    )

    p_build = sub.add_parser(
        "build",
        help="crawl + extract → a passive TRUG graph",
        epilog="example: trugs-web build https://example.com --topic acupuncture --out graph.trug.json",
    )
    p_build.add_argument("seed_urls", nargs="+", help="seed URL(s) to crawl")
    p_build.add_argument("--topic", required=True, help="research topic")
    p_build.add_argument(
        "--out", help="write the TRUG to this path (else print a summary)"
    )
    p_build.add_argument(
        "--provider",
        default="mock",
        choices=["mock", "anthropic", "openai"],
        help="LLM provider for extraction (key from $ANTHROPIC_API_KEY/$OPENAI_API_KEY)",
    )
    p_build.add_argument("--model", help="model override")

    p_query = sub.add_parser(
        "query",
        help="traverse a built graph and print findings",
        epilog="example: trugs-web query graph.trug.json --q 'sources for acupuncture'",
    )
    p_query.add_argument("graph", help="path to a .trug.json graph built by `build`")
    p_query.add_argument("--q", required=True, dest="query", help="query string")
    p_query.add_argument(
        "--min-weight", type=float, default=0.5, help="min edge weight"
    )

    p_syn = sub.add_parser(
        "synthesize",
        help="render a markdown report from a built graph",
        epilog="example: trugs-web synthesize graph.trug.json --q 'acupuncture evidence' --out report.md",
    )
    p_syn.add_argument("graph", help="path to a .trug.json graph built by `build`")
    p_syn.add_argument("--q", required=True, dest="query", help="query string")
    p_syn.add_argument(
        "--out", help="write the markdown report to this path (else stdout)"
    )
    p_syn.add_argument("--min-weight", type=float, default=0.5, help="min edge weight")

    return parser


def _cmd_crawl(args) -> int:
    from .crawler import discover_sources

    sources = asyncio.run(
        discover_sources(args.seed_urls, topic=args.topic, max_sources=args.max_sources)
    )
    print(f"discovered {len(sources)} source(s):")
    for s in sources:
        print(f"  [{s.source_type}] {s.url}")
    return 0


def _cmd_build(args) -> int:
    from .graph_builder import build_graph

    builder = asyncio.run(
        build_graph(
            topic=args.topic,
            seed_urls=args.seed_urls,
            llm_provider=args.provider,
            model=args.model,
            output_path=args.out,
            validate=True,
        )
    )
    graph = builder.graph
    n_nodes, n_edges = len(graph.get("nodes", [])), len(graph.get("edges", []))
    if args.out:
        print(f"wrote {args.out}: {n_nodes} nodes, {n_edges} edges")
    else:
        print(f"built graph: {n_nodes} nodes, {n_edges} edges (use --out to save)")
    return 0


def _cmd_query(args) -> int:
    from .query import load_graph, query_graph

    graph = load_graph(args.graph)
    result = query_graph(graph, args.query, min_weight=args.min_weight)
    print(
        json.dumps(result, indent=2, default=str)
        if not isinstance(result, str)
        else result
    )
    return 0


def _synthesize(args) -> int:
    from .query import load_graph
    from .query.synthesize import generate_report

    graph = load_graph(args.graph)
    report = asyncio.run(
        generate_report(
            graph, args.query, min_weight=args.min_weight, output_path=args.out
        )
    )
    md = report.to_markdown() if hasattr(report, "to_markdown") else str(report)
    if args.out:
        print(f"wrote {args.out}")
    else:
        print(md)
    return 0


_HANDLERS = {
    "crawl": _cmd_crawl,
    "build": _cmd_build,
    "query": _cmd_query,
    "synthesize": _synthesize,
}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "version", False):
        from trugs_web import __version__

        print(f"trugs-web {__version__}")
        return 0
    if not getattr(args, "verb", None):
        parser.print_help()
        return 0

    try:
        return _HANDLERS[args.verb](args)
    except (
        Exception
    ) as exc:  # surface the failure with context instead of a bare traceback
        logger.error("trugs-web %s failed: %s", args.verb, exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
