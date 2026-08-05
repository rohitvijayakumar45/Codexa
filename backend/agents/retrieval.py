from __future__ import annotations

from collections import deque
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from backend.graph.events import GraphEventWriter
from backend.graph.repository import GraphRepository
from backend.agents.llm import LLMClient


class SemanticHit(BaseModel):
    node_id: UUID
    score: float = Field(ge=0, le=1)


class ContextAssemblyRequest(BaseModel):
    agent_name: str = Field(min_length=1, max_length=64)
    seed_node_ids: list[UUID] = Field(default_factory=list)
    semantic_hits: list[SemanticHit] = Field(default_factory=list)
    max_hops: int = Field(default=2, ge=0, le=6)
    token_budget: int = Field(default=2048, ge=128, le=128000)


class ContextAssemblyResult(BaseModel):
    assembly_id: UUID
    selected_node_ids: list[UUID]
    selected_edge_ids: list[UUID]
    estimated_tokens: int
    summarized: bool
    summary: str | None = None


class ContextAssemblyService:
    node_token_estimate = 80
    edge_token_estimate = 24

    def __init__(self, repository: GraphRepository, event_writer: GraphEventWriter, llm: LLMClient) -> None:
        self.repository = repository
        self.event_writer = event_writer
        self.llm = llm

    def assemble(self, request: ContextAssemblyRequest) -> ContextAssemblyResult:
        active_edges = self.repository.list_edges_at()
        outgoing = {}
        for edge in active_edges:
            outgoing.setdefault(edge.from_node_id, []).append(edge)

        selected_nodes = set(request.seed_node_ids)
        selected_edges = set()
        queue = deque((node_id, 0) for node_id in request.seed_node_ids)
        while queue:
            node_id, depth = queue.popleft()
            if depth >= request.max_hops:
                continue
            for edge in outgoing.get(node_id, []):
                selected_edges.add(edge.id)
                if edge.to_node_id not in selected_nodes:
                    selected_nodes.add(edge.to_node_id)
                    queue.append((edge.to_node_id, depth + 1))

        for hit in sorted(request.semantic_hits, key=lambda item: item.score, reverse=True):
            selected_nodes.add(hit.node_id)

        estimated_tokens = (
            len(selected_nodes) * self.node_token_estimate
            + len(selected_edges) * self.edge_token_estimate
        )
        summarized = estimated_tokens > request.token_budget
        result = ContextAssemblyResult(
            assembly_id=uuid4(),
            selected_node_ids=sorted(selected_nodes, key=str),
            selected_edge_ids=sorted(selected_edges, key=str),
            estimated_tokens=min(estimated_tokens, request.token_budget) if summarized else estimated_tokens,
            summarized=summarized,
            summary=(
                f"Context exceeded {request.token_budget} tokens; use graph summary for "
                f"{len(selected_nodes)} nodes and {len(selected_edges)} edges."
                if summarized
                else None
            ),
        )
        self.event_writer.append(
            event_type="retrieval.context.assembled",
            aggregate_id=result.assembly_id,
            payload=result.model_dump(mode="json"),
        )
        return result
