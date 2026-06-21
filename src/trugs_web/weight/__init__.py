"""
TRUGS Web Weight Sub-package

Query-time node importance computed from inbound edge counts across
loaded TRUGs.  All computations are read-time — never stored.

Usage::

    from trugs_tools.web.weight import (
        NodeTopology,
        compute_topology,
        rank_by_importance,
        find_convergence,
        compute_freshness,
    )
"""

from .topology import (
    NodeTopology,
    compute_topology,
    rank_by_importance,
    find_convergence,
    compute_freshness,
)

__all__ = [
    "NodeTopology",
    "compute_topology",
    "rank_by_importance",
    "find_convergence",
    "compute_freshness",
]
