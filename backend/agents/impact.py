"""Change-impact analysis — the blast radius, in front of every change.

Given a natural-language description of a change, this resolves which graph nodes the change touches,
runs the planner's blast-radius traversal to find everything downstream, and grades the risk. The
chat surface calls this BEFORE acting on any change request, so the user always sees the blast radius
and a risk level and must approve before the assistant proceeds.
"""

from __future__ import annotations

import re
from collections import deque
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.agents.planner import PlannerService
from backend.graph.schemas import GraphNode
from backend.graph.service import GraphService

# Impact follows dependency edges in reverse: if a target changes, everything that imports/calls/
# depends on it is affected.
_DEP_EDGES = {"imports", "depends_on", "calls", "flows_into", "correlates_with"}


class ImpactRequest(BaseModel):
    description: str = Field(min_length=1, max_length=2000)
    max_depth: int = Field(default=3, ge=1, le=6)


class NodeRef(BaseModel):
    id: str
    label: str
    node_type: str


class ImpactResult(BaseModel):
    resolved: bool
    targets: list[NodeRef]
    affected: list[NodeRef]
    affected_count: int
    max_depth: int
    max_depth_reached: int
    confidence: float
    risk_level: str  # None | Low | Medium | High | Critical
    risk_score: float
    paths_preview: list[list[str]]
    summary: str
    breakdown: dict[str, int]  # affected count by node type (File, CodeSymbol, ApiRoute, ...)
    files_touched: int  # distinct files across affected File + CodeSymbol nodes
    call_edges: int  # CALLS edges crossing the target/affected subgraph — function-call impact
    import_edges: int  # IMPORTS edges crossing the target/affected subgraph
    coupling_edges: int  # CORRELATES_WITH edges — hidden, git-mined coupling with no code reference


def _label(node: GraphNode) -> str:
    props = node.properties
    for key in ("name", "path", "title", "summary", "repository", "module_path"):
        value = props.get(key)
        if isinstance(value, str) and value:
            return value if len(value) <= 48 else value[:47] + "…"
    tail = node.stable_id.split("://")[-1]
    return tail[:48]


def _candidates(node: GraphNode) -> list[str]:
    out: list[str] = []
    props = node.properties
    name = props.get("name")
    if isinstance(name, str):
        out.append(name)
    path = props.get("path")
    if isinstance(path, str):
        out.append(path)
        out.append(path.split("/")[-1])
    tail = node.stable_id.split("://")[-1]
    out.append(tail)
    out.append(tail.split("/")[-1])
    # Keep tokens that are specific enough to avoid matching common words.
    return [c for c in out if len(c) >= 4]


# Node types worth treating as change targets (code the user could actually modify).
_TARGETABLE = {"File", "CodeSymbol", "ApiRoute", "SchemaField", "Repository"}


def _resolve_targets(description: str, nodes: list[GraphNode]) -> list[GraphNode]:
    text = description.lower()
    matched: dict[str, GraphNode] = {}
    for node in nodes:
        if node.node_type not in _TARGETABLE:
            continue
        for cand in _candidates(node):
            token = cand.lower()
            # Match on a whole word / path segment so "graph" doesn't match everything.
            if re.search(rf"(?<![\w/]){re.escape(token)}(?![\w])", text) or token in text:
                matched[str(node.id)] = node
                break
    # Prefer the most specific matches (symbols/files) and cap the set.
    ordered = sorted(matched.values(), key=lambda n: (n.node_type != "CodeSymbol", n.node_type != "File"))
    return ordered[:6]


def _grade(affected: int, confidence: float) -> tuple[str, float]:
    if affected == 0:
        return "None", 0.0
    if affected <= 2:
        level = "Low"
    elif affected <= 6:
        level = "Medium"
    elif affected <= 12:
        level = "High"
    else:
        level = "Critical"
    # If the propagation is low-confidence, soften one notch.
    order = ["None", "Low", "Medium", "High", "Critical"]
    if confidence < 0.5 and order.index(level) > 1:
        level = order[order.index(level) - 1]
    size = min(affected / 15.0, 1.0)
    score = round(min(1.0, 0.75 * size + 0.25 * confidence), 3)
    return level, score


