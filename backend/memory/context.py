"""Graph-anchored context retrieval for chat grounding.

Replaces the old flat "first 12 memory records regardless of relevance" injection. Resolves the
user's question to specific graph nodes (same name/path matching approach the blast-radius resolver
in `agents/impact.py` uses), pulls each matched symbol's LLM-derived semantic annotation
(`repository/semantic.py`) plus its immediate call/import neighbors, and only falls back to generic
repo-digest facts when nothing in the question resolves to a real symbol. Bounded and targeted:
a question about one function gets that function's neighborhood, not the whole repository's memory.
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.graph.schemas import GraphNode
from backend.graph.service import GraphService
from backend.memory.store import MemoryStore

_TARGETABLE = {"File", "CodeSymbol"}
_DEP_EDGES = {"imports", "calls", "depends_on", "flows_into"}
_MAX_MATCHES = 5
_MAX_NEIGHBORS_PER_MATCH = 6
_MAX_ITEMS = 16


class ContextItem(BaseModel):
    kind: str
    title: str
    content: str


def _in_repo(node: GraphNode, repository: str) -> bool:
    repo_prop = node.properties.get("repository")
    return not repo_prop if repository == "codexa-os" else repo_prop == repository


def _candidates(node: GraphNode) -> list[str]:
    out: list[str] = []
    name = node.properties.get("name")
    if isinstance(name, str):
        out.append(name)
    path = node.properties.get("path")
    if isinstance(path, str):
        out.append(path.split("/")[-1])
    return [c for c in out if len(c) >= 3]


def _label(node: GraphNode) -> str:
    props = node.properties
    value = props.get("name") or props.get("path") or node.stable_id.split("://")[-1]
    return str(value)[:64]


def _load_annotations(store: MemoryStore, repository: str) -> dict[str, dict]:
    for rec in store.list(repository=repository, memory_type="semantic"):
        if rec.metadata.get("source") == "symbol_annotations":
            try:
                return json.loads(rec.content)
            except json.JSONDecodeError:
                return {}
    return {}


def create_context_router(*, store: MemoryStore, graph: GraphService) -> APIRouter:
    router = APIRouter(prefix="/memory", tags=["memory"])

    @router.get("/context", response_model=list[ContextItem])
    def context(repository: str = Query(...), query: str = Query(...)) -> list[ContextItem]:
        text = query.lower()
        all_nodes = graph.list_nodes()
        scoped = [n for n in all_nodes if n.node_type in _TARGETABLE and _in_repo(n, repository)]

        matched: list[GraphNode] = []
        for node in scoped:
            for cand in _candidates(node):
                token = cand.lower()
                if re.search(rf"(?<![\w/]){re.escape(token)}(?![\w])", text):
                    matched.append(node)
                    break
            if len(matched) >= _MAX_MATCHES:
                break

        items: list[ContextItem] = []
        annotations = _load_annotations(store, repository)

        if matched:
            by_id = {n.id: n for n in all_nodes}
            edges = [e for e in graph.list_edges_at() if e.edge_type in _DEP_EDGES]
            for node in matched:
                if len(items) >= _MAX_ITEMS:
                    break
                title = _label(node)
                entry = None
                if node.node_type == "CodeSymbol":
                    key = f"symbol://{repository}/{node.properties.get('file')}#{node.properties.get('name')}"
                    entry = annotations.get(key)
                content = entry["summary"] if entry else (
                    f"{node.node_type} at {node.properties.get('path') or node.properties.get('file')}"
                )
                items.append(ContextItem(kind=node.node_type, title=title, content=content))

                neighbor_count = 0
                for edge in edges:
                    if neighbor_count >= _MAX_NEIGHBORS_PER_MATCH or len(items) >= _MAX_ITEMS:
                        break
                    if edge.from_node_id == node.id:
                        other_id, relation = edge.to_node_id, edge.edge_type
                    elif edge.to_node_id == node.id:
                        other_id, relation = edge.from_node_id, f"{edge.edge_type} (incoming)"
                    else:
                        continue
                    other = by_id.get(other_id)
                    if not other or other.node_type not in _TARGETABLE:
                        continue
                    items.append(ContextItem(
                        kind="relation", title=f"{title} --{relation}--> {_label(other)}", content="",
                    ))
                    neighbor_count += 1

        digest_records = [
            r for r in store.list(repository=repository)
            if r.metadata.get("source") not in ("docs_cache", "symbol_annotations")
        ]
        if matched:
            baseline = [r for r in digest_records if r.title.startswith("What")][:2]
        else:
            baseline = digest_records[:12]
        for r in baseline:
            if len(items) >= _MAX_ITEMS:
                break
            items.append(ContextItem(kind=r.memory_type, title=r.title, content=r.content))

        return items[:_MAX_ITEMS]

    return router
