from __future__ import annotations

from fastapi import APIRouter, status

from backend.trust_safety.confidence import (
    ConfidenceCalibrationRequest,
    ConfidenceCalibrationResult,
    ConfidenceCalibrationService,
)
from backend.trust_safety.economics import (
    EngineeringEconomicsRequest,
    EngineeringEconomicsResult,
    EngineeringEconomicsService,
)
from backend.trust_safety.health import (
    RepositoryHealthRequest,
    RepositoryHealthResult,
    RepositoryHealthService,
)
from backend.trust_safety.incident import (
    IncidentLearningRequest,
    IncidentLearningResult,
    IncidentLearningService,
)
from backend.trust_safety.policy import ExecutionGateRequest, ExecutionGateResult, PolicyEngine
from backend.trust_safety.verification import (
    VerificationRequest,
    VerificationResult,
    VerificationService,
)


def create_trust_safety_router(
    *,
    verification: VerificationService,
    policy: PolicyEngine,
    confidence: ConfidenceCalibrationService,
    economics: EngineeringEconomicsService,
    health: RepositoryHealthService,
    incidents: IncidentLearningService,
) -> APIRouter:
    router = APIRouter(prefix="/trust-safety", tags=["trust-safety"])

    @router.post(
        "/verification/proposals",
        response_model=VerificationResult,
        status_code=status.HTTP_201_CREATED,
    )
    def verify_proposal(request: VerificationRequest) -> VerificationResult:
        return verification.verify_proposal(request)

    @router.post(
        "/policy/execution-gate",
        response_model=ExecutionGateResult,
        status_code=status.HTTP_201_CREATED,
    )
    def evaluate_execution_gate(request: ExecutionGateRequest) -> ExecutionGateResult:
        return policy.evaluate_execution_gate(request)

    @router.post(
        "/confidence/calibrations",
        response_model=ConfidenceCalibrationResult,
        status_code=status.HTTP_201_CREATED,
    )
    def calibrate_confidence(
        request: ConfidenceCalibrationRequest,
    ) -> ConfidenceCalibrationResult:
        return confidence.calibrate(request)

    @router.get(
        "/confidence/calibrations",
        response_model=list[ConfidenceCalibrationResult],
    )
    def list_confidence_calibrations() -> list[ConfidenceCalibrationResult]:
        return confidence.list_calibrations()

    @router.post(
        "/economics/estimates",
        response_model=EngineeringEconomicsResult,
        status_code=status.HTTP_201_CREATED,
    )
    def estimate_engineering_economics(
        request: EngineeringEconomicsRequest,
    ) -> EngineeringEconomicsResult:
        return economics.estimate(request)

    @router.post(
        "/health/repository",
        response_model=RepositoryHealthResult,
        status_code=status.HTTP_201_CREATED,
    )
    def score_repository_health(request: RepositoryHealthRequest) -> RepositoryHealthResult:
        return health.score(request)

    @router.post(
        "/incidents/learning",
        response_model=IncidentLearningResult,
        status_code=status.HTTP_201_CREATED,
    )
    def record_incident_learning(request: IncidentLearningRequest) -> IncidentLearningResult:
        return incidents.record(request)

    return router
