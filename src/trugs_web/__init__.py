"""
trugs-web — a one-way, passive web-to-TRUG builder.

Crawl web sources, extract entities/relations (LLM-backed), resolve, score credibility, and
build a passive TRUGS knowledge graph for querying. It builds graphs; it never closes the
self-developing loop (the reserved patent mechanism).

v1 ships: ingestion (crawler, extractor, resolver, credibility, graph_builder), query, weight.
Hub federation and refresh are deferred to Phase 2 (see deferred_phase2/).

Optional dependencies:
  - pip install "trugs-web[web]"   → httpx, beautifulsoup4, lxml   (crawling)
  - pip install "trugs-web[llm]"   → anthropic, openai             (LLM extraction)
"""

__version__ = "2.0.0"

from .crawler import Source, SourceDiscoverer, discover_sources
from .extractor import (
    Entity,
    Relation,
    LLMClient,
    MockLLMClient,
    AnthropicClient,
    OpenAIClient,
    EntityExtractor,
    RelationExtractor,
    CitationExtractor,
    create_extractor,
)
from .resolver import (
    ResolvedEntity,
    EntityResolver,
    CrossReferenceMapper,
    resolve_entities,
)
from .credibility import (
    CredibilityFactors,
    CredibilityScorer,
    calculate_credibility,
    score_edge_weight,
)
from .graph_builder import (
    TRUGSWebGraphBuilder,
    build_graph,
    load_graph,
    url_to_id,
    make_id,
)
from .query import (
    Node,
    Edge,
    GraphMeta,
    Graph,
    GraphLoader,
    load_graph as load_query_graph,
    TraversalResult,
    GraphTraverser,
    query_graph,
    Finding,
    Report,
    ReportSynthesizer,
    generate_report,
)
from .weight import (
    NodeTopology,
    compute_topology,
    rank_by_importance,
    find_convergence,
    compute_freshness,
)

__all__ = [
    "__version__",
    # crawler
    "Source",
    "SourceDiscoverer",
    "discover_sources",
    # extractor
    "Entity",
    "Relation",
    "LLMClient",
    "MockLLMClient",
    "AnthropicClient",
    "OpenAIClient",
    "EntityExtractor",
    "RelationExtractor",
    "CitationExtractor",
    "create_extractor",
    # resolver
    "ResolvedEntity",
    "EntityResolver",
    "CrossReferenceMapper",
    "resolve_entities",
    # credibility
    "CredibilityFactors",
    "CredibilityScorer",
    "calculate_credibility",
    "score_edge_weight",
    # graph_builder
    "TRUGSWebGraphBuilder",
    "build_graph",
    "load_graph",
    "url_to_id",
    "make_id",
    # query
    "Node",
    "Edge",
    "GraphMeta",
    "Graph",
    "GraphLoader",
    "load_query_graph",
    "TraversalResult",
    "GraphTraverser",
    "query_graph",
    "Finding",
    "Report",
    "ReportSynthesizer",
    "generate_report",
    # weight
    "NodeTopology",
    "compute_topology",
    "rank_by_importance",
    "find_convergence",
    "compute_freshness",
]
