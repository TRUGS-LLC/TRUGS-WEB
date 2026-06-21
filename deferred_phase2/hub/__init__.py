"""
TRUGS Web Hub Sub-package

Hub discovery, qualifying interest matching, and cross-TRUG edge
management for linking TRUGs together on the open web.

A hub is a **pattern**, not a primitive: any TRUG whose root node carries
a ``qualifying_interest`` and weighted edges can act as a hub.

Usage::

    from trugs_tools.web.hub import (
        QualifyingInterest,
        match_interest,
        HubAgent,
        CrossTrugEdge,
        parse_cross_trug_uri,
        Orchestrator,
    )
"""

from .qualifying_interest import (
    QualifyingInterest,
    parse_qualifying_interest,
    match_interest,
    rank_matches,
)
from .hub_agent import (
    HubCandidate,
    HubAgent,
)
from .cross_trug_edges import (
    CrossTrugUri,
    CrossTrugEdge,
    parse_cross_trug_uri,
    is_cross_trug_ref,
    build_cross_trug_uri,
    validate_cross_trug_edge,
    CrossTrugResolver,
)
from .orchestrate import (
    Orchestrator,
    PipelineResult,
)

__all__ = [
    # qualifying_interest
    "QualifyingInterest",
    "parse_qualifying_interest",
    "match_interest",
    "rank_matches",
    # hub_agent
    "HubCandidate",
    "HubAgent",
    # cross_trug_edges
    "CrossTrugUri",
    "CrossTrugEdge",
    "parse_cross_trug_uri",
    "is_cross_trug_ref",
    "build_cross_trug_uri",
    "validate_cross_trug_edge",
    "CrossTrugResolver",
    # orchestrate
    "Orchestrator",
    "PipelineResult",
]
