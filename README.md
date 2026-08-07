# Codexa OS

**The Engineering Intelligence Platform.**

Codexa OS is an advanced Engineering Intelligence Platform that treats your repository as a living knowledge graph. It goes beyond simple chat interfaces, providing reasoning, verification, and continuous learning systems to help you understand, simulate, and evolve complex architectures.

## Core Architecture

Codexa OS is built on a rigorous, projection-based architecture:
- **Backend:** FastAPI (Python 3.12)
- **Primary Source of Truth:** PostgreSQL (JSONB Event Log)
- **Projections:** Neo4j (Graph), Qdrant (Vector)
- **Parsing & Extraction:** Tree-sitter
- **Execution & Sandbox:** Docker
- **Frontend:** Next.js (App Router), TailwindCSS, Three.js (3D Graph Visualizer)

## Key Subsystems

The platform operates across several distinct cognitive subsystems:

1. **Perception:** Ingests pipelines and enforces the Trust Boundary Layer to safely isolate untrusted external content (e.g., public scraped data) from verified assertions.
2. **Understanding:** Employs static analysis, dependency extraction, and architecture evolution tracking to build a semantic model of your codebase.
3. **Memory:** Manages Semantic, Episodic, Procedural, and Organizational memory layers, creating an interconnected web of design intent and historical context.
4. **Graph & Time Machine:** Maintains the core Neo4j schema and allows query replay through time, letting you inspect the exact state of the graph at any historical point.
5. **Agents:** A suite of specialized, autonomous agents (Planner, Architect, Coder, Reviewer, QA, Security, Docs, Research) coordinated via MCP.
6. **Engineering Simulation Engine:** Every proposed change is simulated for impact (Blast Radius) before reaching execution.
7. **Trust & Safety:** A risk scoring and policy engine that verifies pipelines, asserts confidence levels, and guards against unauthorized actions.
8. **Learning:** Continuous policy distillation jobs that refine agent behavior over time.

## Getting Started

### Prerequisites
- Python 3.12+
- Node.js 20+
- PostgreSQL, Neo4j, Qdrant (Managed via Docker Compose)

### 1. Environment Setup

Copy `.env.example` to `.env` and fill in your API keys:
```env
LLM_PROVIDER=nvidia_nim
NVIDIA_API_KEY=...
CODEXA_SEED=1
```

### 2. Backend (FastAPI)

```bash
# Install dependencies
python -m pip install -e .[dev]

# Start the API server
# Note: CODEXA_SEED=1 will populate an in-memory test graph if no DB is connected
$env:CODEXA_SEED="1"
python -m uvicorn backend.main:app --port 8090 --reload
```

### 3. Frontend (Next.js)

```bash
cd graph-viz

# Install dependencies
npm install

# Start the development server
npm run dev
```

The application will be available at [http://localhost:3000](http://localhost:3000).

## Core Principles

- **No Black Boxes:** Every LLM-inferred edge in the graph explicitly cites its source artifact and carries a calculated confidence score (0-1).
- **Graph Projections:** We never write directly to Neo4j or Qdrant outside the projection pipeline. The Postgres event log is the single source of truth.
- **Safety First:** No proposed change hits the execution sandbox without passing through the simulation engine and blast radius checks.
- **Premium Aesthetics:** The frontend relies on spatial glassmorphism, fluid micro-animations, and striking typography to deliver a state-of-the-art developer experience.

## License

Proprietary / Internal Use Only.
