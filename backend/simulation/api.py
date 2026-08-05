from __future__ import annotations

from fastapi import APIRouter, status

from backend.simulation.chaos import ChaosPremortemRequest, ChaosPremortemResult, ChaosPremortemService
from backend.simulation.engine import EngineeringSimulationEngine, SimulationRequest, SimulationResult


def create_simulation_router(
    *, engine: EngineeringSimulationEngine, chaos: ChaosPremortemService
) -> APIRouter:
    router = APIRouter(prefix="/simulation", tags=["simulation"])

    @router.post(
        "/scenarios",
        response_model=SimulationResult,
        status_code=status.HTTP_201_CREATED,
    )
    def run_simulation(request: SimulationRequest) -> SimulationResult:
        return engine.run(request)

    @router.post(
        "/chaos/pre-mortems",
        response_model=ChaosPremortemResult,
        status_code=status.HTTP_201_CREATED,
    )
    def plan_chaos_premortem(request: ChaosPremortemRequest) -> ChaosPremortemResult:
        return chaos.plan(request)

    return router
