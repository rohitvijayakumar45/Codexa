# Codexa OS

**An engineering-intelligence platform that treats a repository as a living knowledge graph.**

Codexa OS ingests a codebase with real parsers (not text pattern-matching), builds a structural
graph of it, layers persistent project memory on top, and puts an LLM agent behind both — so the
agent answers, plans, and builds against a grounded map of the code instead of re-reading files
from scratch on every turn. A live 3D visualization of that graph sits alongside a chat/build
interface in the frontend.

**The core claim is measured, not asserted:** answering the same code-navigation question from the
graph costs **85.8× fewer tokens (98.8% less)** than answering it by reading raw source files —
measured deterministically across 5 real repositories and 174 code symbols, with no LLM in the
loop to introduce variance. See [`docs/graph_token_reduction_proof.md`](docs/graph_token_reduction_proof.md)
for the full write-up and [`tests/benchmarks/memory_graph/retrieval_payload.py`](tests/benchmarks/memory_graph/retrieval_payload.py)
to reproduce it.

---

## What's actually implemented

This section states plainly what exists today, not what's planned — Codexa's own code carries the
same discipline (`backend/seed.py` seeds an honest self-description of the architecture into its
own graph, including the alternatives it rejected).

| Layer | Status |
|---|---|
| **Structural graph** | Real — parsed via [tree-sitter](https://tree-sitter.github.io/) (Python, JavaScript, TypeScript, TSX) into nodes (files/functions/classes) and edges (imports/calls/dependencies). In-memory by default; durable when `CODEXA_DATABASE_URL` points at Postgres (event-sourced, JSONB-backed, idempotent schema bootstrap). |
| **Symbol annotations** | Real — an LLM pass writes a one-line semantic gloss per symbol on top of the structural parse, cached by content hash so unchanged code is never re-annotated. |
| **Project memory** | Real — four durable, model-agnostic memory types: `semantic`, `episodic`, `procedural`, `organizational`. Shared by every LLM working on the project, persisted to disk, survives restarts. |
| **Blast radius / impact analysis** | Real — reverse-dependency graph traversal surfaces every node reachable from a change before the change is made. The same traversal also drives graph-distance-aware context eviction, so stale tool payloads are dropped based on structural relevance, not a flat round-count. |
| **Quorum** | Real — multiple agents answer independently and are checked against the graph *before* seeing a peer's answer; only genuine ties reach a debate round, and that round exchanges structured, verified belief cards rather than free-text — closing the sycophancy vector unrestricted LLM debate opens. |
| **Multi-provider LLM routing** | Real — [litellm](https://github.com/BerriAI/litellm)-based router across 14+ providers (NVIDIA NIM, Gemini, Groq, Upstage, Cerebras, Mistral, Z.ai, OpenRouter, Bedrock, local Ollama, and more), with tier-based model selection, per-key rotation, and error-classified failover (rate-limit vs. transient-upstream vs. dead-key). |
| **Browser tools** | Real — a persistent, thread-marshalled headless-browser session (Playwright) so an agent can navigate, click, type, and read console/network output across a sequence of tool calls, not just one-shot screenshots. |
| **Neo4j / Qdrant projections** | **Not implemented, and not planned** — evaluated and explicitly rejected as unjustified infrastructure/sync complexity at single-repository scale. Python traversal over the graph (in-memory or Postgres-backed) covers current needs; there is no separate vector/semantic-search database — see `backend/repository/semantic.py` for the embedding-based approach actually used. |
| **Docker execution sandbox** | Modeled (`backend/execution/sandbox.py` defines the request/status contract — `blocked` / `scheduled`) but not wired to a live container runtime yet. |
| **MCP agent coordination** | Not implemented. Agent orchestration is direct (`backend/agents/jobs.py`, `controller.py`), not MCP-based. |

## Why the graph, not raw file search

An LLM agent that answers "where is X defined and what calls it?" by opening files pays for every
byte of every file it reads, and on genuinely hard multi-hop questions this can make an agent loop
without ever converging — in testing this repo's benchmarking surfaced single runs reaching
**300K–1.9M tokens with no answer**. The same question answered from the graph is one targeted
lookup: the definition site plus every caller/dependent, nothing else.

| Repository | Raw file-read tokens | Graph-retrieval tokens | Reduction |
|---|---:|---:|---:|
| gods-eye-view | 813,852 | 3,764 | **216×** |
| Exam-Proctoring | 609,888 | 8,081 | **75×** |
| Tourism-Management | 278,000 | 5,026 | **55×** |
| MOMENTUM | 34,620 | 816 | **42×** |
| FitQuest | 124,443 | 3,997 | **31×** |
| **Aggregate (174 symbols)** | **1,860,803** | **21,684** | **85.8×** |

Reproduce: `BENCHMARK_REPO=<repo> python tests/benchmarks/memory_graph/retrieval_payload.py`
(deterministic, fixed random seed, no LLM in the loop).

## Architecture

- **Backend:** FastAPI (Python 3.12), event-sourced graph service, litellm multi-provider routing.
- **Structural parsing:** tree-sitter grammars for Python / JavaScript / TypeScript / TSX.
- **Source of truth:** in-memory graph by default; PostgreSQL (via `psycopg`) when
  `CODEXA_DATABASE_URL` is set — idempotent schema bootstrap, no manual migration step.
- **Frontend:** Next.js 16 (App Router), TailwindCSS, Three.js (live 3D graph visualization),
  Zustand.

### Subsystems (`backend/`)

| Directory | Responsibility |
|---|---|
| `agents/` | Planning, execution, Quorum, browser tools, the LLM router, validators and verification. |
| `graph/` | The structural knowledge graph: schema, events, service, causal/consistency checks. |
| `memory/` | The four-type persistent memory store and context retrieval. |
| `perception/` | Ingestion and the trust boundary between verified assertions and untrusted external content. |
| `understanding/` | Static analysis and semantic modeling built on top of the parsed graph. |
| `repository/` | Cloning, analysis (tree-sitter), symbol annotation, docs generation. |
| `trust_safety/` | Risk scoring, policy, confidence, and explainability for agent-proposed actions. |
| `simulation/` | Impact/blast-radius simulation before a change reaches execution. |
| `execution/` | The sandbox execution contract for running proposed changes. |
| `learning/` | Longer-horizon policy refinement over agent behavior. |
| `chat/`, `files/`, `observability/` | Chat/job API, file I/O, usage and event telemetry. |

### Frontend tour (`graph-viz/app/(workspace)/`)

`chat` · `ide` · `graph` (the live 3D graph) · `strata` · `architecture` · `memory` ·
`time-machine` (replay the graph's state at any past point) · `agents` · `usage` · `repository` ·
`docs`

## Getting started

### Prerequisites
- Python 3.12+
- Node.js 20+
- PostgreSQL — optional; omit `CODEXA_DATABASE_URL` to run fully in-memory

### 1. Environment

Create a `.env` in the project root:

```env
# At least one provider key — pick whichever you have. See backend/agents/llm.py's
# _PROVIDER_ENV for the full list (NVIDIA NIM, Gemini, Groq, Upstage, Mistral, Cerebras, ...).
NVIDIA_API_KEY=...

# Optional — omit to run on the in-memory graph.
CODEXA_DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/codexa

# Optional — seeds an honest self-description of Codexa's own architecture into its graph
# on first boot, so the app has something real to show immediately.
CODEXA_SEED=1
```

### 2. Backend

```bash
python -m pip install -e .[dev]
python -m playwright install chromium   # once, for the browser tools
python -m uvicorn backend.main:app --port 8090
```

`--reload` is intentionally not used in normal operation: this platform runs long background
agent jobs, and the reloader tears the process down on every file save mid-job. Use a separate
`backend.main:app --reload` invocation only when iterating on backend code with no job running.

### 3. Frontend

```bash
cd graph-viz
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Benchmarks

`tests/benchmarks/memory_graph/` holds two independent proofs:

- **`retrieval_payload.py`** — the deterministic, model-free token-reduction proof above.
  `BENCHMARK_REPS` / `BENCHMARK_MODES` / `BENCHMARK_QUESTIONS` / `BENCHMARK_RUN_DIR` env vars
  control repetitions and scope; `aggregate.py` rolls repeated runs into a report with 95%
  confidence intervals.
- **`runner.py`** — an end-to-end agentic comparison (Raw file tools vs. Graph-only vs. Full
  Codexa) driving a real model through `JobManager`. Useful for qualitative behavior, but not
  the token-reduction instrument: on hard multi-hop questions every arm, on every model tested,
  was observed to occasionally thrash without converging, which measures model stability rather
  than the architecture.

## Core principles

- **No black boxes.** Every LLM-inferred fact in the graph cites its source and carries a
  confidence score.
- **State what's real.** The architecture the code claims is the architecture that ships — see
  the implementation table above; `backend/seed.py` seeds this same honesty into Codexa's own
  self-model.
- **Verify, don't self-report.** Agent claims are checked against the graph/filesystem, not taken
  on the model's word — see `backend/agents/verification.py`.
- **Grounded disagreement, not persuasion.** Quorum resolves multi-agent disagreement through
  graph-checked structured claims first, and only falls back to a tightly-scoped, non-free-text
  debate round when the graph genuinely can't settle it.

## License

Proprietary / Internal use only.
