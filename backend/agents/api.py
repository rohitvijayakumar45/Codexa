from __future__ import annotations

from fastapi import APIRouter, status

from backend.agents.coder import ChangeProposalRequest, ChangeProposalResult, CoderService
from backend.agents.planner import BlastRadiusRequest, BlastRadiusResult, PlannerService
from backend.agents.research import (
    ResearchAgentService,
    ResearchRecommendationRequest,
    ResearchRecommendationResult,
)
from backend.agents.retrieval import (
    ContextAssemblyRequest,
    ContextAssemblyResult,
    ContextAssemblyService,
)


def create_agents_router(
    *,
    planner: PlannerService,
    coder: CoderService,
    research: ResearchAgentService,
    retrieval: ContextAssemblyService,
) -> APIRouter:
    router = APIRouter(prefix="/agents", tags=["agents"])

    @router.post(
        "/planner/blast-radius",
        response_model=BlastRadiusResult,
        status_code=status.HTTP_201_CREATED,
    )
    def compute_blast_radius(request: BlastRadiusRequest) -> BlastRadiusResult:
        return planner.compute_blast_radius(request)

    @router.post(
        "/coder/proposals",
        response_model=ChangeProposalResult,
        status_code=status.HTTP_201_CREATED,
    )
    def record_change_proposal(request: ChangeProposalRequest) -> ChangeProposalResult:
        return coder.record_proposal(request)

    @router.post(
        "/research/recommendations",
        response_model=ResearchRecommendationResult,
        status_code=status.HTTP_201_CREATED,
    )
    def record_research_recommendation(
        request: ResearchRecommendationRequest,
    ) -> ResearchRecommendationResult:
        return research.record_recommendation(request)

    @router.post(
        "/retrieval/context",
        response_model=ContextAssemblyResult,
        status_code=status.HTTP_201_CREATED,
    )
    def assemble_context(request: ContextAssemblyRequest) -> ContextAssemblyResult:
        return retrieval.assemble(request)

    return router
