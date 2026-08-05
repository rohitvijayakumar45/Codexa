from __future__ import annotations

from fastapi import APIRouter, status

from backend.understanding.architecture_evolution import (
    ArchitectureEvolutionService,
    ArchitectureTrendRequest,
    ArchitectureTrendResult,
)
from backend.understanding.nightly_review import (
    NightlyArchitectureReviewRequest,
    NightlyArchitectureReviewResult,
    NightlyArchitectureReviewService,
)


def create_understanding_router(
    *,
    architecture_evolution: ArchitectureEvolutionService,
    nightly_review: NightlyArchitectureReviewService,
) -> APIRouter:
    router = APIRouter(prefix="/understanding", tags=["understanding"])

    @router.post(
        "/architecture/trends",
        response_model=ArchitectureTrendResult,
        status_code=status.HTTP_201_CREATED,
    )
    def record_architecture_trend(request: ArchitectureTrendRequest) -> ArchitectureTrendResult:
        return architecture_evolution.record_trend(request)

    @router.get(
        "/architecture/trends",
        response_model=list[ArchitectureTrendResult],
    )
    def list_architecture_trends() -> list[ArchitectureTrendResult]:
        return architecture_evolution.list_trends()

    @router.post(
        "/architecture/nightly-review",
        response_model=NightlyArchitectureReviewResult,
        status_code=status.HTTP_201_CREATED,
    )
    def run_nightly_architecture_review(
        request: NightlyArchitectureReviewRequest,
    ) -> NightlyArchitectureReviewResult:
        return nightly_review.run(request)

    return router
