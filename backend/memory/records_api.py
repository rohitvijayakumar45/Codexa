from __future__ import annotations

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from backend.memory.store import MEMORY_TYPES, MemoryRecord, MemoryStore, RepositorySummary


class MemoryCreate(BaseModel):
    repository: str = Field(min_length=1, max_length=256)
    memory_type: str = Field(pattern="^(semantic|episodic|procedural|organizational)$")
    title: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=4000)


def create_memory_store_router(*, store: MemoryStore) -> APIRouter:
    router = APIRouter(prefix="/memory", tags=["memory"])

    @router.get("/records", response_model=list[MemoryRecord])
    def list_records(
        repository: str | None = Query(default=None),
        memory_type: str | None = Query(default=None),
    ) -> list[MemoryRecord]:
        return store.list(repository=repository, memory_type=memory_type)

    @router.post("/records", response_model=MemoryRecord, status_code=status.HTTP_201_CREATED)
    def create_record(request: MemoryCreate) -> MemoryRecord:
        return store.add(
            repository=request.repository,
            memory_type=request.memory_type,
            title=request.title,
            content=request.content,
        )

    @router.get("/repositories", response_model=list[RepositorySummary])
    def list_repositories() -> list[RepositorySummary]:
        return store.repositories()

    @router.get("/types", response_model=list[str])
    def list_types() -> list[str]:
        return list(MEMORY_TYPES)

    return router
