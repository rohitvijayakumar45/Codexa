"""Graph-anchored context eviction — which stale tool payloads get extra grace before compaction.

backend/agents/jobs.py's `_compact_stale_payloads` collapses bulky tool payloads (design-guidance
dumps, file contents in write_file/edit_file calls) a fixed number of rounds after they were last
used, regardless of whether the model is still actively working in that area of the codebase or has
moved on entirely. This module makes that eviction graph-aware instead: it resolves the file the
model most recently touched to its knowledge-graph node, runs the same reverse-dependency traversal
blast-radius analysis uses (backend/agents/impact.py: blast_radius_ids) to find what's structurally
close to it, and lets a stale payload for a file still in that neighborhood survive longer than one
for a file the task has clearly moved past. The graph distance is a real signal for "will the model
need this again soon" that a flat round-count can't see.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from backend.agents.impact import blast_radius_ids

# Payloads for a file still within the current blast-radius neighborhood get this many times the
# normal staleness threshold before compaction — outside it, the normal (shorter) threshold applies.
GRACE_MULTIPLIER_IN_RADIUS = 3
_RADIUS_DEPTH = 2
_FILE_TOOLS = ("write_file", "edit_file", "read_file")


def _latest_touched_path(messages: list[dict]) -> str | None:
    """The path of the most recent write_file/edit_file/read_file call in the conversation so far —
    used as the "what is the model currently working on" anchor for the blast-radius lookup."""
    for msg in reversed(messages):
        if msg.get("role") != "assistant" or not msg.get("tool_calls"):
            continue
        for tc in msg["tool_calls"]:
            fn = tc.get("function", {})
            if fn.get("name") not in _FILE_TOOLS:
                continue
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            path = args.get("path")
            if isinstance(path, str) and path:
                return path
    return None


def _file_node_id(path: str, repository: str, graph: Any) -> UUID | None:
    for n in graph.list_nodes():
        if n.node_type != "File":
            continue
        repo_prop = n.properties.get("repository")
        same_repo = (not repo_prop) if repository == "codexa-os" else repo_prop == repository
        if same_repo and n.properties.get("path") == path:
            return n.id
    return None


def relevant_paths(messages: list[dict], *, repository: str, graph: Any) -> set[str] | None:
    """Paths structurally close to whatever the model most recently touched — files whose stale
    payloads should get extra grace before compaction. Returns None (not an empty set) when there's
    no anchor to compute from, so the caller can tell "nothing is protected" apart from "couldn't
    determine relevance, don't extend anyone's grace"."""
    anchor_path = _latest_touched_path(messages)
    if anchor_path is None:
        return None
    anchor_id = _file_node_id(anchor_path, repository, graph)
    if anchor_id is None:
        return None
    radius = blast_radius_ids({anchor_id}, graph=graph, max_depth=_RADIUS_DEPTH)
    relevant_ids = {anchor_id} | radius.affected_ids
    return {
        n.properties.get("path")
        for n in graph.list_nodes()
        if n.node_type == "File" and n.id in relevant_ids and n.properties.get("path")
    }
