from __future__ import annotations

from fastapi import APIRouter, status

from backend.graph.events import GraphEventWriter
from backend.perception.repository import ArtifactRepository
from backend.perception.schemas import IngestArtifactRequest, IsolatedArtifact
from backend.perception.trust_boundary import TrustBoundaryService


def create_perception_router(
    *,
    trust_boundary: TrustBoundaryService,
    artifact_repository: ArtifactRepository,
    event_writer: GraphEventWriter,
) -> APIRouter:
    router = APIRouter(prefix="/perception", tags=["perception"])

    @router.post(
        "/artifacts",
        response_model=IsolatedArtifact,
        status_code=status.HTTP_201_CREATED,
    )
    def ingest_artifact(request: IngestArtifactRequest) -> IsolatedArtifact:
        isolated = trust_boundary.isolate(request)
        artifact_repository.save(request, isolated)
        event_writer.append(
            event_type="artifact.ingested",
            aggregate_id=isolated.artifact_id,
            payload={
                "artifact_id": str(isolated.artifact_id),
                "source_uri": isolated.source_uri,
                "kind": isolated.kind,
                "trust_level": isolated.trust_level,
                "isolated_content": isolated.isolated_content,
                "instruction_content_removed": isolated.instruction_content_removed,
                "findings": [finding.model_dump() for finding in isolated.findings],
            },
        )
        return isolated

    return router
