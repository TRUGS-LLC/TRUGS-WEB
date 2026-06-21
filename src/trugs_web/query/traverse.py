"""
Graph Traversal Module

Provides high-level traversal patterns for answering queries.
"""

from dataclasses import dataclass, field


@dataclass
class TraversalResult:
    """Result of a graph traversal operation."""

    query: str
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    paths: list = field(default_factory=list)

    # Aggregated info
    total_weight: float = 0.0
    avg_weight: float = 0.0
    high_credibility_count: int = 0  # nodes with credibility >= 0.7

    def __post_init__(self):
        """Calculate aggregated stats."""
        if self.edges:
            self.total_weight = sum(e.weight for e in self.edges)
            self.avg_weight = self.total_weight / len(self.edges)

        self.high_credibility_count = sum(1 for n in self.nodes if n.credibility >= 0.7)

    @property
    def is_empty(self):
        return len(self.nodes) == 0

    def top_nodes(self, n=5):
        """Get top N nodes by credibility."""
        sorted_nodes = sorted(self.nodes, key=lambda x: x.credibility, reverse=True)
        return sorted_nodes[:n]

    def top_edges(self, n=5):
        """Get top N edges by weight."""
        sorted_edges = sorted(self.edges, key=lambda x: x.weight, reverse=True)
        return sorted_edges[:n]


