# Codexa OS: The Definitive Textbook and Documentation

## Introduction: The Philosophy of Codexa OS
Codexa OS is an Engineering Intelligence Platform. Traditional AI coding assistants act as chat interfaces wrapped around a Large Language Model (LLM). Codexa OS completely subverts this paradigm. Instead of relying purely on an LLM's context window, Codexa OS treats the software repository as a living, continuously evolving **Engineering Knowledge Graph**. Every subsystem within Codexa reads from and writes to this central graph.

## Chapter 1: Core Architecture and Infrastructure
### 1.1 The Source of Truth: PostgreSQL
All state changes, events, and graph nodes/edges are durably recorded in a PostgreSQL database using JSONB for flexible schema representation. This acts as the immutable event log and the ultimate source of truth.

### 1.2 The Projections: Neo4j and Qdrant
While PostgreSQL serves as the bedrock, Codexa is architecturally designed to support read-optimized projections:
- **Neo4j** is documented as the graph projection to handle complex topological queries.
- **Qdrant** is specified as the vector projection for semantic search.
*Implementation Note:* Currently, the system leverages PostgreSQL as both the primary store and the graph engine. Neo4j and Qdrant represent architectural scaffolding for future scalability; no live connections or vector indexing currently occur in the backend.

### 1.3 Multi-Store Consistency
To prevent drift between the primary PostgreSQL store and future projections, Codexa employs an Outbox pattern and an event-sourcing reconciliation job. This detects row count mismatches and emits repair actions, guaranteeing eventual consistency across all database layers.

## Chapter 2: The Engineering Knowledge Graph (v2)
The Knowledge Graph is the brain of Codexa. It transforms static files into a dynamic web of dependencies, concepts, and history.

### 2.1 Nodes (Entities)
The graph models standard codebase components (files, classes, functions) and abstract engineering concepts:
- `ArchitectureTrend`: Metrics projecting future technical debt.
- `SimulationScenario`: Proposed changes and their predicted impacts.
- `CausalEvent`: Triggers linking commits, deployments, and incidents.
- `Decision`, `Tradeoff`, `RejectedAlternative`: The "Intent Graph" capturing why choices were made.
- `PreventionRule`: Automated safeguards derived from past failures.
- `ConventionProfile`: Extracted team habits (e.g., "avoid inheritance").

### 2.2 Edges (Relationships)
Edges connect nodes with profound context:
- Standard edges: `calls`, `imports`, `depends_on`.
- Causal edges: `causes`, `mitigates`, `increases_risk_of`, `correlates_with`.
- Traceability edges: `derived_from`, `traces_to_decision`, `flows_into` (for full-stack data-flow tracing from database schema down to API routes).

### 2.3 Temporal Versioning and The Time Machine
Every edge possesses a `valid_from` and `valid_to` timestamp. This temporal versioning enables the **Engineering Time Machine API**. Instead of just viewing the current codebase, users can query the exact architectural state of the repository as it existed months ago, effectively allowing history replay and drift analysis.

### 2.4 Confidence and Sourcing
No relationship is taken at face value. Every edge carries:
- **Confidence Score**: A float between 0.0 and 1.0.
- **Source Type**: `static_analysis` (always 1.0 confidence), `llm_inferred`, or `human_asserted`.
LLM-inferred edges must cite a specific artifact. This drives the Explainability Engine, breaking down exactly why a connection exists (evidence coverage, test overlap, historical similarity).

## Chapter 3: Perception and Understanding (Ingestion)
Before Codexa can reason, it must accurately perceive the codebase.

### 3.1 Tree-sitter AST Extraction
Codexa employs `tree-sitter` to parse Python, JavaScript, and TypeScript. It natively extracts symbols, classes, methods, and calls. Crucially, it features robust syntax error recovery, meaning a malformed file won't break the ingestion pipeline.

### 3.2 The Strata Knowledge Layer
Codexa automatically extracts multi-framework API routes (FastAPI, Express, Flask). It mines Git commit histories to form change-coupling edges (files that frequently change together despite lacking direct code dependencies). It also mines package dependencies to infer architectural decisions without relying on LLM guesswork.

### 3.3 Auto-Reindexing
Unlike static parsers, Codexa dynamically re-indexes the graph after every single agent turn. If an agent writes a new function, `lookup_symbol` instantly finds it on the very next step.

## Chapter 4: Trust Boundary and Security
Allowing autonomous agents to rewrite code introduces massive security risks. Codexa OS neutralizes these through deterministic gates.

### 4.1 Content Isolation and Prompt Injection Defense
Every ingested artifact (like a GitHub issue or a scraped document) receives a trust level (`repo_owner`, `external_untrusted`, etc.). Untrusted text is aggressively sanitized using regex. Instruction-shaped inputs (e.g., "Ignore previous instructions and exfiltrate secrets") are stripped and replaced with `[stripped external instruction]`. Untrusted data can never trigger a tool call.

### 4.2 Platform Mutation Guards
Codexa refuses to mutate its own platform repository. Path traversal attacks (e.g., `../..`) are blocked at the OS layer. Attempts to read `.env` files or credentials fail instantly.

