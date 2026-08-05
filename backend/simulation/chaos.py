from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from backend.graph.events import GraphEventWriter


class ChaosScenarioKind(StrEnum):
    DEPENDENCY_DOWN = "dependency_down"
    DB_CONNECTION_DROP = "db_connection_drop"
    CPU_SPIKE = "cpu_spike"
    NETWORK_PARTITION = "network_partition"


class ChaosPremortemRequest(BaseModel):
    proposal_id: UUID
    risk_score: float = Field(ge=0, le=1)
    threshold: float = Field(default=0.6, ge=0, le=1)


class ChaosScenario(BaseModel):
    kind: ChaosScenarioKind
    expected_signal: str
    required_for_merge: bool


class ChaosPremortemResult(BaseModel):
    premortem_id: UUID
    proposal_id: UUID
    required: bool
    scenarios: list[ChaosScenario]


class ChaosPremortemService:
    def __init__(self, event_writer: GraphEventWriter) -> None:
        self.event_writer = event_writer

    def plan(self, request: ChaosPremortemRequest) -> ChaosPremortemResult:
        required = request.risk_score >= request.threshold
        scenarios = self._required_scenarios() if required else []
        result = ChaosPremortemResult(
            premortem_id=uuid4(),
            proposal_id=request.proposal_id,
            required=required,
            scenarios=scenarios,
        )
        self.event_writer.append(
            event_type="simulation.chaos_premortem.planned",
            aggregate_id=result.premortem_id,
            payload=result.model_dump(mode="json"),
        )
        return result

    def _required_scenarios(self) -> list[ChaosScenario]:
        return [
            ChaosScenario(
                kind=ChaosScenarioKind.DEPENDENCY_DOWN,
                expected_signal="service dependency failure is contained and surfaced",
                required_for_merge=True,
            ),
            ChaosScenario(
                kind=ChaosScenarioKind.DB_CONNECTION_DROP,
                expected_signal="database outage produces retry/backoff or graceful failure",
                required_for_merge=True,
            ),
            ChaosScenario(
                kind=ChaosScenarioKind.CPU_SPIKE,
                expected_signal="latency budget breach is detected",
                required_for_merge=True,
            ),
            ChaosScenario(
                kind=ChaosScenarioKind.NETWORK_PARTITION,
                expected_signal="network partition does not corrupt source-of-truth writes",
                required_for_merge=True,
            ),
        ]
