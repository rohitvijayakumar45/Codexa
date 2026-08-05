from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from backend.graph.schemas import GraphNodeCreate, GraphNodeType
from backend.graph.service import GraphService


WEIGHTS = {
    "evidence_coverage": 0.25,
    "repo_familiarity": 0.15,
    "test_coverage_overlap": 0.2,
    "historical_similarity": 0.15,
    "verification_pass_rate": 0.15,
    "dependency_certainty": 0.1,
}


class ConfidenceCalibrationRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=512)
    evidence_coverage: float = Field(ge=0, le=1)
    repo_familiarity: float = Field(ge=0, le=1)
    test_coverage_overlap: float = Field(ge=0, le=1)
    historical_similarity: float = Field(ge=0, le=1)
    verification_pass_rate: float = Field(ge=0, le=1)
    dependency_certainty: float = Field(ge=0, le=1)


class ConfidenceCalibrationResult(BaseModel):
    calibration_node_id: UUID
    subject: str
    confidence: float = Field(ge=0, le=1)
    breakdown: dict[str, float]


class ConfidenceCalibrationService:
    def __init__(self, graph: GraphService) -> None:
        self.graph = graph

    def calibrate(self, request: ConfidenceCalibrationRequest) -> ConfidenceCalibrationResult:
        values = {
            "evidence_coverage": request.evidence_coverage,
            "repo_familiarity": request.repo_familiarity,
            "test_coverage_overlap": request.test_coverage_overlap,
            "historical_similarity": request.historical_similarity,
            "verification_pass_rate": request.verification_pass_rate,
            "dependency_certainty": request.dependency_certainty,
        }
        breakdown = {
            name: round(values[name] * weight, 6)
            for name, weight in WEIGHTS.items()
        }
        confidence = round(sum(breakdown.values()), 6)
        node = self.graph.add_node(
            GraphNodeCreate(
                node_type=GraphNodeType.HEALTH_METRIC,
                stable_id=f"confidence-calibration://{request.subject}",
                properties={
                    "metric_kind": "confidence_calibration",
                    "subject": request.subject,
                    "confidence": confidence,
                    "breakdown": breakdown,
                    "weights": WEIGHTS,
                },
            )
        )
        return ConfidenceCalibrationResult(
            calibration_node_id=node.id,
            subject=request.subject,
            confidence=confidence,
            breakdown=breakdown,
        )

    def list_calibrations(self) -> list[ConfidenceCalibrationResult]:
        results: list[ConfidenceCalibrationResult] = []
        for node in self.graph.list_nodes():
            properties = node.properties
            if (
                node.node_type != GraphNodeType.HEALTH_METRIC
                or properties.get("metric_kind") != "confidence_calibration"
            ):
                continue
            results.append(
                ConfidenceCalibrationResult(
                    calibration_node_id=node.id,
                    subject=properties["subject"],
                    confidence=properties["confidence"],
                    breakdown=properties.get("breakdown", {}),
                )
            )
        return sorted(results, key=lambda result: result.subject)