class GraphTraverser:
    """
    High-level traversal patterns for query answering.

    Patterns:
    - concept_sources: Find sources that define/discuss a concept
    - related_concepts: Find concepts related to a given concept
    - citation_chain: Find citation path between sources
    - find_by_relation: Find all edges of a specific relation type
    - high_credibility_sources: Find high-credibility sources
    - weighted_consensus: Find claims with multi-source support
    - alternatives: Find alternatives to a given node
    """

    def __init__(self, graph):
        self.graph = graph

    def concept_sources(self, concept, min_weight=0.5):
        """
        Find sources that define or discuss a concept.

        Looks for nodes with matching name/description and follows
        incoming edges (sources pointing to the concept).
        """
        concept_nodes = self.graph.search_nodes(concept)

        if not concept_nodes:
            return TraversalResult(query=f"concept_sources({concept})")

        all_sources = []
        all_edges = []

        for concept_node in concept_nodes:
            edges = self.graph.get_incoming(
                concept_node.id,
                min_weight=min_weight,
            )

            for edge in edges:
                source = self.graph.get_node(edge.from_id)
                if source and source not in all_sources:
                    all_sources.append(source)
                    all_edges.append(edge)

        # Sort by edge weight
        paired = list(zip(all_sources, all_edges))
        paired.sort(key=lambda x: x[1].weight, reverse=True)

        if paired:
            all_sources, all_edges = zip(*paired)
            all_sources = list(all_sources)
            all_edges = list(all_edges)

        return TraversalResult(
            query=f"concept_sources({concept})",
            nodes=all_sources,
            edges=all_edges,
        )

    def related_concepts(
        self,
        concept,
        relation_types=None,
        min_weight=0.3,
        max_depth=2,
    ):
        """
        Find concepts related to a given concept.

        Follows edges of specified types (or all types) to find
        related concepts within max_depth hops.
        """
        concept_nodes = self.graph.search_nodes(concept)

        if not concept_nodes:
            return TraversalResult(query=f"related_concepts({concept})")

        all_related = []
        all_edges = []

        for start_node in concept_nodes:
            # Traverse outgoing
            for node, edge, depth in self.graph.traverse(
                start_node.id,
                direction="outgoing",
                min_weight=min_weight,
                max_depth=max_depth,
            ):
                if relation_types is None or edge.relation in relation_types:
                    if node not in all_related:
                        all_related.append(node)
                        all_edges.append(edge)

            # Traverse incoming
            for node, edge, depth in self.graph.traverse(
                start_node.id,
                direction="incoming",
                min_weight=min_weight,
                max_depth=max_depth,
            ):
                if relation_types is None or edge.relation in relation_types:
                    if node not in all_related:
                        all_related.append(node)
                        all_edges.append(edge)

        return TraversalResult(
            query=f"related_concepts({concept})",
            nodes=all_related,
            edges=all_edges,
        )

    def citation_chain(self, source_id, target_id, max_depth=5):
        """Find citation path between two sources."""
        path = self.graph.find_path(source_id, target_id, max_depth)

        if path is None:
            return TraversalResult(query=f"citation_chain({source_id} → {target_id})")

        nodes = [p[0] for p in path]
        edges = [p[1] for p in path]

        return TraversalResult(
            query=f"citation_chain({source_id} → {target_id})",
            nodes=nodes,
            edges=edges,
            paths=[path],
        )

    def find_by_relation(self, relation, min_weight=0.5):
        """
        Find all edges of a specific relation type.

        Useful for finding:
        - All CONTRADICTS edges
        - All SUPPORTS edges
        - All ALTERNATIVE_TO edges
        """
        edges = self.graph.get_edges(relation=relation, min_weight=min_weight)

        node_ids = set()
        for edge in edges:
            node_ids.add(edge.from_id)
            node_ids.add(edge.to_id)

        nodes = [self.graph.get_node(nid) for nid in node_ids]
        nodes = [n for n in nodes if n is not None]

        return TraversalResult(
            query=f"find_by_relation({relation})",
            nodes=nodes,
            edges=edges,
        )

    def high_credibility_sources(self, min_weight=0.7, node_type=None):
        """Find high-credibility sources in the graph."""
        nodes = self.graph.nodes

        if node_type:
            nodes = [n for n in nodes if n.type == node_type]

        high_cred = [n for n in nodes if n.credibility >= min_weight]
        high_cred.sort(key=lambda n: n.credibility, reverse=True)

        return TraversalResult(
            query=f"high_credibility_sources(min={min_weight})",
            nodes=high_cred,
        )

    def weighted_consensus(self, concept, min_sources=2, min_weight=0.5):
        """
        Find concepts/claims supported by multiple credible sources.

        Returns nodes that have multiple incoming edges from
        high-credibility sources.
        """
        concept_nodes = self.graph.search_nodes(concept)

        consensus_nodes = []
        consensus_edges = []

        for node in concept_nodes:
            edges = self.graph.get_incoming(node.id, min_weight=min_weight)

            if len(edges) >= min_sources:
                consensus_nodes.append(node)
                consensus_edges.extend(edges)

        return TraversalResult(
            query=f"weighted_consensus({concept}, min_sources={min_sources})",
            nodes=consensus_nodes,
            edges=consensus_edges,
        )

    def alternatives(self, node_id, min_weight=0.3):
        """
        Find alternatives to a given node (tool, approach, etc.).

        Looks for ALTERNATIVE_TO edges in both directions.
        """
        alternatives = []
        alt_edges = []

        # Outgoing ALTERNATIVE_TO
        for edge in self.graph.get_outgoing(node_id, "ALTERNATIVE_TO", min_weight):
            node = self.graph.get_node(edge.to_id)
            if node:
                alternatives.append(node)
                alt_edges.append(edge)

        # Incoming ALTERNATIVE_TO
        for edge in self.graph.get_incoming(node_id, "ALTERNATIVE_TO", min_weight):
            node = self.graph.get_node(edge.from_id)
            if node:
                alternatives.append(node)
                alt_edges.append(edge)

        return TraversalResult(
            query=f"alternatives({node_id})",
            nodes=alternatives,
            edges=alt_edges,
        )


def query_graph(graph, query, min_weight=0.5):
    """
    Simple query interface for graph traversal.

    Routes keyword-based queries to the appropriate traversal pattern.
    """
    traverser = GraphTraverser(graph)
    query_lower = query.lower()

    if "alternatives to" in query_lower:
        target = query_lower.replace("alternatives to", "").strip()
        nodes = graph.search_nodes(target)
        if nodes:
            return traverser.alternatives(nodes[0].id, min_weight)

    if "high credibility" in query_lower or "best sources" in query_lower:
        return traverser.high_credibility_sources(min_weight)

    if "contradictions" in query_lower or "conflicts" in query_lower:
        return traverser.find_by_relation("CONTRADICTS", min_weight)

    # Default: search for concept sources
    return traverser.concept_sources(query, min_weight)
