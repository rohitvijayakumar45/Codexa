"""Persistent, cross-model memory store.

Holds the four memory types from the architecture — semantic, episodic, procedural, and
organizational — as durable records on disk so they survive restarts and are shared by every model
(chat injects the active repository's memory into the prompt regardless of which model is selected).

When a repository is loaded, a permanent memory bundle is written for it here.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

MEMORY_TYPES = ("semantic", "episodic", "procedural", "organizational")

DATA_DIR = Path(os.getenv("CODEXA_DATA_DIR", ".codexa"))


class MemoryRecord(BaseModel):
    id: str
    repository: str
    memory_type: str
    title: str
    content: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepositorySummary(BaseModel):
    repository: str
    counts: dict[str, int]
    total: int
    last_updated: datetime | None


class MemoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (DATA_DIR / "memories.json")
        self._lock = threading.Lock()
        self._records: list[MemoryRecord] = []
        self._load()
        if not self._records:
            self._seed_self()

    def _load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._records = [MemoryRecord(**item) for item in raw]
            except (json.JSONDecodeError, ValueError):
                self._records = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [json.loads(record.model_dump_json()) for record in self._records]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add(
        self,
        *,
        repository: str,
        memory_type: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"unknown memory_type: {memory_type}")
        record = MemoryRecord(
            id=str(uuid4()),
            repository=repository,
            memory_type=memory_type,
            title=title,
            content=content,
            created_at=datetime.now(UTC),
            metadata=metadata or {},
        )
        with self._lock:
            self._records.append(record)
            self._save()
        return record

    def remove(self, repository: str, source: str | None = None) -> int:
        """Drop a repository's memories (optionally only those from a given source). Returns count."""
        with self._lock:
            before = len(self._records)
            self._records = [
                r
                for r in self._records
                if not (r.repository == repository and (source is None or r.metadata.get("source") == source))
            ]
            removed = before - len(self._records)
            if removed:
                self._save()
            return removed

    def list(self, repository: str | None = None, memory_type: str | None = None) -> list[MemoryRecord]:
        return [
            r
            for r in self._records
            if (repository is None or r.repository == repository)
            and (memory_type is None or r.memory_type == memory_type)
        ]

    def has_repository(self, repository: str) -> bool:
        return any(r.repository == repository for r in self._records)

    def repositories(self) -> list[RepositorySummary]:
        summaries: dict[str, RepositorySummary] = {}
        for record in self._records:
            summary = summaries.get(record.repository)
            if summary is None:
                summary = RepositorySummary(
                    repository=record.repository,
                    counts={t: 0 for t in MEMORY_TYPES},
                    total=0,
                    last_updated=record.created_at,
                )
                summaries[record.repository] = summary
            summary.counts[record.memory_type] += 1
            summary.total += 1
            if summary.last_updated is None or record.created_at > summary.last_updated:
                summary.last_updated = record.created_at
        return sorted(summaries.values(), key=lambda s: s.repository)

    def context_block(self, repository: str, limit: int = 12) -> str:
        """A compact memory brief for injecting into any model's prompt."""
        records = self.list(repository=repository)[:limit]
        if not records:
            return ""
        lines = [f"Persistent memory for repository '{repository}':"]
        for r in records:
            lines.append(f"- [{r.memory_type}] {r.title}: {r.content}")
        return "\n".join(lines)

    def _seed_self(self) -> None:
        """Seed the platform's own repository so Memory has real content from the first load."""
        repo = "codexa-os"
        bundle = [
            ("semantic", "What Codexa OS is",
             "An engineering intelligence platform built around a temporal, confidence-weighted "
             "Engineering Knowledge Graph. FastAPI backend, Next.js frontend."),
            ("organizational", "Conventions",
             "Python with typed Pydantic v2 models on every route. Postgres JSONB as source of truth; "
             "Neo4j/Qdrant are projections. Untrusted content is isolated at a trust boundary."),
            ("procedural", "How to run it",
             "Backend: uvicorn backend.main:app --env-file .env (CODEXA_SEED=1). "
             "Frontend: npm --prefix graph-viz run dev."),
            ("episodic", "Origin",
             "Bootstrapped from codexa_os_build_prompt_v5. The knowledge graph is the flagship surface."),
        ]
        for mtype, title, content in bundle:
            self.add(repository=repo, memory_type=mtype, title=title, content=content,
                     metadata={"source": "seed"})
