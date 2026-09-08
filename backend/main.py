import logging
import os

from dotenv import load_dotenv

# Root cause of a real bug: nothing in this codebase ever loaded .env into the process — every
# key (GEMINI_API_KEY_2 included) sitting in .env was invisible to os.getenv() unless a real shell
# session happened to export it separately. That's why the Gemini key-failover mechanism in
# backend/agents/llm.py (correct on its own) silently never fired: LLMClient.__init__ only sees a
# second key when len(keys) > 1, and os.getenv("GEMINI_API_KEY_2") was returning None at runtime.
# MUST run before any backend import below - several modules (llm.py's LLMClient, in particular)
# read env vars at import/construction time, not lazily.
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

from backend.agents.api import create_agents_router
from backend.agents.coder import CoderService
from backend.agents.llm import LLMClient
from backend.agents.planner import PlannerService
from backend.agents.quorum import QuorumService
from backend.agents.research import ResearchAgentService
from backend.agents.retrieval import ContextAssemblyService
from backend.agents.impact import create_impact_router
from backend.chat.api import create_chat_router
from backend.observability.api import create_observability_router
from backend.docs_gen.api import create_docs_router
from backend.memory.records_api import create_memory_store_router
from backend.memory.context import create_context_router
from backend.memory.store import MemoryStore
from backend.repository.api import create_repository_router, rehydrate_repositories
from backend.files.api import create_files_router
from backend.graph.api import create_graph_router
from backend.graph.causal import CausalGraphService
from backend.graph.consistency import MultiStoreConsistencyService
from backend.graph.data_flow import DataFlowTracingService
from backend.graph.events import InMemoryGraphEventWriter, PostgresGraphEventWriter
from backend.graph.repository import InMemoryGraphRepository, PostgresGraphRepository
from backend.graph.service import GraphService
from backend.learning.api import create_learning_router
from backend.learning.policy_distillation import PolicyDistillationService
from backend.memory.api import create_memory_router
from backend.memory.services import (
    EngineeringDNAService,
    IntentGraphService,
    OrganizationalIntelligenceService,
)
from backend.perception.api import create_perception_router
from backend.perception.repository import InMemoryArtifactRepository, PostgresArtifactRepository
from backend.perception.trust_boundary import TrustBoundaryService
from backend.execution.api import create_execution_router
from backend.execution.sandbox import SandboxExecutionService
from backend.simulation.api import create_simulation_router
from backend.simulation.chaos import ChaosPremortemService
from backend.simulation.engine import EngineeringSimulationEngine
from backend.trust_safety.api import create_trust_safety_router
from backend.trust_safety.confidence import ConfidenceCalibrationService
from backend.trust_safety.economics import EngineeringEconomicsService
from backend.trust_safety.health import RepositoryHealthService
from backend.trust_safety.incident import IncidentLearningService
from backend.trust_safety.policy import PolicyEngine
from backend.trust_safety.verification import VerificationService
from backend.understanding.api import create_understanding_router
from backend.understanding.architecture_evolution import ArchitectureEvolutionService
from backend.understanding.nightly_review import NightlyArchitectureReviewService


_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


