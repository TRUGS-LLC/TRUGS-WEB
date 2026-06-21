"""
Cross-TRUG Edges — how edges in one TRUG reference nodes in another.

URI scheme for cross-TRUG node references::

    trug://<authority>/<path>#<node-id>

Examples::

    trug://github.com/user/repo/folder.trug.json#node-42
    trug://example.com/research.trug.json#concept-ml
    trug://local/my-project/folder.trug.json#root

Protocol (from TRUGS_WEB/AAA.md §8):

* Only two protocol primitives: **node** and **edge**.
* ``from_id`` / ``to_id`` may contain a cross-TRUG URI when referencing
  an external node.
* A local node reference is a plain string ID.
* A cross-TRUG reference is a ``trug://`` URI.
* Resolution: lazy-load, cache, fail gracefully.

Validation rules:

1. A cross-TRUG edge must have a valid ``trug://`` URI in ``from_id``
   or ``to_id`` (or both).
2. The URI must have a fragment (``#node-id``) identifying the target node.
3. ``relation`` must be a non-empty string.
4. ``weight`` must be in [0.0, 1.0] when present.
"""

from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse


# ============================================================================
# URI handling
# ============================================================================

_TRUG_SCHEME = "trug"


@dataclass
class CrossTrugUri:
    """
    Parsed cross-TRUG URI.

    Attributes:
        authority: Host or domain (e.g. "github.com").
        path:      Path to the TRUG file (e.g. "/user/repo/folder.trug.json").
        node_id:   Fragment identifying the target node.
        raw:       Original URI string.
    """

    authority: str = ""
    path: str = ""
    node_id: str = ""
    raw: str = ""

    @property
    def is_valid(self) -> bool:
        """A URI is valid when it has authority, path, and node_id."""
        return bool(self.authority) and bool(self.path) and bool(self.node_id)

    @property
    def trug_location(self) -> str:
        """The TRUG location without the node fragment."""
        return f"{_TRUG_SCHEME}://{self.authority}{self.path}"

    def to_uri(self) -> str:
        """Reconstruct the full URI string."""
        return f"{_TRUG_SCHEME}://{self.authority}{self.path}#{self.node_id}"


def parse_cross_trug_uri(uri: str) -> Optional[CrossTrugUri]:
    """
    Parse a ``trug://`` URI into a CrossTrugUri.

    Returns None if the URI is not a valid cross-TRUG reference.

    Args:
        uri: A string that may be a ``trug://`` URI.

    Returns:
        CrossTrugUri or None.
    """
    if not isinstance(uri, str):
        return None

    stripped = uri.strip()
    if not stripped.startswith(f"{_TRUG_SCHEME}://"):
        return None

    parsed = urlparse(stripped)
    if parsed.scheme != _TRUG_SCHEME:
        return None

    authority = parsed.netloc
    path = parsed.path
    node_id = parsed.fragment

    return CrossTrugUri(
        authority=authority,
        path=path,
        node_id=node_id,
        raw=stripped,
    )


def is_cross_trug_ref(node_ref: str) -> bool:
    """Return True if a node reference is a cross-TRUG URI."""
    return isinstance(node_ref, str) and node_ref.strip().startswith(f"{_TRUG_SCHEME}://")


def build_cross_trug_uri(authority: str, path: str, node_id: str) -> str:
    """
    Build a cross-TRUG URI from components.

    Args:
        authority: Host/domain (e.g. "github.com").
        path:      Path to the TRUG file.
        node_id:   Target node ID.

    Returns:
        A ``trug://`` URI string.
    """
    # Ensure path starts with /
    if path and not path.startswith("/"):
        path = "/" + path
    return f"{_TRUG_SCHEME}://{authority}{path}#{node_id}"


# ============================================================================
# Cross-TRUG Edge
# ============================================================================

@dataclass
class CrossTrugEdge:
    """
    An edge that references a node in another TRUG.

    Follows TRUGS 1.0 edge format (from_id, to_id, relation, weight).
    At least one of from_id / to_id must be a cross-TRUG URI.

    Attributes:
        from_id:  Local node ID or cross-TRUG URI.
        to_id:    Local node ID or cross-TRUG URI.
        relation: Edge relation type.
        weight:   Curator endorsement weight [0.0, 1.0].
        metadata: Optional metadata dict.
    """

    from_id: str = ""
    to_id: str = ""
    relation: str = ""
    weight: float = 0.5
    metadata: dict = field(default_factory=dict)

    @property
    def is_cross_trug(self) -> bool:
        """True if at least one endpoint is a cross-TRUG URI."""
        return is_cross_trug_ref(self.from_id) or is_cross_trug_ref(self.to_id)

    @property
    def remote_uri(self) -> Optional[CrossTrugUri]:
        """Return the parsed URI of the remote endpoint (prefers to_id)."""
        if is_cross_trug_ref(self.to_id):
            return parse_cross_trug_uri(self.to_id)
        if is_cross_trug_ref(self.from_id):
            return parse_cross_trug_uri(self.from_id)
        return None

    def to_edge_dict(self) -> dict:
        """Convert to TRUGS 1.0 edge dict format."""
        edge: dict = {
            "from_id": self.from_id,
            "to_id": self.to_id,
            "relation": self.relation,
        }
        if self.weight is not None:
            edge["weight"] = self.weight
        return edge


