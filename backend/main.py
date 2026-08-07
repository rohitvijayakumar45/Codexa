import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.api import create_agents_router
from backend.agents.coder import CoderService
from backend.agents.llm import LLMClient
from backend.agents.planner import PlannerService
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


def create_app() -> FastAPI:
    app = FastAPI(title="Codexa OS", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
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
    rehydrate_repositories(store=memory_store, graph=graph_service)
    app.include_router(create_files_router())
    app.include_router(create_chat_router(llm=llm_client, graph=graph_service, store=memory_store))
    app.include_router(create_observability_router(event_writer=event_writer, llm=llm_client))
    app.include_router(create_docs_router(llm=llm_client))

    # Development seed: with no database configured, the store boots empty. When CODEXA_SEED is
    # enabled we populate the in-memory graph with real, self-referential data so the frontend
    # reads a live backend instead of fabricating mock data.
    if not database_url and os.getenv("CODEXA_SEED", "").strip().lower() in {"1", "true", "yes", "on"}:
        from backend.seed import seed_graph

        seed_graph(
            graph=graph_service,
            causal=causal_graph_service,
            architecture=architecture_evolution_service,
            health=health_service,
        )

    return app


app = create_app()
