from __future__ import annotations

from fastapi import APIRouter, status

from backend.memory.schemas import (
    ConventionProfileRequest,
    ConventionProfileResult,
    EngineeringDNARequest,
    EngineeringDNAResult,
    IntentGraphRequest,
    IntentGraphResult,
)
from backend.memory.services import (
    EngineeringDNAService,
    IntentGraphService,
    OrganizationalIntelligenceService,
)


def create_memory_router(
    *,
    intent_graph: IntentGraphService,
    organizational_intelligence: OrganizationalIntelligenceService,
    engineering_dna: EngineeringDNAService,
) -> APIRouter:
    router = APIRouter(prefix="/memory", tags=["memory"])

    @router.post(
        "/intent/chains",
        response_model=IntentGraphResult,
        status_code=status.HTTP_201_CREATED,
    )
    def record_intent_chain(request: IntentGraphRequest) -> IntentGraphResult:
        return intent_graph.record_chain(request)

    @router.post(
        "/organizational/conventions",
        response_model=ConventionProfileResult,
        status_code=status.HTTP_201_CREATED,
    )
    def record_convention_profile(
        request: ConventionProfileRequest,
    ) -> ConventionProfileResult:
        return organizational_intelligence.record_convention_profile(request)

    @router.post(
        "/engineering-dna/conventions",
        response_model=EngineeringDNAResult,
        status_code=status.HTTP_201_CREATED,
    )
    def record_engineering_dna(request: EngineeringDNARequest) -> EngineeringDNAResult:
        return engineering_dna.record_repo_convention(request)

    return router
