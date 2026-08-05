from __future__ import annotations

import re
from uuid import UUID

from backend.graph.schemas import (
    GraphEdgeCreate,
    GraphEdgeSourceType,
    GraphEdgeType,
    GraphNodeCreate,
    GraphNodeType,
)
from backend.graph.service import GraphService
from backend.memory.schemas import (
    ConventionProfileRequest,
    ConventionProfileResult,
    EngineeringDNARequest,
    EngineeringDNAResult,
    IntentGraphRequest,
    IntentGraphResult,
)


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized[:96] or "empty"


def _source_artifact_node(graph: GraphService, source_artifact_id: UUID):
    return graph.add_node(
        GraphNodeCreate(
            node_type=GraphNodeType.EXTERNAL_ARTIFACT,
            stable_id=f"artifact://{source_artifact_id}",
            properties={"artifact_id": str(source_artifact_id)},
        )
    )


class IntentGraphService:
    def __init__(self, graph: GraphService) -> None:
        self.graph = graph

    def record_chain(self, request: IntentGraphRequest) -> IntentGraphResult:
        source = _source_artifact_node(self.graph, request.source_artifact_id)
        chain_key = f"{request.source_artifact_id}/{_slug(request.decision)}"
        decision = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.DECISION,
                stable_id=f"decision://{chain_key}",
                properties={
                    "summary": request.decision,
                    "confidence": request.confidence,
                },
            )
        )
        tradeoff = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.TRADEOFF,
                stable_id=f"tradeoff://{chain_key}/{_slug(request.tradeoff)}",
                properties={
                    "summary": request.tradeoff,
                    "confidence": request.confidence,
                },
            )
        )
        rejected = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.REJECTED_ALTERNATIVE,
                stable_id=f"rejected-alternative://{chain_key}/{_slug(request.rejected_alternative)}",
                properties={
                    "summary": request.rejected_alternative,
                    "confidence": request.confidence,
                },
            )
        )

        edges = [
            self.graph.add_edge(
                GraphEdgeCreate(
                    from_node_id=decision.id,
                    to_node_id=source.id,
                    edge_type=GraphEdgeType.DERIVED_FROM,
                    confidence=request.confidence,
                    source_type=GraphEdgeSourceType.LLM_INFERRED,
                    source_artifact_id=request.source_artifact_id,
                    properties={"relationship": "decision_source"},
                )
            ),
            self.graph.add_edge(
                GraphEdgeCreate(
                    from_node_id=tradeoff.id,
                    to_node_id=decision.id,
                    edge_type=GraphEdgeType.TRACES_TO_DECISION,
                    confidence=request.confidence,
                    source_type=GraphEdgeSourceType.LLM_INFERRED,
                    source_artifact_id=request.source_artifact_id,
                    properties={"relationship": "tradeoff_for_decision"},
                )
            ),
            self.graph.add_edge(
                GraphEdgeCreate(
                    from_node_id=rejected.id,
                    to_node_id=decision.id,
                    edge_type=GraphEdgeType.TRACES_TO_DECISION,
                    confidence=request.confidence,
                    source_type=GraphEdgeSourceType.LLM_INFERRED,
                    source_artifact_id=request.source_artifact_id,
                    properties={"relationship": "rejected_for_decision"},
                )
            ),
        ]
        return IntentGraphResult(
            decision_node_id=decision.id,
            tradeoff_node_id=tradeoff.id,
            rejected_alternative_node_id=rejected.id,
            edge_ids=[edge.id for edge in edges],
        )


class OrganizationalIntelligenceService:
    def __init__(self, graph: GraphService) -> None:
        self.graph = graph

    def record_convention_profile(
        self, request: ConventionProfileRequest
    ) -> ConventionProfileResult:
        source = _source_artifact_node(self.graph, request.source_artifact_id)
        owner = request.author or request.team
        profile = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.CONVENTION_PROFILE,
                stable_id=f"convention-profile://{_slug(request.team)}/{_slug(owner)}/{_slug(request.convention)}",
                properties={
                    "team": request.team,
                    "author": request.author,
                    "convention": request.convention,
                    "evidence": request.evidence,
                    "confidence": request.confidence,
                    "profile_kind": "organizational_intelligence",
                },
            )
        )
        edge = self.graph.add_edge(
            GraphEdgeCreate(
                from_node_id=profile.id,
                to_node_id=source.id,
                edge_type=GraphEdgeType.DERIVED_FROM,
                confidence=request.confidence,
                source_type=GraphEdgeSourceType.LLM_INFERRED,
                source_artifact_id=request.source_artifact_id,
            )
        )
        return ConventionProfileResult(
            profile_node_id=profile.id,
            source_node_id=source.id,
            edge_id=edge.id,
        )


class EngineeringDNAService:
    def __init__(self, graph: GraphService) -> None:
        self.graph = graph

    def record_repo_convention(self, request: EngineeringDNARequest) -> EngineeringDNAResult:
        source = _source_artifact_node(self.graph, request.source_artifact_id)
        convention = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.CONVENTION_PROFILE,
                stable_id=(
                    f"engineering-dna://{_slug(request.repository)}/"
                    f"{_slug(request.category)}/{_slug(request.convention)}"
                ),
                properties={
                    "repository": request.repository,
                    "category": request.category,
                    "convention": request.convention,
                    "evidence": request.evidence,
                    "confidence": request.confidence,
                    "profile_kind": "engineering_dna",
                },
            )
        )
        edge = self.graph.add_edge(
            GraphEdgeCreate(
                from_node_id=convention.id,
                to_node_id=source.id,
                edge_type=GraphEdgeType.DERIVED_FROM,
                confidence=request.confidence,
                source_type=GraphEdgeSourceType.LLM_INFERRED,
                source_artifact_id=request.source_artifact_id,
            )
        )
        return EngineeringDNAResult(
            convention_node_id=convention.id,
            source_node_id=source.id,
            edge_id=edge.id,
        )
