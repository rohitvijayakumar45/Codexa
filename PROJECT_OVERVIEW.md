# Codexa OS — Project Overview

Codexa OS is an **Engineering Intelligence Platform**. The core product is an **Engineering Knowledge Graph** along with the reasoning, verification, and learning systems built around it. It is designed to act as an "Engineering Brain," utilizing a graph of all code, architecture, history, and organizational knowledge to make intelligent decisions.

This project is built based on the architecture described in `codexa_os_build_prompt_v5.md` and enforces strict guidelines on code integration and simulation.

---

## Architecture Overview

The system processes and reasons about engineering artifacts through a multi-stage cognitive architecture:

1. **Perception**: Ingests code, issues, PRs, and documentation.
2. **Trust Boundary & Content Isolation**: Tags ingested artifacts with trust levels (e.g., `repo_owner`, `external_untrusted`). Untrusted text is strictly isolated as data and can never directly trigger tool calls or agents.
3. **Understanding**: Uses static analysis (Tree-sitter) and dependency extraction.
4. **Engineering Knowledge Graph**: The core entity storing nodes (e.g., `File`, `ArchitectureTrend`, `CausalEvent`) and temporal edges (e.g., `calls`, `causes`, `flows_into`) with confidence levels.
5. **Memory**: Manages semantic, episodic, procedural, and organizational memory.
6. **Planning**: Multi-agent systems determine execution strategies.
7. **Engineering Simulation Engine (Digital Twin)**: Any proposed code change is simulated against a digital twin to predict blast radius, test failures, and performance impact before affecting the real repo.
8. **Execution & Verification**: Code changes are run in a secure Docker sandbox and validated.
9. **Continuous Learning / Policy Distillation**: Evaluates accepted/reverted changes and incident outcomes to update internal policies and retrieval weights.

---

## Core Features & Subsystems

The backend is driven by several intelligent micro-subsystems:

* **Architecture Evolution Engine**: Tracks coupling, complexity, and file churn. It forecasts technical debt trends and highlights architectural bottlenecks.
* **Causal Engineering Graph**: Chains events (commit → deployment → incident) to map true causal relationships rather than just code dependencies.
* **Organizational Intelligence & Intent Graph**: Extracts team conventions, architectural decisions, and trade-offs from PR reviews and ADRs, ensuring agents write code that respects team culture.
* **Engineering Economics**: Estimates implementation effort, maintenance costs, and future tech-debt for any proposed change.
* **Repository Health Score**: Calculates an overall health score based on maintainability, coupling, architecture stability, and DORA metrics.
* **Incident Learning & Chaos Testing**: Extracts `PreventionRule`s from past incidents and runs pre-mortem fault injections (e.g., dropping DB connections) in ephemeral sandboxes to prevent regressions.
* **Engineering Time Machine**: An API to query or replay the graph's historical evolution at any past timestamp.

---

## The Knowledge Graph Visualization

As the platform's flagship frontend deliverable, the **Interactive Knowledge Graph Visualization** (`/graph-viz`) provides a live, 2.5D force-directed layout of the engineering brain.

**Key Visual Capabilities:**
* **Live Agent Traversal**: Nodes and edges pulse when actively traversed by reasoning agents.
* **Confidence-Mapped Edges**: Edge opacity and thickness map to the system's confidence in the relationship.
* **Time-Scrubber**: A draggable timeline that uses the Engineering Time Machine to replay the graph's historical evolution.
* **Cluster Drift & Causal Particles**: Architecture trends physically swell and destabilize on the graph when their health declines, and cause-effect chains animate with flowing particles.

---

## Technology Stack

* **Backend**: FastAPI
* **Storage Source of Truth**: PostgreSQL (JSONB)
* **Storage Projections**: Neo4j (Graph), Qdrant (Vector)
* **Queues & Scheduling**: Redis + RQ
* **Parsing**: Tree-sitter
* **Frontend Visualization**: React, Three.js
* **Sandbox**: Docker
