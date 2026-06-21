"""
Diff-based Updates — compare two TRUG graph dicts and produce a changeset.

Pure functions for computing minimal changesets between TRUG versions and
applying those changesets to produce updated graphs.

Design constraints (TRUGS_WEB/AAA.md §8):
  - All computations are pure — no mutation of input graphs.
  - No new dependencies.
"""

import copy
from dataclasses import dataclass, field


# ============================================================================
# Data structures
# ============================================================================

@dataclass
class TrugDiff:
    """
    Minimal changeset between two versions of a TRUG graph.

    Attributes:
        nodes_added:      Nodes present in *new* but not *old*.
        nodes_removed:    Nodes present in *old* but not *new*.
        nodes_modified:   Nodes present in both but with changed properties.
                          Each entry is ``{"id": ..., "old": ..., "new": ...}``.
        edges_added:      Edges present in *new* but not *old*.
        edges_removed:    Edges present in *old* but not *new*.
        edges_reweighted: Edges present in both but with a weight change
                          exceeding *threshold*.  Each entry is
                          ``{"edge": ..., "old_weight": ..., "new_weight": ...}``.
    """

    nodes_added: list = field(default_factory=list)
    nodes_removed: list = field(default_factory=list)
    nodes_modified: list = field(default_factory=list)
    edges_added: list = field(default_factory=list)
    edges_removed: list = field(default_factory=list)
    edges_reweighted: list = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True when the diff contains no changes."""
        return (
            not self.nodes_added
            and not self.nodes_removed
            and not self.nodes_modified
            and not self.edges_added
            and not self.edges_removed
            and not self.edges_reweighted
        )

    @property
    def summary(self) -> str:
        """One-line human-readable summary of changes."""
        parts: list = []
        if self.nodes_added:
            parts.append(f"+{len(self.nodes_added)} nodes")
        if self.nodes_removed:
            parts.append(f"-{len(self.nodes_removed)} nodes")
        if self.nodes_modified:
            parts.append(f"~{len(self.nodes_modified)} nodes")
        if self.edges_added:
            parts.append(f"+{len(self.edges_added)} edges")
        if self.edges_removed:
            parts.append(f"-{len(self.edges_removed)} edges")
        if self.edges_reweighted:
            parts.append(f"~{len(self.edges_reweighted)} edges")
        return ", ".join(parts) if parts else "no changes"


# ============================================================================
# Diff computation
# ============================================================================

def _edge_key(edge: dict) -> tuple:
    """Canonical key for matching edges: (from_id, to_id, relation)."""
    return (edge.get("from_id", ""), edge.get("to_id", ""), edge.get("relation", ""))


def _node_properties_differ(old_node: dict, new_node: dict) -> bool:
    """Return True when meaningful node fields have changed."""
    # Compare type + properties + metric_level (ignore structural: parent_id, contains, dimension)
    for key in ("type", "properties", "metric_level"):
        if old_node.get(key) != new_node.get(key):
            return True
    return False


def diff_trugs(
    old_graph: dict,
    new_graph: dict,
    weight_threshold: float = 0.05,
) -> TrugDiff:
    """
    Compare two TRUG graph dicts and produce a minimal changeset.

    Args:
        old_graph:        Previous version of the TRUG graph dict.
        new_graph:        Current version of the TRUG graph dict.
        weight_threshold: Minimum absolute weight change to count as
                          a reweight (default 0.05).

    Returns:
        A :class:`TrugDiff` describing what changed.
    """
    result = TrugDiff()

    # ----- Nodes -----
    old_nodes = {n["id"]: n for n in old_graph.get("nodes", [])}
    new_nodes = {n["id"]: n for n in new_graph.get("nodes", [])}

    old_ids = set(old_nodes)
    new_ids = set(new_nodes)

    for nid in sorted(new_ids - old_ids):
        result.nodes_added.append(new_nodes[nid])
    for nid in sorted(old_ids - new_ids):
        result.nodes_removed.append(old_nodes[nid])
    for nid in sorted(old_ids & new_ids):
        if _node_properties_differ(old_nodes[nid], new_nodes[nid]):
            result.nodes_modified.append({
                "id": nid,
                "old": old_nodes[nid],
                "new": new_nodes[nid],
            })

    # ----- Edges -----
    old_edges = {_edge_key(e): e for e in old_graph.get("edges", [])}
    new_edges = {_edge_key(e): e for e in new_graph.get("edges", [])}

    old_ekeys = set(old_edges)
    new_ekeys = set(new_edges)

    for ek in sorted(new_ekeys - old_ekeys):
        result.edges_added.append(new_edges[ek])
    for ek in sorted(old_ekeys - new_ekeys):
        result.edges_removed.append(old_edges[ek])
    for ek in sorted(old_ekeys & new_ekeys):
        old_w = old_edges[ek].get("weight")
        new_w = new_edges[ek].get("weight")
        if old_w is not None and new_w is not None:
            if abs(new_w - old_w) >= weight_threshold:
                result.edges_reweighted.append({
                    "edge": new_edges[ek],
                    "old_weight": old_w,
                    "new_weight": new_w,
                })

    return result


# ============================================================================
# Apply diff
# ============================================================================

def apply_diff(base_graph: dict, diff: TrugDiff) -> dict:
    """
    Produce an updated graph by applying *diff* to *base_graph*.

    This is a **pure** function — *base_graph* is not mutated.

    Args:
        base_graph: The original TRUG graph dict.
        diff:       A :class:`TrugDiff` to apply.

    Returns:
        A new graph dict with the diff applied.
    """
    result = copy.deepcopy(base_graph)

    # Remove nodes
    removed_ids = {n["id"] for n in diff.nodes_removed}
    result["nodes"] = [n for n in result.get("nodes", []) if n["id"] not in removed_ids]

    # Add nodes
    existing_ids = {n["id"] for n in result.get("nodes", [])}
    for node in diff.nodes_added:
        if node["id"] not in existing_ids:
            result["nodes"].append(copy.deepcopy(node))
            existing_ids.add(node["id"])

    # Modify nodes
    mod_map = {m["id"]: m["new"] for m in diff.nodes_modified}
    result["nodes"] = [
        copy.deepcopy(mod_map[n["id"]]) if n["id"] in mod_map else n
        for n in result["nodes"]
    ]

    # Remove edges
    removed_ekeys = {_edge_key(e) for e in diff.edges_removed}
    result["edges"] = [
        e for e in result.get("edges", []) if _edge_key(e) not in removed_ekeys
    ]

    # Add edges
    existing_ekeys = {_edge_key(e) for e in result.get("edges", [])}
    for edge in diff.edges_added:
        ek = _edge_key(edge)
        if ek not in existing_ekeys:
            result["edges"].append(copy.deepcopy(edge))
            existing_ekeys.add(ek)

    # Reweight edges
    reweight_map = {
        _edge_key(rw["edge"]): rw["new_weight"]
        for rw in diff.edges_reweighted
    }
    for edge in result["edges"]:
        ek = _edge_key(edge)
        if ek in reweight_map:
            edge["weight"] = reweight_map[ek]

    return result
