from __future__ import annotations

import re
from uuid import uuid4

from backend.perception.schemas import (
    IngestArtifactRequest,
    IsolatedArtifact,
    IsolationFinding,
    TrustLevel,
)


UNTRUSTED_LEVELS = {
    TrustLevel.EXTERNAL_UNTRUSTED,
    TrustLevel.PUBLIC_SCRAPED,
}


INSTRUCTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "prompt_override",
        re.compile(r"\b(ignore|forget|discard)\b.{0,80}\b(previous|prior|above|system|developer)\b", re.I),
    ),
    (
        "tool_invocation",
        re.compile(r"\b(run|execute|call|invoke|use)\b.{0,80}\b(tool|shell|terminal|powershell|cmd|curl|wget)\b", re.I),
    ),
    (
        "secret_exfiltration",
        re.compile(r"\b(print|dump|exfiltrate|send|upload)\b.{0,80}\b(secret|token|api[_ -]?key|env)\b", re.I),
    ),
    (
        "destructive_instruction",
        re.compile(r"\b(delete|remove|drop|wipe|overwrite)\b.{0,80}\b(file|repo|database|table|directory)\b", re.I),
    ),
)


class TrustBoundaryService:
    """Converts external artifact text into safe agent-context data."""

    def isolate(self, artifact: IngestArtifactRequest) -> IsolatedArtifact:
        if artifact.trust_level not in UNTRUSTED_LEVELS:
            return IsolatedArtifact(
                artifact_id=uuid4(),
                source_uri=artifact.source_uri,
                kind=artifact.kind,
                trust_level=artifact.trust_level,
                isolated_content=artifact.content,
                instruction_content_removed=False,
                findings=[],
                safe_for_agent_context=True,
            )

        isolated_lines: list[str] = []
        findings: list[IsolationFinding] = []

        for line in artifact.content.splitlines():
            reasons = self._instruction_reasons(line)
            if reasons:
                findings.extend(
                    IsolationFinding(reason=reason, excerpt=line.strip()[:240])
                    for reason in reasons
                )
                isolated_lines.append("[stripped external instruction]")
            else:
                isolated_lines.append(line)

        return IsolatedArtifact(
            artifact_id=uuid4(),
            source_uri=artifact.source_uri,
            kind=artifact.kind,
            trust_level=artifact.trust_level,
            isolated_content="\n".join(isolated_lines),
            instruction_content_removed=bool(findings),
            findings=findings,
            safe_for_agent_context=True,
        )

    def _instruction_reasons(self, text: str) -> list[str]:
        return [reason for reason, pattern in INSTRUCTION_PATTERNS if pattern.search(text)]
