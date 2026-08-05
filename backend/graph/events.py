from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from typing import Any, Protocol
from uuid import UUID, uuid4

import psycopg


@dataclass(frozen=True)
class GraphEvent:
    """Source-of-truth event that projection workers can replay."""

    event_type: str
    payload: dict[str, Any]
    aggregate_id: UUID
    id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class GraphEventWriter(Protocol):
    def append(self, event_type: str, aggregate_id: UUID, payload: dict[str, Any]) -> GraphEvent:
        """Persist an event for Postgres-backed graph projections."""


class InMemoryGraphEventWriter:
    """Test/dev event writer until Postgres persistence is wired."""

    def __init__(self) -> None:
        self.events: list[GraphEvent] = []

    def append(self, event_type: str, aggregate_id: UUID, payload: dict[str, Any]) -> GraphEvent:
        event = GraphEvent(
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=payload,
        )
        self.events.append(event)
        return event


class PostgresGraphEventWriter:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def append(self, event_type: str, aggregate_id: UUID, payload: dict[str, Any]) -> GraphEvent:
        event = GraphEvent(
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=payload,
        )
        with psycopg.connect(self.database_url) as conn:
            conn.execute(
                """
                INSERT INTO graph_events (id, aggregate_id, event_type, payload, occurred_at)
                VALUES (%s, %s, %s, %s::jsonb, %s)
                """,
                (
                    event.id,
                    event.aggregate_id,
                    event.event_type,
                    json.dumps(event.payload),
                    event.occurred_at,
                ),
            )
        return event
