from __future__ import annotations

from fastapi import APIRouter, status

from backend.execution.sandbox import SandboxExecutionService, SandboxRunRequest, SandboxRunResult


def create_execution_router(*, sandbox: SandboxExecutionService) -> APIRouter:
    router = APIRouter(prefix="/execution", tags=["execution"])

    @router.post(
        "/sandbox-runs",
        response_model=SandboxRunResult,
        status_code=status.HTTP_201_CREATED,
    )
    def schedule_sandbox_run(request: SandboxRunRequest) -> SandboxRunResult:
        return sandbox.schedule_run(request)

    return router
