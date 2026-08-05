from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from backend.graph.events import GraphEventWriter
from backend.graph.repository import GraphRepository
from backend.graph.schemas import GraphEdge
from backend.agents.llm import LLMClient


class BlastRadiusRequest(BaseModel):
    changed_node_ids: list[UUID] = Field(min_length=1)
    max_depth: int = Field(default=3, ge=1, le=8)
    at_time: datetime | None = None


class BlastRadiusPath(BaseModel):
    node_ids: list[UUID]
    edge_ids: list[UUID]
    confidence: float = Field(ge=0, le=1)


class BlastRadiusResult(BaseModel):
    analysis_id: UUID
    changed_node_ids: list[UUID]
    affected_node_ids: list[UUID]
    paths: list[BlastRadiusPath]
    max_depth: int
    confidence: float = Field(ge=0, le=1)


@dataclass(frozen=True)
class _TraversalState:
    node_id: UUID
    path_nodes: tuple[UUID, ...]
    path_edges: tuple[UUID, ...]
    confidence: float


class PlannerService:
    def __init__(self, repository: GraphRepository, event_writer: GraphEventWriter, llm: LLMClient) -> None:
        self.repository = repository
        self.event_writer = event_writer
        self.llm = llm

    def synthesize_plan(self, prompt: str) -> str:
        return self.llm.generate("planner", prompt)

    def compute_blast_radius(self, request: BlastRadiusRequest) -> BlastRadiusResult:
        active_edges = self.repository.list_edges_at(request.at_time)
        outgoing = self._outgoing_edges(active_edges)
        changed = set(request.changed_node_ids)
        affected: set[UUID] = set()
        paths: list[BlastRadiusPath] = []

        queue: deque[_TraversalState] = deque(
            _TraversalState(
                node_id=node_id,
                path_nodes=(node_id,),
                path_edges=(),
                confidence=1.0,
            )
            for node_id in request.changed_node_ids
        )

        best_depth_by_node: dict[UUID, int] = {node_id: 0 for node_id in request.changed_node_ids}
        while queue:
            state = queue.popleft()
            depth = len(state.path_edges)
            if depth >= request.max_depth:
                continue

            for edge in outgoing.get(state.node_id, []):
                if edge.to_node_id in state.path_nodes:
                    continue
                next_depth = depth + 1
                previous_best = best_depth_by_node.get(edge.to_node_id)
                if previous_best is not None and previous_best <= next_depth:
                    continue

                next_confidence = min(state.confidence, edge.confidence)
                next_state = _TraversalState(
                    node_id=edge.to_node_id,
                    path_nodes=(*state.path_nodes, edge.to_node_id),
                    path_edges=(*state.path_edges, edge.id),
                    confidence=next_confidence,
                )
                best_depth_by_node[edge.to_node_id] = next_depth
                affected.add(edge.to_node_id)
                paths.append(
                    BlastRadiusPath(
                        node_ids=list(next_state.path_nodes),
                        edge_ids=list(next_state.path_edges),
                        confidence=next_confidence,
                    )
                )
                queue.append(next_state)

        result = BlastRadiusResult(
            analysis_id=uuid4(),
            changed_node_ids=request.changed_node_ids,
            affected_node_ids=sorted(affected - changed, key=str),
            paths=paths,
            max_depth=request.max_depth,
            confidence=min((path.confidence for path in paths), default=1.0),
        )
        self.event_writer.append(
            event_type="planner.blast_radius.computed",
            aggregate_id=result.analysis_id,
            payload=result.model_dump(mode="json"),
        )
        return result

    def _outgoing_edges(self, edges: list[GraphEdge]) -> dict[UUID, list[GraphEdge]]:
        outgoing: dict[UUID, list[GraphEdge]] = {}
        for edge in edges:
            outgoing.setdefault(edge.from_node_id, []).append(edge)
        return outgoing
