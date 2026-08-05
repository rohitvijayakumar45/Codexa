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
from backend.agents.llm import LLMClient


class ResearchCitation(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=512)
    summary: str = Field(min_length=1, max_length=1024)


class ResearchRecommendationRequest(BaseModel):
    query: str = Field(min_length=1, max_length=512)
    recommendation: str = Field(min_length=1, max_length=2048)
    citations: list[ResearchCitation] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class ResearchRecommendationResult(BaseModel):
    recommendation_node_id: UUID
    citation_node_ids: list[UUID]
    edge_ids: list[UUID]
    confidence: float = Field(ge=0, le=1)


class ResearchAgentService:
    def __init__(self, graph: GraphService, llm: LLMClient) -> None:
        self.graph = graph
        self.llm = llm

    def record_recommendation(
        self, request: ResearchRecommendationRequest
    ) -> ResearchRecommendationResult:
        recommendation = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.DECISION,
                stable_id=f"research-recommendation://{request.query}",
                properties={
                    "decision_kind": "research_recommendation",
                    "query": request.query,
                    "summary": request.recommendation,
                    "confidence": request.confidence,
                    "citations": [citation.model_dump() for citation in request.citations],
                },
            )
        )
        citation_nodes = [
            self.graph.add_node(
                GraphNodeCreate(
                    node_type=GraphNodeType.EXTERNAL_ARTIFACT,
                    stable_id=f"research-source://{citation.url}",
                    properties={
                        "source_uri": citation.url,
                        "title": citation.title,
                        "summary": citation.summary,
                        "trust_level": "public_scraped",
                    },
                )
            )
            for citation in request.citations
        ]
        edges = [
            self.graph.add_edge(
                GraphEdgeCreate(
                    from_node_id=recommendation.id,
                    to_node_id=citation.id,
                    edge_type=GraphEdgeType.DERIVED_FROM,
                    confidence=request.confidence,
                    source_type=GraphEdgeSourceType.HUMAN_ASSERTED,
                    properties={"relationship": "cited_research_source"},
                )
            )
            for citation in citation_nodes
        ]
        return ResearchRecommendationResult(
            recommendation_node_id=recommendation.id,
            citation_node_ids=[node.id for node in citation_nodes],
            edge_ids=[edge.id for edge in edges],
            confidence=request.confidence,
        )
