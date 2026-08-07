# Codexa OS — Progress Summary & Semantic Memory Layer Proposal

*Draft for external research / second opinion. Written from the current state of the codebase as of this session.*

---

## 1. What Codexa OS is

An engineering-intelligence platform built around a live knowledge graph of a codebase, with a chat interface that gates any requested change behind a computed **blast radius** (what breaks downstream, and how risky) before an LLM is allowed to act on it. Backend: FastAPI + an event-sourced, temporal graph store. Frontend: Next.js 16 / React 19, a 3D force-directed graph view, chat, an in-app codebase viewer, repository scoring, architecture trends, and a time-machine replay of the graph's history.

## 2. Current state (verified working)

**Knowledge graph**
- Nodes: `Repository`, `File`, `CodeSymbol`, `HealthMetric`, plus platform self-model node types (`ArchitectureTrend`, `CausalEvent`, etc.).
- Edges: `IMPORTS`, `CALLS`, `DEPENDS_ON`, `FLOWS_INTO`, temporal (`valid_from`/`valid_to`) so a repo's structure can be replayed over time.
- Static analysis (`backend/repository/analyze.py`) does regex-based extraction of functions/classes/imports/an approximate call graph for JS/TS/Python. This is **structural only** — it knows *what exists and what calls what*, not *what anything means*.
- The graph is in-memory. Repo clones and their source URL persist to disk (`.codexa/repos/<name>/.codexa-repo.json`); on backend restart, `rehydrate_repositories()` (`backend/repository/api.py`) automatically rebuilds every previously-loaded repo's graph/score from disk without user action.

**Blast radius (`backend/agents/impact.py`, `POST /agents/impact`)**
- Resolves a free-text change description to graph nodes, then does a **reverse** BFS over dependency edges to find everything downstream (fixed from an earlier version that traversed forward and undercounted impact).
- Returns: affected count, risk level/score, confidence, propagation-chain previews, and (added this session) a breakdown by node type, distinct files touched, and counts of `CALLS`/`IMPORTS` edges crossed — so "23 downstream components" also reads as "11 files, 36 function calls."
- Chat detects change-intent language, runs this **before** any implementation plan, and requires explicit user approval (`ImpactCard`) before the agent proceeds.

**LLM layer (`backend/agents/llm.py`)**
- Multi-provider via litellm: NVIDIA NIM, Groq, Gemini, and Z.ai (GLM 5.2, verified 1M-token context window; GLM 4.5 Air for light tasks).
- Task-tier routing (`TASK_TIER`): architecture/reasoning/planning/coding route to the heavy tier, docs/summary to light, chat to balanced.
- A model is offered only if its provider key is present in `.env`.

**Tool-calling agent (`backend/agents/tools.py`, `POST /chat/agent`)**
- Real tools: `read_file`, `list_directory`, `search_code`, `write_file`, `run_python` (sandboxed subprocess, 10s), `web_search` (Tavily API — the earlier DuckDuckGo scraper was dead-blocked by an anti-bot challenge and was replaced this session).
- SSE streams `tool_call` / `tool_result` / `delta` events; frontend renders a collapsible tool-trace row per call.

