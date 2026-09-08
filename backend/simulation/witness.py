"""Graph-state witness hashing — extends the existing simulate-to-execute diff-hash binding
(backend/simulation/engine.py hashes the proposed diff text; backend/execution/sandbox.py re-hashes
and refuses to run on mismatch) to also cover the DEPENDENCY SUBGRAPH the simulation reasoned about,
not just the diff itself.

The diff-hash alone only proves "the code change about to run is byte-identical to what was
simulated" — it says nothing about whether the SURROUNDING graph (the files/symbols the blast-radius
analysis found downstream) has moved since. A dependency could be renamed, a symbol deleted, or an
edge added between simulation and execution without the diff text changing at all, silently
invalidating the blast-radius conclusion the PASSED verdict was based on. Hashing the witnessed state
of that subgraph at simulation time, and refusing execution if it drifted, closes that gap —
this is the code-knowledge-graph-specific analogue of a server ETag / optimistic-concurrency token,
scoped to the exact set of nodes a decision actually depended on rather than one server-wide version.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID


def hash_graph_state(node_ids: set[UUID], *, graph: Any) -> str:
    """A stable hash of the current properties of exactly these graph nodes — the ids a
    blast-radius traversal actually touched (both the target and everything downstream), not the
    whole graph. Order-independent (sorted by id) so the same node set always hashes the same way
    regardless of how the graph happens to iterate them."""
    if not node_ids:
        return hashlib.sha256(b"empty").hexdigest()
    wanted = {str(nid) for nid in node_ids}
    relevant = sorted(
        (
            {"id": str(n.id), "node_type": n.node_type, "properties": n.properties}
            for n in graph.list_nodes()
            if str(n.id) in wanted
        ),
        key=lambda d: d["id"],
    )
    payload = json.dumps(relevant, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
