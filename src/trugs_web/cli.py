"""Describe folders, query graphs and crawl sources with consent."""

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
        description="Describe folders, query graphs and build research graphs from web sources.",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(
        dest="verb", metavar="{map,crawl,build,query,synthesize,demo}"
    )

    p_map = sub.add_parser(
        "map", help="describe a folder without network or model calls"
    )
    p_map.add_argument("folder", help="folder to describe")
    p_map.add_argument(
        "--out",
        help="write JSON here (default: stdout); use a path outside the mapped folder",
    )
    p_map.add_argument(
        "--include-hidden",
        action="store_true",
        help="include hidden folders; .git is always skipped",
    )
    sub.add_parser("demo", help="query the installed prior-art hub, offline")

    p_crawl = sub.add_parser(
        "crawl",
        help="discover sources from seed URLs (no LLM)",
        epilog="example: trugs-web crawl https://example.com --topic acupuncture",
    )
    p_crawl.add_argument("seed_urls", nargs="+", help="seed URL(s) to crawl")
    p_crawl.add_argument("--topic", default="", help="topic hint")
    p_crawl.add_argument(
        "--max-sources",
        type=int,
        default=20,
        help="source-count threshold checked before each batch; final batch may exceed it",
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

    for command in (p_crawl, p_build):
        command.add_argument(
            "--yes", action="store_true", help="consent without a terminal prompt"
        )
        command.add_argument(
            "--allow-other-hosts",
            action="store_true",
            help="also permit requests to hosts reached by links and redirects",
        )

    p_query = sub.add_parser(
        "query",
        help="traverse a built graph and print findings",
        epilog="example: trugs-web query graph.trug.json --q 'sources for acupuncture'",
    )
    p_query.add_argument("graph", help="path to a .trug.json graph")
    p_query.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="output format (default: json)",
    )
    p_query.add_argument("--q", required=True, dest="query", help="query string")
    p_query.add_argument(
        "--min-weight",
        type=float,
        default=0.5,
        help="minimum node credibility in high-credibility mode; minimum edge weight otherwise",
    )

    p_syn = sub.add_parser(
        "synthesize",
        help="render a markdown report from a built graph",
        epilog="example: trugs-web synthesize graph.trug.json --q 'acupuncture evidence' --out report.md",
    )
    p_syn.add_argument("graph", help="path to a .trug.json graph")
    p_syn.add_argument("--q", required=True, dest="query", help="query string")
    p_syn.add_argument(
        "--out", help="write the markdown report to this path (else stdout)"
    )
    p_syn.add_argument(
        "--min-weight",
        type=float,
        default=0.5,
        help="minimum node credibility in high-credibility mode; minimum edge weight otherwise",
    )

    return parser


def _consent(args) -> None:
    from .crawler import seed_hosts

    hosts = sorted(seed_hosts(args.seed_urls))
    if args.yes:
        return
    print("Crawl seed hosts: " + ", ".join(hosts), file=sys.stderr)
    print(
        "--allow-other-hosts permits requests to other hosts reached by links or redirects "
        + ("(enabled)." if args.allow_other_hosts else "(disabled)."),
        file=sys.stderr,
    )
    if not sys.stdin.isatty():
        raise ValueError("Crawling needs a terminal and consent, or --yes")
    print(
        "Contact these hosts? Type yes to continue: ",
        end="",
        file=sys.stderr,
        flush=True,
    )
    try:
        answer = input()
    except EOFError:
        answer = ""
    if answer.strip().lower() != "yes":
        raise ValueError("Crawling declined")


def _cmd_map(args) -> int:
    from pathlib import Path
    from .map import map_folder

    if args.out and Path(args.out).resolve().is_relative_to(
        Path(args.folder).resolve()
    ):
        raise ValueError(
            "Choose --out outside the mapped folder to keep repeated maps stable"
        )
    data = (
        json.dumps(
            map_folder(args.folder, include_hidden=args.include_hidden),
            indent=2,
            ensure_ascii=True,
        )
        + "\n"
    )
    if args.out:
        Path(args.out).write_text(data, encoding="utf-8")
    else:
        print(data, end="")
    print(
        "Open the graph in the viewer: https://trugs-llc.github.io/TRUGS-VIEWER/",
        file=sys.stderr,
    )
    return 0


def _cmd_demo(args) -> int:
    from importlib.resources import files
    from .query import load_graph, query_graph
    from .query.output import result_object

    resource = files("trugs_web").joinpath(
        "data/hubs/semantic-and-executable-graphs/graph.trug.json"
    )
    graph = load_graph(str(resource))
    print(
        json.dumps(
            result_object(query_graph(graph, "best sources", min_weight=0)), indent=2
        )
    )
    return 0


def _cmd_crawl(args) -> int:
    from .crawler import discover_sources

    _consent(args)
    sources = asyncio.run(
        discover_sources(
            args.seed_urls,
            topic=args.topic,
            max_sources=args.max_sources,
            allow_other_hosts=args.allow_other_hosts,
        )
    )
    print(f"discovered {len(sources)} source(s):")
    for s in sources:
        print(f"  [{s.source_type}] {s.url}")
        for link in sorted(s.outbound_links):
            print(f"    link: {link}")
    return 0


def _cmd_build(args) -> int:
    from .graph_builder import build_graph

    _consent(args)
    builder = asyncio.run(
        build_graph(
            topic=args.topic,
            seed_urls=args.seed_urls,
            llm_provider=args.provider,
            model=args.model,
            output_path=args.out,
            validate=True,
            allow_other_hosts=args.allow_other_hosts,
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
    from .query.output import result_object, result_text

    print(
        json.dumps(result_object(result), indent=2)
        if args.format == "json"
        else result_text(result)
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
    "map": _cmd_map,
    "demo": _cmd_demo,
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
