# Codexa OS Internal Architecture

## 1. Overview
Codexa OS is an Engineering Intelligence Platform that treats the repository as a living, continuously evolving knowledge graph. It relies on rigorous projection-based architecture, simulation engines, and autonomous agents to provide reasoning, verification, and continuous learning over the codebase.

## 2. Core Architecture & Persistence
- **Backend Stack:** FastAPI (Python 3.12).
- **Primary Source of Truth:** PostgreSQL (JSONB Event Log). All state changes are written here first.
- **Projections:** Neo4j (Graph representation of the codebase, history, and metadata) and Qdrant (Vector semantic search). Projections are strictly read-optimized and rebuilt from the Postgres event stream via asynchronous workers (Redis + RQ). Direct writes to Neo4j/Qdrant outside of the projection pipeline are prohibited.
- **Multi-Store Consistency:** A reconciliation job periodically heals drift between the event log and projections.
- **Execution Sandbox:** Isolated Docker environments ensure safe command execution, engineering simulation, and pre-mortem chaos testing.

## 3. Engineering Knowledge Graph (v2 Schema)
- **Entities (Nodes):** Include codebase components and abstract concepts like `ArchitectureTrend`, `SimulationScenario`, `CausalEvent`, `Decision`, `Tradeoff`, `RejectedAlternative`, `HealthMetric`, and `PreventionRule`.
- **Relationships (Edges):** Edges natively support temporal versioning (`valid_from`, `valid_to`) to power the Engineering Time Machine API. Every edge requires a `confidence` score (0-1) and a `source_type` (`static_analysis` [confidence=1.0], `llm_inferred`, or `human_asserted`). LLM-inferred edges must explicitly cite their source artifact.

## 4. Major Subsystems
- **Perception & Trust Boundary:** Ingests external artifacts (issues, PRs, docs). Untrusted content is tagged (`external_untrusted`, `public_scraped`) and strictly isolated from execution. Instruction-shaped text is stripped to prevent indirect prompt injection.
- **Understanding:** Uses Tree-sitter for parsing, dependency extraction, and static analysis to feed the semantic model.
- **Memory (Semantic, Episodic, Procedural, Organizational):** Stores inferred repo conventions (Engineering DNA), tracks historical execution loops, and mines organizational intelligence (e.g., team-specific PR review patterns) to guide agent behavior.
- **Agents:** A suite of specialized MCP-coordinated agents (Planner, Architect, Coder, Reviewer, QA, Security, Research, DevOps).
- **Engineering Simulation Engine:** Sits between planning and execution. Simulates the blast radius of proposed changes (`ImpactRequest`, `BlastRadius`), dependency propagation, schema impact, and rollback viability before any code is modified.
- **Trust & Safety / Incident Learning:** Converts incidents into causal chains (`Incident → RootCause → Fix → RegressionTest → PreventionRule`). Feeds the risk scoring and policy engine.
- **Learning (Policy Distillation):** Continuously distills accepted changes and incident outcomes into updated prompt templates, context retrieval weights, and risk calibration metrics.

## 5. Execution Control & State Transitions
- **JobManager:** Handles resilient execution. Jobs maintain an append-only event log (`_events_path`) and atomic checkpoints to ensure perfect recoverability across restarts or flaky network interactions.
- **ExecutionController:** Owns strict plan advancement. Tasks are completed mechanically by Codexa validators, not by LLMs self-reporting completion. The controller relies on exact tool-call matching, exact capability checks (e.g., `DesignIntent`), and automatic intervention/recovery loops for stalled tasks.
- **Context Compaction:** Aggressively compacts stale tool payloads to save tokens, selectively preserving file contexts based on the current active blast radius (`relevant_paths`) and pinning critical instructions (e.g., design guidance).

## 6. Model & Provider Interaction
- **LLMClient:** Manages robust model interactions with sliding-window rate limiting (`_RateLimiter`) and intelligent key management.
- **Multi-Key Rotation & Failover:** Groups buckets by model and API key. If a rate limit or mid-stream fallback error is hit before streaming begins, it transparently fails over to the next configured key.
- **Worker & Failover Rings:** Models are tiered. Execution gracefully degrades through fallback model rings if primary models exhaust limits or stall, ensuring continuous agent operation.

## 7. Knowledge Graph Visualization (graph-viz)
The flagship frontend application, built with Next.js, TailwindCSS, and Three.js (WebGL force-directed layout).
- **Features:** 
  - Live agent traversal (watching the agent's path pulse in real time)
  - Confidence-mapped edges (thickness and opacity map to certainty)
  - Time-scrubber for history replay via the Engineering Time Machine API
  - Causal propagation particles (animating `causes` chains)
  - Interactive explainability panels and cluster drift visualization from the Architecture Evolution Engine.