def create_impact_router(*, graph: GraphService, planner: PlannerService) -> APIRouter:
    router = APIRouter(prefix="/agents/impact", tags=["agents"])

    @router.post("", response_model=ImpactResult)
    def analyze(request: ImpactRequest) -> ImpactResult:
        nodes = graph.list_nodes()
        by_id = {node.id: node for node in nodes}
        targets = _resolve_targets(request.description, nodes)

        if not targets:
            return ImpactResult(
                resolved=False,
                targets=[],
                affected=[],
                affected_count=0,
                max_depth=request.max_depth,
                max_depth_reached=0,
                confidence=1.0,
                risk_level="None",
                risk_score=0.0,
                paths_preview=[],
                summary="Couldn't map this change to a known part of the graph. Name a file, symbol, or route to scope the blast radius.",
                breakdown={},
                files_touched=0,
                call_edges=0,
                import_edges=0,
                coupling_edges=0,
            )

        # Build reverse dependency adjacency: for edge A -> B (A depends on B), a change in B
        # affects A, so B's dependents include A.
        dependents: dict[UUID, list[tuple[UUID, float]]] = {}
        for edge in graph.list_edges_at():
            if edge.edge_type in _DEP_EDGES:
                dependents.setdefault(edge.to_node_id, []).append((edge.from_node_id, edge.confidence))

        target_ids = {t.id for t in targets}
        affected_ids: set[UUID] = set()
        parent: dict[UUID, UUID] = {}
        min_conf = 1.0
        queue: deque[tuple[UUID, int, float]] = deque((t.id, 0, 1.0) for t in targets)
        best_depth: dict[UUID, int] = {t.id: 0 for t in targets}
        while queue:
            nid, depth, path_conf = queue.popleft()
            if depth >= request.max_depth:
                continue
            for pred, conf in dependents.get(nid, []):
                if pred in target_ids:
                    continue
                next_conf = min(path_conf, conf)
                if pred in best_depth and best_depth[pred] <= depth + 1:
                    continue
                best_depth[pred] = depth + 1
                parent[pred] = nid
                affected_ids.add(pred)
                min_conf = min(min_conf, next_conf)
                queue.append((pred, depth + 1, next_conf))

        affected_nodes = [by_id[nid] for nid in affected_ids if nid in by_id]
        confidence = round(min_conf if affected_nodes else 1.0, 3)
        level, score = _grade(len(affected_nodes), confidence)

        # Reconstruct a few representative dependency chains, deepest first.
        preview: list[list[str]] = []
        leaves = sorted(affected_ids, key=lambda nid: -best_depth.get(nid, 0))
        seen_chain: set[UUID] = set()
        for leaf in leaves:
            if leaf in seen_chain:
                continue
            chain: list[UUID] = []
            cur: UUID | None = leaf
            while cur is not None:
                chain.append(cur)
                seen_chain.add(cur)
                cur = parent.get(cur)
            chain.reverse()
            preview.append([_label(by_id[nid]) for nid in chain if nid in by_id])
            if len(preview) >= 3:
                break

        # Breakdown by node type — lets the card show "3 files, 5 functions, 1 API route" instead
        # of one opaque count.
        breakdown: dict[str, int] = {}
        for node in affected_nodes:
            breakdown[node.node_type] = breakdown.get(node.node_type, 0) + 1

        # Distinct files touched: File nodes directly, plus the file each affected CodeSymbol lives
        # in (a symbol's file may not itself appear as a separate affected File node).
        files_touched: set[str] = set()
        for node in affected_nodes:
            if node.node_type == "File":
                p = node.properties.get("path")
                if isinstance(p, str) and p:
                    files_touched.add(p)
            elif node.node_type == "CodeSymbol":
                f = node.properties.get("file")
                if isinstance(f, str) and f:
                    files_touched.add(f)

        # Function-call / import edges that cross the target+affected subgraph — how much of the
        # actual call graph and module wiring this change reaches, not just node count.
        subgraph_ids = target_ids | affected_ids
        call_edges = 0
        import_edges = 0
        coupling_edges = 0
        for edge in graph.list_edges_at():
            if edge.from_node_id in subgraph_ids and edge.to_node_id in subgraph_ids:
                if edge.edge_type == "calls":
                    call_edges += 1
                elif edge.edge_type == "imports":
                    import_edges += 1
                elif edge.edge_type == "correlates_with":
                    coupling_edges += 1

        max_depth_reached = max((best_depth[nid] for nid in affected_ids), default=0)

        target_labels = ", ".join(_label(t) for t in targets)
        extra = []
        if files_touched:
            extra.append(f"{len(files_touched)} file{'s' if len(files_touched) != 1 else ''}")
        if call_edges:
            extra.append(f"{call_edges} function call{'s' if call_edges != 1 else ''}")
        if coupling_edges:
            extra.append(f"{coupling_edges // 2} hidden coupling link{'s' if coupling_edges // 2 != 1 else ''}")
        extra_str = f" ({', '.join(extra)})" if extra else ""
        summary = (
            f"Changing {target_labels} propagates to {len(affected_nodes)} downstream "
            f"component{'s' if len(affected_nodes) != 1 else ''}{extra_str} within {request.max_depth} hops. "
            f"Risk: {level}."
        )

        return ImpactResult(
            resolved=True,
            targets=[NodeRef(id=str(t.id), label=_label(t), node_type=t.node_type) for t in targets],
            affected=[NodeRef(id=str(n.id), label=_label(n), node_type=n.node_type) for n in affected_nodes],
            affected_count=len(affected_nodes),
            max_depth=request.max_depth,
            max_depth_reached=max_depth_reached,
            confidence=confidence,
            risk_level=level,
            risk_score=score,
            paths_preview=preview,
            summary=summary,
            breakdown=breakdown,
            files_touched=len(files_touched),
            call_edges=call_edges,
            import_edges=import_edges,
            coupling_edges=coupling_edges,
        )

    return router
