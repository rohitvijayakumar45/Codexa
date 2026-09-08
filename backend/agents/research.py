from __future__ import annotations

import json
import re
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from backend.graph.schemas import (
    GraphEdgeCreate,
    GraphEdgeSourceType,
    GraphEdgeType,
    GraphNodeCreate,
    GraphNodeProvenance,
    GraphNodeType,
)
from backend.graph.service import GraphService
from backend.agents.llm import LLMClient

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


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


class ResearchAskRequest(BaseModel):
    repository: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=1000)
    model: str | None = None


class ResearchAskResult(BaseModel):
    recommendation_node_id: UUID
    citation_node_ids: list[UUID]
    edge_ids: list[UUID]
    query: str
    recommendation: str
    confidence: float
    citations: list["ResearchCitation"]
    used_web_search: bool


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
                    # Content originated outside the codebase/user — tag it so any consumer walking
                    # the graph (explanation, verification, an auditor) can tell this apart from
                    # internally-analyzed code or a user-asserted fact without re-deriving it.
                    provenance=GraphNodeProvenance.EXTERNAL_UNTRUSTED,
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

    def ask(self, request: ResearchAskRequest) -> ResearchAskResult:
        """The real, callable entry point `record_recommendation` never got wired to — it only
        persists a recommendation/citations someone else already produced. Runs a live web search
        (when TAVILY_API_KEY is configured) to ground the answer in current external information,
        asks the LLM to synthesize a recommendation with citations, then persists it through the
        same graph path so the agent-network dashboard attributes real activity to this node."""
        from backend.agents.tools import _web_search

        search_result = _web_search(request.query)
        used_web_search = not search_result.startswith("Web search unavailable")

        prompt = (
            f"You are the research agent. A user working on the repository '{request.repository}' "
            f"asked: {request.query}\n\n"
            + (
                f"Web search results:\n{search_result}\n\n"
                if used_web_search
                else "No web search is configured — answer from your own knowledge and say so.\n\n"
            )
            + "Respond with ONLY a JSON object (no markdown fences, no commentary) shaped exactly "
            'like: {"recommendation": "concrete answer/recommendation, 2-5 sentences", '
            '"confidence": 0.0-1.0, "citations": [{"url": "...", "title": "...", "summary": "..."}]}. '
            "If you have no real source (no web search ran), cite \"internal://reasoning\" as the url "
            "with a title like \"Model reasoning\" and summarize what informed the answer."
        )
        raw = self.llm.complete([{"role": "user", "content": prompt}], model=request.model, agent="research")
        recommendation, confidence, citations = self._parse_answer(raw, used_web_search)

        record = self.record_recommendation(ResearchRecommendationRequest(
            query=request.query, recommendation=recommendation, citations=citations, confidence=confidence,
        ))
        return ResearchAskResult(
            recommendation_node_id=record.recommendation_node_id,
            citation_node_ids=record.citation_node_ids,
            edge_ids=record.edge_ids,
            query=request.query,
            recommendation=recommendation,
            confidence=confidence,
            citations=citations,
            used_web_search=used_web_search,
        )

    @staticmethod
    def _parse_answer(raw: str, used_web_search: bool) -> tuple[str, float, list["ResearchCitation"]]:
        """Robust against a model that doesn't follow the JSON-only instruction exactly — never lets
        a malformed response crash the request; falls back to recording the raw text as the
        recommendation with a synthetic citation so nothing is silently lost."""
        match = _JSON_BLOCK.search(raw)
        if match:
            try:
                data = json.loads(match.group(0))
                recommendation = str(data.get("recommendation") or "").strip()
                confidence = float(data.get("confidence") or 0.5)
                confidence = max(0.0, min(1.0, confidence))
                raw_citations = data.get("citations") or []
                citations = [
                    ResearchCitation(url=c["url"], title=c["title"], summary=c["summary"])
                    for c in raw_citations
                    if isinstance(c, dict) and c.get("url") and c.get("title") and c.get("summary")
                ]
                if recommendation and citations:
                    return recommendation, confidence, citations
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass
        # Total parse failure (or missing citations) — record the raw output as the recommendation
        # with a synthetic citation, rather than dropping the model's answer entirely.
        fallback = raw.strip()[:2000] or "No answer produced."
        source = "web search" if used_web_search else "the model's own knowledge (no web search)"
        return (
            fallback,
            0.4,
            [ResearchCitation(url="internal://reasoning", title="Model reasoning",
                               summary=f"Derived from {source}; response was not structured JSON.")],
        )
