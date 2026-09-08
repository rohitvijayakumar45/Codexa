from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from backend.graph.schemas import (
    GraphEdgeCreate,
    GraphEdgeSourceType,
    GraphEdgeType,
    GraphNodeCreate,
    GraphNodeType,
)
from backend.graph.service import GraphService


class IncidentLearningRequest(BaseModel):
    source_artifact_id: UUID
    incident: str = Field(min_length=1, max_length=1024)
    root_cause: str = Field(min_length=1, max_length=1024)
    fix: str = Field(min_length=1, max_length=1024)
    regression_test: str = Field(min_length=1, max_length=1024)
    prevention_rule: str = Field(min_length=1, max_length=1024)
    confidence: float = Field(ge=0, le=1)
    # Which File graph nodes this incident actually implicated — optional, but without it an
    # incident is only ever reachable by its own source_artifact_id, invisible to anything walking
    # the code graph (blast radius, coupling analysis) from a file the user is about to touch.
    affected_file_ids: list[UUID] = Field(default_factory=list)


class IncidentLearningResult(BaseModel):
    incident_node_id: UUID
    root_cause_node_id: UUID
    fix_node_id: UUID
    regression_test_node_id: UUID
    prevention_rule_node_id: UUID
    edge_ids: list[UUID]


class IncidentLearningService:
    def __init__(self, graph: GraphService) -> None:
        self.graph = graph

    def record(self, request: IncidentLearningRequest) -> IncidentLearningResult:
        incident = self._causal_node("incident", request.incident, request)
        root_cause = self._causal_node("root_cause", request.root_cause, request)
        fix = self._causal_node("fix", request.fix, request)
        regression_test = self._causal_node("regression_test", request.regression_test, request)
        prevention_rule = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.PREVENTION_RULE,
                stable_id=f"prevention-rule://{request.source_artifact_id}",
                properties={
                    "summary": request.prevention_rule,
                    "confidence": request.confidence,
                    "source_artifact_id": str(request.source_artifact_id),
                },
            )
        )
        edges = [
            self._edge(root_cause.id, incident.id, GraphEdgeType.CAUSES, request),
            self._edge(fix.id, root_cause.id, GraphEdgeType.MITIGATES, request),
            self._edge(regression_test.id, incident.id, GraphEdgeType.MITIGATES, request),
            self._edge(prevention_rule.id, root_cause.id, GraphEdgeType.MITIGATES, request),
        ]
        # Link the actual files this incident implicated to its root cause — the join that lets
        # blast-radius/coupling analysis (backend/agents/impact.py) discover "a file you're about to
        # touch has a real incident history" instead of incidents living only in their own isolated
        # subgraph, reachable solely by source_artifact_id.
        edges.extend(
            self._edge(file_id, root_cause.id, GraphEdgeType.CORRELATES_WITH, request)
            for file_id in request.affected_file_ids
        )
        return IncidentLearningResult(
            incident_node_id=incident.id,
            root_cause_node_id=root_cause.id,
            fix_node_id=fix.id,
            regression_test_node_id=regression_test.id,
            prevention_rule_node_id=prevention_rule.id,
            edge_ids=[edge.id for edge in edges],
        )

    def _causal_node(
        self,
        event_kind: str,
        summary: str,
        request: IncidentLearningRequest,
    ):
        return self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.CAUSAL_EVENT,
                stable_id=f"incident-learning://{request.source_artifact_id}/{event_kind}",
                properties={
                    "event_kind": event_kind,
                    "summary": summary,
                    "confidence": request.confidence,
                    "source_artifact_id": str(request.source_artifact_id),
                },
            )
        )

    def _edge(
        self,
        from_node_id: UUID,
        to_node_id: UUID,
        edge_type: GraphEdgeType,
        request: IncidentLearningRequest,
    ):
        return self.graph.add_edge(
            GraphEdgeCreate(
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                edge_type=edge_type,
                confidence=request.confidence,
                source_type=GraphEdgeSourceType.LLM_INFERRED,
                source_artifact_id=request.source_artifact_id,
            )
        )
