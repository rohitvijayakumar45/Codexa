from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class TrustLevel(StrEnum):
    REPO_OWNER = "repo_owner"
    VERIFIED_CONTRIBUTOR = "verified_contributor"
    EXTERNAL_UNTRUSTED = "external_untrusted"
    PUBLIC_SCRAPED = "public_scraped"


class ArtifactKind(StrEnum):
    ISSUE_BODY = "issue_body"
    PR_DESCRIPTION = "pr_description"
    COMMENT = "comment"
    SCRAPED_DOC = "scraped_doc"


class IsolationFinding(BaseModel):
    reason: str
    excerpt: str = Field(max_length=240)


class IngestArtifactRequest(BaseModel):
    source_uri: str = Field(min_length=1, max_length=2048)
    kind: ArtifactKind
    trust_level: TrustLevel
    content: str = Field(min_length=1)


class IsolatedArtifact(BaseModel):
    artifact_id: UUID
    source_uri: str
    kind: ArtifactKind
    trust_level: TrustLevel
    isolated_content: str
    instruction_content_removed: bool
    findings: list[IsolationFinding]
    safe_for_agent_context: bool