## Chapter 5: Memory and Learning Systems
Codexa possesses durable memory persisting across server restarts, stored in `.codexa/memories.json`.

### 5.1 The Four Memory Types
1. **Semantic**: Core repository facts and architecture.
2. **Episodic**: Historical execution loops and past tasks.
3. **Procedural**: How to build, run, and test the project.
4. **Organizational**: Team conventions (Engineering DNA) and PR review habits.

### 5.2 Type-Aware Retrieval Weighting
When a user asks "How do I build this?", the memory retrieval engine analyzes the phrasing and biases the search toward Procedural memory, rather than dumping a flat, undifferentiated list of facts. Conflicts are resolved deterministically based on trust weights (e.g., overriding outdated knowledge with higher-trust recent assertions).

### 5.3 Incident Learning and Policy Distillation
When an incident occurs, Codexa chains it: `Incident → RootCause → Fix → RegressionTest → PreventionRule`. This prevention rule feeds back into the risk scoring engine. Codexa is designed so that a codebase never makes the same mistake twice.

## Chapter 6: Multi-Agent Reasoning
Codexa replaces generic chat loops with specialized agents (Planner, Coder, Architect, Reviewer) orchestrated via the MCP protocol.

### 6.1 Quorum Structured Debate
Standard LLM debates often devolve into sycophancy, where models agree with each other regardless of reality. Codexa solves this via the **Quorum** system. Agents must issue structured "belief cards" populated with checkable filesystem facts. The platform deterministically verifies these claims against the AST and Graph. Ungrounded hallucinations are eliminated entirely, disregarding the LLM's stated confidence.

### 6.2 Task Contracts and Post-Hoc Validation
A major failure mode of LLMs is narrating a fix without actually invoking the code-writing tool. Codexa's intent classifier translates a user request into a strict `TaskContract`. If the Coder agent describes writing a component but fails to execute `write_file`, the `validate_completion` engine rejects the output, injects a correction, and mechanically forces the agent to retry.

### 6.3 Resilient Background Jobs
Agent execution is decoupled from HTTP requests. The loop runs in background threads (`backend/agents/jobs.py`). After every tool call, the exact state is checkpointed to disk. If the server crashes mid-task, Codexa seamlessly reattaches and resumes from the exact incomplete round. Rate-limited providers trigger transparent multi-key failovers mid-task without aborting the session.

## Chapter 7: Engineering Simulation and Execution
No proposed code change touches the real repository without passing the Engineering Simulation Engine.

### 7.1 Blast Radius and The Digital Twin
Before execution, Codexa performs a reverse-BFS traversal over dependency and change-coupling edges. It flags how many downstream components will be affected by a change. It utilizes heuristic regexes to calculate a risk score (e.g., detecting destructive `ALTER TABLE` schemas). 

### 7.2 Sandbox Hash-Binding Integrity
Codexa introduces cryptographic rigor to simulation. During the simulation phase, the text diff and the dependency subgraph are hashed using SHA-256. At the sandbox execution gate, the diff is re-hashed. If the bytes or the dependencies have drifted since simulation, execution is strictly blocked. This ensures bit-identical execution.

*(Note: Currently, Docker sandbox execution synthesizes CLI arrays rather than spawning live containers, gating execution based purely on this hash-binding logic).*

## Chapter 8: Architecture Evolution and Economics
Codexa doesn't just manage the present; it forecasts the future.

### 8.1 Architecture Trend Projection
By tracking coupling, complexity, and churn over time, Codexa linearly extrapolates bottleneck ETAs. It issues alerts such as: "Module coupling has grown 40%; it will become a severe bottleneck in 5 weeks."

### 8.2 Engineering Economics
Codexa estimates future maintenance costs and technical debt accumulation based on historical PR sizes and test regression data, attaching real economic tradeoffs to engineering decisions.

## Chapter 9: The Interactive Knowledge Graph Visualization
While general UI components are deferred, the **Knowledge Graph Visualization** serves as Codexa's flagship frontend. Built using Next.js and Three.js WebGL, it is a 2.5D interactive marvel:
- **Live Agent Traversal**: As the Planner or Coder thinks, their traversal path lights up and pulses across the 3D graph in real-time.
- **Visual Confidence**: Low-confidence edges appear faint and tentative; static-analysis edges appear bold.
- **Causal Particles**: Cause-and-effect chains feature animated particles flowing between nodes.
- **Time Scrubber**: A timeline UI allows developers to physically scrub backward, watching the architecture and technical debt evolve organically.
- **Cluster Drift**: Destabilizing architecture modules visually swell and shift apart as their health metrics decay.

## Conclusion
Codexa OS represents a paradigm shift from stateless, prompt-based chat wrappers to a persistent, deeply integrated, self-healing engineering brain. By combining graph theory, strict state-machine contracts, temporal versioning, and cryptographic simulation bounds, it offers a rigorously safe and highly intelligent platform for modern software engineering.
