from __future__ import annotations

from fastapi import APIRouter, status

from backend.agents.coder import (
    ChangeProposalRequest,
    ChangeProposalResult,
    CoderService,
    ProposeChangeRequest,
    ProposeChangeResult,
)
from backend.agents.planner import BlastRadiusRequest, BlastRadiusResult, PlanRequest, PlanResult, PlannerService
from backend.agents.quorum import QuorumRunRequest, QuorumRunResult, QuorumService
from backend.agents.research import (
    ResearchAgentService,
    ResearchAskRequest,
    ResearchAskResult,
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
    quorum: QuorumService,
) -> APIRouter:
    router = APIRouter(prefix="/agents", tags=["agents"])

    @router.post(
        "/planner/blast-radius",
        response_model=BlastRadiusResult,
        status_code=status.HTTP_201_CREATED,
    )
    def compute_blast_radius(request: BlastRadiusRequest) -> BlastRadiusResult:
        return planner.compute_blast_radius(request)

    @router.post("/planner/plan", response_model=PlanResult, status_code=status.HTTP_201_CREATED)
    def synthesize_plan(request: PlanRequest) -> PlanResult:
        """Actually calls the LLM to turn a goal into a concrete plan — unlike blast-radius (pure
        graph traversal), this is real planning-agent work."""
        return planner.plan(request)

    @router.post(
        "/coder/proposals",
        response_model=ChangeProposalResult,
        status_code=status.HTTP_201_CREATED,
    )
    def record_change_proposal(request: ChangeProposalRequest) -> ChangeProposalResult:
        return coder.record_proposal(request)

    @router.post("/coder/propose", response_model=ProposeChangeResult, status_code=status.HTTP_201_CREATED)
    def propose_change(request: ProposeChangeRequest) -> ProposeChangeResult:
        """Actually calls the LLM to read the named files and produce a real diff + rationale,
        unlike /coder/proposals which only persists a diff someone else already produced."""
        return coder.propose(request)

    @router.post(
        "/research/recommendations",
        response_model=ResearchRecommendationResult,
        status_code=status.HTTP_201_CREATED,
    )
    def record_research_recommendation(
        request: ResearchRecommendationRequest,
    ) -> ResearchRecommendationResult:
        return research.record_recommendation(request)

    @router.post("/research/ask", response_model=ResearchAskResult, status_code=status.HTTP_201_CREATED)
    def ask_research(request: ResearchAskRequest) -> ResearchAskResult:
        """Actually runs a live web search (when configured) and calls the LLM to synthesize a
        cited recommendation, unlike /research/recommendations which only persists a recommendation
        someone else already produced."""
        return research.ask(request)

    @router.post("/quorum/run", response_model=QuorumRunResult, status_code=status.HTTP_201_CREATED)
    def run_quorum(request: QuorumRunRequest) -> QuorumRunResult:
        """Runs the same question through a panel of independently-answering agents, filters their
        claims deterministically against the real graph before any of them sees a peer's answer, and
        only falls back to a structured (belief-card, not free-text) debate round for whatever the
        graph genuinely can't resolve either way."""
        return quorum.run(request)

    @router.post(
        "/retrieval/context",
        response_model=ContextAssemblyResult,
        status_code=status.HTTP_201_CREATED,
    )
    def assemble_context(request: ContextAssemblyRequest) -> ContextAssemblyResult:
        return retrieval.assemble(request)

    return router