**Memory (`backend/memory/store.py`)**
- Four types — semantic, episodic, procedural, organizational — persisted to `.codexa/memories.json`, survives restarts.
- On repo load: writes a grounded digest (package info, README excerpt, dependency-derived framework labels, directory tree, a "key functions & components" summary from the static-analysis pass).
- Injected into every chat turn as a system-message "answer strictly from these facts" block — this is the current (flat, un-ranked, top-12-records) grounding mechanism.
- Generated repository documentation is now persisted here too (`source: "docs_cache"`, this session's fix) instead of regenerating on every tab open or backend restart, and is excluded from the per-turn chat grounding block so it doesn't eat context budget on every message.

**Repository scoring (`backend/repository/scoring.py`)**
- Real metrics on ingestion: documentation, test coverage, modularity, maintainability, type safety, structure — each with a reasoning string and conditional suggestions, no hardcoded/mock output.

**Known, deliberate gaps**
- Static analysis is regex-based, not a real parser/AST — it can miss dynamic imports, complex destructuring, etc.
- The knowledge graph has no semantic layer: it can tell you *that* `useServices` is called by 14 things, not *what* `useServices` actually does.
- Grounding context for chat is a flat list of memory records, not scoped/ranked by relevance to the actual question, and caps at 12 records regardless of repo size.
- Blast radius is scoped to a single loaded repository; it doesn't propagate across repos that share a dependency.

---

## 3. The problem this proposal addresses

Every competitor in this space (Sourcegraph Cody, Cursor, GitHub Copilot, Windsurf) solves "does the model understand my whole codebase" the same way: retrieve-on-demand, either via embeddings/vector search or, in our case, on-demand tool calls (`read_file`, `search_code`) during the agent loop. Two problems fall out of that:

1. **Redundant work.** The model re-discovers the same facts about the codebase on every conversation, sometimes every turn, because nothing durable is written down about *what the code means* — only that it exists.
2. **Hallucination risk stays high.** Retrieval returns raw file contents or graph structure; the model still has to infer meaning live, under time/token pressure, with no persistent record of what it concluded last time or whether that conclusion is still true.

The user's framing: *"a secondary, permanent context made whenever an LLM fully explores the codebase, which other models can also access — not literally unlimited context, but something that avoids needing to re-search the whole codebase every time, with real anti-hallucination measures."*

That is achievable — not as literally-infinite context (no provider offers that; it's a hard token-limit constraint regardless of vendor), but as a **precomputed, persistent, structured semantic layer that sits in the graph itself**, shared across every model because it lives on the backend, not in any one conversation.

---

## 4. Proposed architecture: Graph + LLM-derived Semantic Layer

### 4.1 Core mechanism

Add a second analysis pass, after the existing regex-based `analyze_repo()`, that is **LLM-driven instead of pattern-driven**:

- For each `CodeSymbol` node (function/class/hook/component), one LLM call produces a structured annotation: purpose, inputs/outputs, side effects, invariants, and any notable coupling — stored as **properties on the graph node itself**, not as chat history.
- Because this lives in the graph/`MemoryStore` (backend-side, repository-scoped), it is automatically available to **every model and every conversation** — this is already how the platform's repo-memory injection works today, so no new cross-model plumbing is needed, only a richer thing to inject.

### 4.2 Why this beats "just use a bigger context window"

- Stuffing an entire repository into a 1M-token prompt is slow, expensive, and still forces the model to re-read everything on every turn — it doesn't solve re-discovery, it just makes each re-discovery cost more tokens.
- Pre-annotating once means a query **resolves to specific nodes** — the same resolution logic `impact.py` already uses (`_resolve_targets`) — and then expands outward to that node's neighborhood plus one summary level up. Bounded, cheap, targeted. Not "search the whole codebase" on every message.

### 4.3 Hierarchical rollups (solves "what level of detail does this question need")

A four-level summary hierarchy, each level generated by combining the level below it:

| Level | Scope | Example |
|---|---|---|
| 0 | Per-symbol | "`useServices` returns the DI context for storage/auth adapters; 14 callers" |
| 1 | Per-file | Combines its symbols' summaries |
| 2 | Per-directory/module | Combines file summaries |
| 3 | Whole-repo architecture | Combines module summaries |

A query about one function pulls level 0. A question like "how does auth work" pulls the relevant level-2 summary. Nobody needs the whole tree loaded for either.

### 4.4 Hallucination guardrails — the part that's actually novel

1. **Provenance + drift detection.** Store a content hash per symbol alongside its annotation. If the underlying file changes, the hash mismatches and that annotation is marked stale — excluded from grounding, or queued for re-verification — before it can be presented as current fact. This directly targets the class of hallucination where the model confidently describes code that no longer exists in that form.
2. **Cross-model consensus.** Four providers are already wired up (NVIDIA, Groq, Gemini, Z.ai). For high-stakes symbols — anything touching auth, payments, or already flagged by a blast-radius risk check — generate the annotation with two different providers and store disagreement as a lowered confidence score, instead of silently trusting whichever one ran first.
3. **Cite-or-refuse enforcement.** Not just prompted ("answer strictly from facts," which is what exists today) but **checked**: every factual claim in a response should trace to a specific node ID with a currently-valid content hash. If it can't, the response is forced to hedge or say "not covered by verified codebase facts" rather than answer confidently. This is a mechanical check, not a request the model can silently ignore.

### 4.5 Honest cost tradeoff

Annotating every symbol via LLM is not free — a real repository is hundreds of symbols. Mitigations:
- Use the light/cheap model tier for the bulk first pass; escalate to the heavy tier only for cross-checking flagged/high-risk symbols (ties directly into the existing `TASK_TIER` routing).
- Only re-annotate what changed — the content-hash diff means a reload only touches symbols whose source actually moved, not the whole repo.
- This can run as a background job after ingestion rather than blocking the initial `/repository/load` response.

### 4.6 Competitive/patent framing

Pure graph-based impact/blast-radius analysis has prior art (e.g. [US Patent 9201649](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9201649), and standalone tools like [blast-radius.dev](https://blast-radius.dev/)). The novelty claim here is **not** "we compute impact via graph traversal" — it's the specific combination of:

> structural graph **+** LLM-derived semantic annotation per node **+** content-hash-based staleness invalidation **+** multi-model consensus scoring for high-risk facts **+** all of it shared cross-provider from a single backend-resident store.

That combination is not what Cody, Cursor, or Copilot do today (per the market research done this session, all of them re-retrieve per query rather than maintain a persistent, verified, structured semantic cache).

---

## 5. Related feature ideas already scoped this session (for context, not all urgent)

Ranked by how much they'd matter for market competitiveness, from a prior research pass this session:

1. **Cross-repo blast radius** — propagate impact across repos that share a dependency, not just within one loaded repo. Nothing in the competitive set does this well.
2. **Hybrid graph+LLM risk consensus** — same consensus mechanism as §4.4, applied specifically to blast-radius risk grading, not just semantic annotation.
3. **Self-healing live graph** — a file-watcher that incrementally patches the graph on save instead of requiring a full re-ingest (directly related to the staleness/hash mechanism above — it's the same primitive doing two jobs).
4. **CI/PR gate + IDE extension** — expose blast radius as a GitHub Action / VS Code extension, not just inside the Codexa chat UI. Named explicitly as a top enterprise buying criterion in the research.
5. **Ownership-aware risk routing** — git-blame-derived code ownership; auto-flag when a change's blast radius crosses into someone else's code.
6. Lower-priority: compliance audit-trail export, blast-radius-scoped test generation, causal incident replay from the existing event log, proactive architecture-debt alerts (the platform already computes a "projected bottleneck: N days" figure but doesn't act on it).

---

## 6. Open questions for second opinion / further research

1. **Annotation trigger**: run the semantic pass synchronously during `/repository/load`, or as an async background job (better UX, more moving parts)?
2. **Storage shape**: symbol-level annotations as graph-node properties (queryable via existing graph API) vs. as `MemoryStore` records (consistent with how docs/facts are already stored, but less structurally queryable). Possibly both — property for fast lookup, memory record for the injected-context format.
3. **Consensus policy**: which symbols are "high-stakes" enough to warrant a second model call? Keyword heuristics (auth/payment/secret) vs. blast-radius-risk-driven (only re-check symbols already flagged Medium+ by impact analysis)?
4. **Staleness re-verification**: lazy (re-annotate the first time a stale symbol is touched by a query) vs. eager (batch re-annotate on every reload)? Lazy is cheaper but means the very first post-change answer about that symbol could still be stale.
5. **Cost ceiling**: is there a per-repo annotation budget (e.g., skip symbols below some size/complexity threshold, or cap total LLM calls per ingestion) needed to keep this practical on large repositories?
6. **Legitimate risk to flag**: this whole design still cannot exceed a provider's real context/rate limits — worth confirming the hierarchical-rollup approach is actually sufficient, versus needing a proper vector index as a fallback for pure "find similar code" queries that don't cleanly resolve to graph nodes.

---

*This document reflects the state of `backend/` and `graph-viz/` as built and verified in this working session. File references are accurate as of this draft; nothing in §4 is implemented yet — it is a proposal pending direction.*
