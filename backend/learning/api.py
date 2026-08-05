from __future__ import annotations

from fastapi import APIRouter, status

from backend.learning.policy_distillation import (
    PolicyDistillationRequest,
    PolicyDistillationResult,
    PolicyDistillationService,
)


def create_learning_router(*, policy_distillation: PolicyDistillationService) -> APIRouter:
    router = APIRouter(prefix="/learning", tags=["learning"])

    @router.post(
        "/policy-distillation/runs",
        response_model=PolicyDistillationResult,
        status_code=status.HTTP_201_CREATED,
    )
    def run_policy_distillation(
        request: PolicyDistillationRequest,
    ) -> PolicyDistillationResult:
        return policy_distillation.distill(request)

    return router
