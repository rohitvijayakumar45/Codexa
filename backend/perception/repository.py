from __future__ import annotations

import json
from typing import Protocol

import psycopg

from backend.perception.schemas import IngestArtifactRequest, IsolatedArtifact


class ArtifactRepository(Protocol):
    def save(self, raw: IngestArtifactRequest, isolated: IsolatedArtifact) -> None:
        """Persist raw and isolated artifact forms to Postgres source of truth."""


class InMemoryArtifactRepository:
    def __init__(self) -> None:
        self.artifacts: list[tuple[IngestArtifactRequest, IsolatedArtifact]] = []

    def save(self, raw: IngestArtifactRequest, isolated: IsolatedArtifact) -> None:
        self.artifacts.append((raw, isolated))


class PostgresArtifactRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def save(self, raw: IngestArtifactRequest, isolated: IsolatedArtifact) -> None:
        with psycopg.connect(self.database_url) as conn:
            conn.execute(
                """
                INSERT INTO ingested_artifacts (
                    id,
                    source_uri,
                    kind,
                    trust_level,
                    raw_content,
                    isolated_content,
                    instruction_content_removed,
                    isolation_findings
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    isolated.artifact_id,
                    raw.source_uri,
                    raw.kind,
                    raw.trust_level,
                    raw.content,
                    isolated.isolated_content,
                    isolated.instruction_content_removed,
                    json.dumps([finding.model_dump() for finding in isolated.findings]),
                ),
            )
