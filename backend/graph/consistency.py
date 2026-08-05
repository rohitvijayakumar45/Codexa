from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from backend.graph.events import GraphEventWriter


class ProjectionCount(BaseModel):
    store: str = Field(min_length=1, max_length=64)
    count: int = Field(ge=0)


class ConsistencyCheckRequest(BaseModel):
    postgres_event_count: int = Field(ge=0)
    projections: list[ProjectionCount] = Field(min_length=1)


class ConsistencyCheckResult(BaseModel):
    check_id: str
    consistent: bool
    drift: dict[str, int]
    repair_actions: list[str]


class MultiStoreConsistencyService:
    def __init__(self, event_writer: GraphEventWriter) -> None:
        self.event_writer = event_writer

    def check(self, request: ConsistencyCheckRequest) -> ConsistencyCheckResult:
        drift = {
            projection.store: request.postgres_event_count - projection.count
            for projection in request.projections
            if projection.count != request.postgres_event_count
        }
        repair_actions = [
            f"replay_outbox_to_{store}"
            for store, delta in drift.items()
            if delta != 0
        ]
        result = ConsistencyCheckResult(
            check_id=str(uuid4()),
            consistent=not drift,
            drift=drift,
            repair_actions=repair_actions,
        )
        self.event_writer.append(
            event_type="graph.multistore_consistency.checked",
            aggregate_id=uuid4(),
            payload=result.model_dump(mode="json"),
        )
        return result