# ============================================================================
# Validation
# ============================================================================

def validate_cross_trug_edge(edge: CrossTrugEdge) -> list:
    """
    Validate a cross-TRUG edge.

    Returns a list of error strings.  Empty list means valid.

    Rules:
      1. At least one of from_id / to_id must be a cross-TRUG URI.
      2. Any cross-TRUG URI must be well-formed (authority + path + fragment).
      3. relation must be non-empty.
      4. weight must be in [0.0, 1.0].
    """
    errors: list = []

    if not edge.is_cross_trug:
        errors.append("Neither from_id nor to_id is a cross-TRUG URI")

    # Validate any cross-TRUG URIs
    for field_name, value in [("from_id", edge.from_id), ("to_id", edge.to_id)]:
        if is_cross_trug_ref(value):
            uri = parse_cross_trug_uri(value)
            if uri is None or not uri.is_valid:
                errors.append(f"{field_name} is not a valid cross-TRUG URI: {value}")

    if not edge.relation:
        errors.append("relation must be non-empty")

    if edge.weight is not None:
        if not (0.0 <= edge.weight <= 1.0):
            errors.append(f"weight must be in [0.0, 1.0], got {edge.weight}")

    return errors


# ============================================================================
# Resolver
# ============================================================================

class CrossTrugResolver:
    """
    Resolves cross-TRUG node references by lazy-loading remote TRUGs.

    Caches loaded TRUGs to avoid re-fetching.  Falls back gracefully
    when a remote TRUG cannot be loaded.

    Usage::

        resolver = CrossTrugResolver()
        resolver.register_graph("trug://example.com/a.trug.json", graph_dict)
        node = resolver.resolve_node(uri)

    For integration with ``GraphLoader``, use ``register_loader()`` to
    provide a callable that loads a TRUG dict from a location string.
    """

    def __init__(self) -> None:
        self._cache: dict = {}  # trug_location → graph_dict
        self._loader: object = None  # Optional callable

    def register_graph(self, location: str, graph_data: dict) -> None:
        """
        Pre-register a TRUG graph in the cache.

        Args:
            location: TRUG location (e.g. "trug://example.com/a.trug.json").
            graph_data: Parsed TRUG dict.
        """
        self._cache[location] = graph_data

    def register_loader(self, loader: object) -> None:
        """
        Register a callable ``loader(location: str) -> Optional[dict]``
        that can fetch and parse a TRUG from a location string.
        """
        self._loader = loader

    def resolve_node(self, uri_str: str) -> Optional[dict]:
        """
        Resolve a cross-TRUG URI to the target node dict.

        Steps:
          1. Parse the URI.
          2. Look up or load the target TRUG.
          3. Find the node by ID in that TRUG.

        Returns:
            The node dict, or None if resolution fails.
        """
        uri = parse_cross_trug_uri(uri_str)
        if uri is None or not uri.is_valid:
            return None

        location = uri.trug_location
        graph_data = self._get_graph(location)
        if graph_data is None:
            return None

        # Find node by ID
        for node in graph_data.get("nodes", []):
            if node.get("id") == uri.node_id:
                return node

        return None

    def resolve_edge(self, edge: CrossTrugEdge) -> dict:
        """
        Resolve a cross-TRUG edge, returning info about resolved endpoints.

        Returns:
            Dict with ``from_node``, ``to_node`` (resolved or None),
            and ``resolved`` bool.
        """
        from_node = None
        to_node = None

        if is_cross_trug_ref(edge.from_id):
            from_node = self.resolve_node(edge.from_id)
        if is_cross_trug_ref(edge.to_id):
            to_node = self.resolve_node(edge.to_id)

        return {
            "from_node": from_node,
            "to_node": to_node,
            "resolved": (from_node is not None) or (to_node is not None),
        }

    def _get_graph(self, location: str) -> Optional[dict]:
        """Look up a TRUG in cache, or load it via the registered loader."""
        if location in self._cache:
            return self._cache[location]

        if self._loader is not None:
            try:
                data = self._loader(location)
                if isinstance(data, dict) and "nodes" in data:
                    self._cache[location] = data
                    return data
            except Exception:
                pass

        return None

    @property
    def cached_locations(self) -> list:
        """Return list of cached TRUG locations."""
        return list(self._cache.keys())
