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
_MAX_NEIGHBORS_PER_MATCH = 4
_MAX_ITEMS = 8
# Digest records (project structure, function listings) can be several KB uncapped — this is what
# was quietly padding every chat request's prompt regardless of relevance. See
# docs/token_usage_investigation.md.
_MAX_CONTENT_CHARS = 800
# When no symbols match, inject at most this many digest records (ranked by relevance).
_MAX_BASELINE_RECORDS = 4


def _truncate(text: str, limit: int = _MAX_CONTENT_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + f"… [truncated, {len(text)} chars total]"


# Query phrasing that indicates which memory type the question is really asking about — used to
# weight ranking, not to filter, so a record of the "wrong" type can still surface on strong keyword
# overlap alone. Without this, "how do I run this" and "what tech stack does this use" score purely
# on keyword overlap and can lose to an unrelated but keyword-heavier record of a different type,
# even though the type itself is a near-perfect signal for which record actually answers the
# question — semantic/episodic/procedural/organizational otherwise sit in one undifferentiated pool.
_TYPE_SIGNALS: dict[str, re.Pattern[str]] = {
    "procedural": re.compile(
        r"\b(how (do|to|can) (i|you)|run|build|start|install|setup|set up|deploy|command|script|npm|yarn|pnpm)\b",
        re.IGNORECASE,
    ),
    "organizational": re.compile(
        r"\b(stack|tech stack|convention|framework|language|architecture|health|score|"
        r"dependency|dependencies|structure|conventions)\b",
        re.IGNORECASE,
    ),
    "episodic": re.compile(
        r"\b(when (was|did)|history|changelog|loaded|created|cloned|timeline|recently|last (loaded|updated))\b",
        re.IGNORECASE,
    ),
    "semantic": re.compile(
        r"\b(what is|what does|what are|explain|describe|purpose|function|component|class|"
        r"symbol|method)\b",
        re.IGNORECASE,
    ),
}
# Additive, not multiplicative — a type match nudges ranking (enough to beat a same-score record of
# the wrong type) without fully overriding genuine keyword relevance from a strong text match.
_TYPE_MATCH_BONUS = 0.35


def _relevance_score(query: str, title: str, content: str, memory_type: str | None = None) -> float:
    """Keyword-overlap score (0.0-1.0+, title matches count 2x) plus a bonus when the query's
    phrasing signals the record's own memory_type is the one that actually answers it."""
    query_tokens = [w for w in re.split(r"\W+", query.lower()) if len(w) >= 3]
    if not query_tokens:
        return 0.0
    text = f"{title.lower()} {title.lower()} {content.lower()}"  # title weighted 2x
    hits = sum(1 for t in query_tokens if t in text)
    score = hits / len(query_tokens)
    signal = _TYPE_SIGNALS.get(memory_type or "")
    if signal and signal.search(query):
        score += _TYPE_MATCH_BONUS
    return score


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
    value = props.get("qualname") or props.get("name") or props.get("path") or node.stable_id.split("://")[-1]
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
                    qual = node.properties.get("qualname") or node.properties.get("name")
                    key = f"symbol://{repository}/{node.properties.get('file')}#{qual}"
                    entry = annotations.get(key)
                content = entry["summary"] if entry else (
                    f"{node.node_type} at {node.properties.get('path') or node.properties.get('file')}"
                )
                items.append(ContextItem(kind=node.node_type, title=title, content=_truncate(content)))

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
            # Symbols matched → add up to 2 baseline facts for broader context.
            baseline = sorted(
                digest_records,
                key=lambda r: _relevance_score(text, r.title, r.content, r.memory_type),
                reverse=True,
            )[:2]
        else:
            # No symbols matched → rank ALL digest records by relevance, take top-k.
            baseline = sorted(
                digest_records,
                key=lambda r: _relevance_score(text, r.title, r.content, r.memory_type),
                reverse=True,
            )[:_MAX_BASELINE_RECORDS]
        for r in baseline:
            if len(items) >= _MAX_ITEMS:
                break
            items.append(ContextItem(kind=r.memory_type, title=r.title, content=_truncate(r.content)))

        return items[:_MAX_ITEMS]

    return router
