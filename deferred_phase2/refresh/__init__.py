"""
TRUGS Web Refresh Sub-package

Persistent queries and diff-based updates for keeping TRUGs current.

Usage::

    from trugs_tools.web.refresh import (
        PersistentQuery,
        QueryStore,
        QueryRunner,
        QueryDiffResult,
        TrugDiff,
        diff_trugs,
        apply_diff,
    )
"""

from .persistent_query import (
    PersistentQuery,
    QueryStore,
    QueryRunner,
    QueryDiffResult,
)
from .diff import (
    TrugDiff,
    diff_trugs,
    apply_diff,
)

__all__ = [
    # persistent_query
    "PersistentQuery",
    "QueryStore",
    "QueryRunner",
    "QueryDiffResult",
    # diff
    "TrugDiff",
    "diff_trugs",
    "apply_diff",
]
