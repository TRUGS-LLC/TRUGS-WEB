"""
Weight Topology — query-time node importance across loaded TRUGs.

From TRUGS_WEB/AAA.md §8:

    *"Node importance is computed at query time from inbound edge
    counts across loaded TRUGs — not stored."*

All computations are **read-time** and never mutate the input graphs.
No new dependencies.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ============================================================================
# Data structures
# ============================================================================


@dataclass
class NodeTopology:
    """
    Topology summary for a single node across one or more loaded TRUGs.

    Attributes:
        node_id:          Canonical node identifier.
        inbound_count:    Total number of inbound edges across all graphs.
        weighted_inbound: Sum of inbound edge weights.
        sources:          Set of TRUG names/IDs that contribute edges to
                          this node.
    """

    node_id: str
    inbound_count: int = 0
    weighted_inbound: float = 0.0
    sources: set = field(default_factory=set)


# ============================================================================
# Topology computation
# ============================================================================


def _graph_name(graph: dict) -> str:
    """Extract a human-usable name from a TRUG graph dict."""
    return graph.get("name", graph.get("id", "unknown"))


def compute_topology(graphs: list) -> dict:
    """
    Compute inbound edge topology across multiple loaded TRUGs.

    Args:
        graphs: List of TRUG graph dicts.

    Returns:
        ``{node_id: NodeTopology}`` mapping for every node that has at
        least one inbound edge.
    """
    topology: dict = {}

    for graph in graphs:
        gname = _graph_name(graph)
        for edge in graph.get("edges", []):
            to_id = edge.get("to_id", "")
            if not to_id:
                continue
            if to_id not in topology:
                topology[to_id] = NodeTopology(node_id=to_id)
            topo = topology[to_id]
            topo.inbound_count += 1
            topo.weighted_inbound += edge.get("weight", 0.5)
            topo.sources.add(gname)

    return topology


# ============================================================================
# Ranking & filtering
# ============================================================================


def rank_by_importance(
    topology: dict,
    min_inbound: int = 1,
) -> list:
    """
    Return nodes sorted by weighted inbound score (descending).

    Args:
        topology:    ``{node_id: NodeTopology}`` as returned by
                     :func:`compute_topology`.
        min_inbound: Minimum inbound count to be included (default 1).

    Returns:
        List of :class:`NodeTopology` sorted by ``weighted_inbound`` desc.
    """
    return sorted(
        (t for t in topology.values() if t.inbound_count >= min_inbound),
        key=lambda t: t.weighted_inbound,
        reverse=True,
    )


def find_convergence(
    topology: dict,
    min_sources: int = 2,
) -> list:
    """
    Find nodes endorsed by multiple independent TRUGs.

    Args:
        topology:    ``{node_id: NodeTopology}`` mapping.
        min_sources: Minimum number of distinct TRUG sources required.

    Returns:
        List of :class:`NodeTopology` with ``len(sources) >= min_sources``,
        sorted by number of sources descending then by weighted_inbound.
    """
    return sorted(
        (t for t in topology.values() if len(t.sources) >= min_sources),
        key=lambda t: (len(t.sources), t.weighted_inbound),
        reverse=True,
    )


# ============================================================================
# Freshness
# ============================================================================

_DEFAULT_HALF_LIFE_DAYS = 30.0


def compute_freshness(
    edge: dict,
    now: Optional[datetime] = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> float:
    """
    Time-based freshness decay from an edge's timestamp.

    Freshness is computed at **read time**, never stored.

    Uses exponential decay: ``freshness = 0.5 ** (age_days / half_life_days)``.
    An edge with no parseable timestamp gets the minimum freshness (0.0).

    Args:
        edge:           An edge dict.  Looks for ``"timestamp"`` or
                        ``"created"`` in the edge or its properties.
        now:            Reference time (defaults to ``datetime.now(UTC)``).
        half_life_days: Half-life for the decay curve (default 30 days).

    Returns:
        Float in ``[0.0, 1.0]``.
    """
    ts_str = (
        edge.get("timestamp")
        or edge.get("created")
        or edge.get("properties", {}).get("timestamp")
        or edge.get("properties", {}).get("created")
    )
    if not ts_str:
        return 0.0

    try:
        ts = datetime.fromisoformat(str(ts_str))
    except (ValueError, TypeError):
        return 0.0

    if now is None:
        now = datetime.now(timezone.utc)

    # Ensure both are offset-aware for comparison
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_days = max((now - ts).total_seconds() / 86400.0, 0.0)
    freshness = 0.5 ** (age_days / half_life_days)
    return round(min(max(freshness, 0.0), 1.0), 6)