class _CatchUnhandledMiddleware(BaseHTTPMiddleware):
    """Turns an unhandled exception into a clean JSON 500 instead of an opaque connection drop.

    This has to be a real ASGI middleware (added to the stack via app.add_middleware), not an
    `@app.exception_handler(Exception)` — Starlette special-cases a handler registered for the bare
    `Exception`/500 key by handing it to ServerErrorMiddleware, which sits OUTSIDE CORSMiddleware.
    ServerErrorMiddleware sends that handler's response over the raw, pre-CORS `send` it was given
    (CORSMiddleware never gets a chance to wrap it, since the exception propagated up past
    CORSMiddleware without it ever sending anything), so an exception_handler-based response reaches
    the browser with no Access-Control-Allow-Origin header — the browser reports it as a
    network-level "Failed to fetch", masking every backend error as "server unreachable" (confirmed
    via TestClient vs real uvicorn — same code, header present in-process, missing over real HTTP).
    A BaseHTTPMiddleware, registered BEFORE CORSMiddleware (so CORSMiddleware ends up wrapping it,
    per Starlette's add_middleware inserting each new one at the front of the stack), instead runs
    INSIDE CORSMiddleware — its response passes through CORSMiddleware's normal per-request header
    injection exactly like a real 200 OK would, and CORSMiddleware handles the origin-matching
    itself instead of this needing to reimplement it.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 - last-resort handler, must not itself raise
            logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
            return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


def create_app() -> FastAPI:
    app = FastAPI(title="Codexa OS", version="0.1.0")
    # Order matters: add_middleware inserts each new middleware at the front of the stack, so
    # adding the catch-all BEFORE CORSMiddleware makes CORSMiddleware end up outermost — meaning it
    # wraps (and applies its header logic to) the catch-all's responses. See the class docstring.
    app.add_middleware(_CatchUnhandledMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_DEV_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    database_url = os.getenv("CODEXA_DATABASE_URL") or os.getenv("DATABASE_URL")
    if database_url:
        artifact_repository = PostgresArtifactRepository(database_url)
        graph_repository = PostgresGraphRepository(database_url)
        event_writer = PostgresGraphEventWriter(database_url)
    else:
        artifact_repository = InMemoryArtifactRepository()
        graph_repository = InMemoryGraphRepository()
        event_writer = InMemoryGraphEventWriter()

    graph_service = GraphService(repository=graph_repository, event_writer=event_writer)
    data_flow_service = DataFlowTracingService(graph=graph_service)
    causal_graph_service = CausalGraphService(graph=graph_service)
    consistency_service = MultiStoreConsistencyService(event_writer=event_writer)
    llm_client = LLMClient()
    planner_service = PlannerService(repository=graph_repository, event_writer=event_writer, llm=llm_client)
    coder_service = CoderService(event_writer=event_writer, llm=llm_client)
    research_service = ResearchAgentService(graph=graph_service, llm=llm_client)
    quorum_service = QuorumService(llm=llm_client, graph=graph_service)
    retrieval_service = ContextAssemblyService(
        repository=graph_repository,
        event_writer=event_writer,
        llm=llm_client,
    )
    verification_service = VerificationService(event_writer=event_writer)
    policy_engine = PolicyEngine(event_writer=event_writer)
    confidence_service = ConfidenceCalibrationService(graph=graph_service)
    economics_service = EngineeringEconomicsService(graph=graph_service)
    health_service = RepositoryHealthService(graph=graph_service)
    incident_learning_service = IncidentLearningService(graph=graph_service)
    simulation_engine = EngineeringSimulationEngine(graph=graph_service, planner=planner_service)
    chaos_premortem_service = ChaosPremortemService(event_writer=event_writer)
    sandbox_execution_service = SandboxExecutionService(event_writer=event_writer, graph=graph_service)
    architecture_evolution_service = ArchitectureEvolutionService(graph=graph_service)
    nightly_review_service = NightlyArchitectureReviewService(
        graph=graph_service,
        architecture_evolution=architecture_evolution_service,
    )
    intent_graph_service = IntentGraphService(graph=graph_service)
    organizational_intelligence_service = OrganizationalIntelligenceService(graph=graph_service)
    engineering_dna_service = EngineeringDNAService(graph=graph_service)
    policy_distillation_service = PolicyDistillationService(graph=graph_service)
    trust_boundary = TrustBoundaryService()

    app.state.artifact_repository = artifact_repository
    app.state.graph_repository = graph_repository
    app.state.graph_event_writer = event_writer
    app.include_router(
        create_perception_router(
            trust_boundary=trust_boundary,
            artifact_repository=artifact_repository,
            event_writer=event_writer,
        )
    )
    app.include_router(
        create_graph_router(
            graph=graph_service,
            data_flow=data_flow_service,
            causal_graph=causal_graph_service,
            consistency=consistency_service,
        )
    )
    app.include_router(
        create_agents_router(
            planner=planner_service,
            coder=coder_service,
            research=research_service,
            retrieval=retrieval_service,
            quorum=quorum_service,
        )
    )
    app.include_router(
        create_simulation_router(engine=simulation_engine, chaos=chaos_premortem_service)
    )
    app.include_router(
        create_trust_safety_router(
            verification=verification_service,
            policy=policy_engine,
            confidence=confidence_service,
            economics=economics_service,
            health=health_service,
            incidents=incident_learning_service,
            graph=graph_service,
        )
    )
    app.include_router(create_execution_router(sandbox=sandbox_execution_service))
    app.include_router(
        create_understanding_router(
            architecture_evolution=architecture_evolution_service,
            nightly_review=nightly_review_service,
        )
    )
    app.include_router(
        create_memory_router(
            intent_graph=intent_graph_service,
            organizational_intelligence=organizational_intelligence_service,
            engineering_dna=engineering_dna_service,
        )
    )
    app.include_router(
        create_learning_router(policy_distillation=policy_distillation_service)
    )
    memory_store = MemoryStore()
    app.state.memory_store = memory_store
    app.include_router(create_impact_router(graph=graph_service, planner=planner_service))
    app.include_router(create_memory_store_router(store=memory_store))
    app.include_router(create_context_router(store=memory_store, graph=graph_service))
    app.include_router(create_repository_router(store=memory_store, graph=graph_service, llm=llm_client))

    # Development seed: with no database configured, the in-memory graph boots empty. When
    # CODEXA_SEED is enabled we populate it with real, self-referential "codexa-os" data so the
    # frontend reads a live backend instead of fabricating mock data. seed_graph no-ops as soon as
    # ANY node already exists (graph.list_nodes() is non-empty) — it MUST run before
    # rehydrate_repositories below, not after. rehydrate_repositories re-ingests every real repo
    # previously loaded from `.codexa/repos/*` on disk (the in-memory graph itself doesn't survive
    # a restart, but those clones do), and on any machine with real repos already loaded, that
    # happens on every single boot — permanently starving the seed check of the "still empty" state
    # it needs, so codexa-os's own graph/architecture tabs read empty forever even with
    # CODEXA_SEED=1 set. Order here is load-bearing.
    if not database_url and os.getenv("CODEXA_SEED", "").strip().lower() in {"1", "true", "yes", "on"}:
        from backend.seed import seed_graph

        seed_graph(
            graph=graph_service,
            causal=causal_graph_service,
            architecture=architecture_evolution_service,
            health=health_service,
        )

    # Rebuilding every previously-loaded repo's graph is right for a real server boot and wrong for
    # anything constructing an app to inspect it: it walks `.codexa/repos/*` on the host's actual
    # disk, so create_app() quietly inherits whatever that developer happens to have loaded. Under
    # pytest that meant ~1600 real graph events landing in tests asserting a pristine event log —
    # eight failures that looked like unrelated product bugs and were really one environment leak.
    # Defaults to on, so production behaviour is unchanged; the test suite opts out (tests/conftest.py).
    if os.getenv("CODEXA_REHYDRATE", "1").strip().lower() not in {"0", "false", "no", "off"}:
        rehydrate_repositories(store=memory_store, graph=graph_service)
    app.include_router(create_files_router())
    app.include_router(create_chat_router(llm=llm_client, graph=graph_service, store=memory_store))
    app.include_router(create_observability_router(event_writer=event_writer, llm=llm_client))
    app.include_router(create_docs_router(llm=llm_client))

    return app


app = create_app()
