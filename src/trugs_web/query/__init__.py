"""
TRUGS Web Query Sub-package

Provides graph loading, traversal, and report synthesis for
TRUGS 1.0 research graphs produced by TRUGSWebGraphBuilder.

Usage::

    from trugs_tools.web.query import GraphLoader, GraphTraverser, ReportSynthesizer

    graph = GraphLoader().load(path)
    traverser = GraphTraverser(graph)
    result = traverser.concept_sources("machine learning")
"""

from .loader import Node, Edge, GraphMeta, Graph, GraphLoader, load_graph
from .traverse import TraversalResult, GraphTraverser, query_graph
from .synthesize import Finding, Report, ReportSynthesizer, generate_report

__all__ = [
    # loader
    "Node",
    "Edge",
    "GraphMeta",
    "Graph",
    "GraphLoader",
    "load_graph",
    # traverse
    "TraversalResult",
    "GraphTraverser",
    "query_graph",
    # synthesize
    "Finding",
    "Report",
    "ReportSynthesizer",
    "generate_report",
]
