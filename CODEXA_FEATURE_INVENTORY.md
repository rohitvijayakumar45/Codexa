# Codexa OS — Feature & Specification Inventory

*Compiled 2026-09-05 for patent-worthiness / novelty research. Every claim below is grounded in actual code (file:line citations in the source sections), not marketing copy — sections 8-9 and 14 specifically flag which subsystems are real algorithms vs. current scaffolding, since that distinction matters for a prior-art search.*

## 0. What it is
"Codexa OS" — a FastAPI backend + Next.js frontend engineering-intelligence platform. Core idea: a temporal knowledge graph of a codebase (files, symbols, imports, calls, health, decisions) plus a chat agent that can read/write that codebase through tools, grounded in a 4-type memory store and a live-updating graph.

## 1. Agent job execution architecture (built/verified this session — backend/agents/jobs.py)
- The chat agent's tool-calling loop used to run inline inside the HTTP request's StreamingResponse. Now it runs as a **detached background thread**, keyed by a job id, fully decoupled from any one HTTP connection.
- **Checkpoint-and-resume**: after every round (and after every tool call within a round), full job state (message history, round number, tool-call history, working repo) is serialized to disk (`backend/data/jobs/<id>.json`).
- **Crash recovery**: if the backend process restarts mid-task, the next client reconnect (`GET /chat/agent/stream/{job_id}`) detects the job isn't in the live in-memory registry, loads the checkpoint, and **resumes the tool-calling loop from the next incomplete round** — not from scratch. Verified: simulated a crash after 1 of 3 file writes; resume continued with writes 2 and 3, did not redo write 1.
- **Client-disconnect independence**: a browser tab switch/close doesn't cancel the backend job (only the local SSE subscription is aborted). The frontend tracks a `pendingJobId` per conversation (persisted client-side) and replays the full event log from a fresh subscription when the user returns — verified across "job still running" and "job already finished while away" cases.
- **Explicit cancellation**: a separate cooperative-cancellation path (`POST /chat/agent/job/{id}/cancel`) — checked between streamed chunks and between rounds — so a user-initiated Stop still actually halts billing, distinct from the "just walked away" case which intentionally lets the job keep running.
- **Rate-limit-aware model fallback mid-task**: if a provider rate-limits mid-round (before any tokens streamed), the loop transparently switches to the next model in the same capability tier and continues the SAME task/conversation, emitting a `model_switched` event the UI surfaces.
- **Stall recovery**: a provider that goes silent mid-generation (observed on some models during large single-shot file writes) gets a bounded number of "continue where you left off" recoveries with an injected system note, rather than failing the whole turn.

## 2. Tool orchestration (backend/agents/tools.py, task.py)
- ~50+ tools exposed to the LLM (file I/O, code search, symbol lookup, git, test/lint/build, browser/visual QA, design-system guidance, web search, code execution).
- **Dynamic tool grouping**: instead of exposing all tools on every turn, the user's message is classified into groups (repo/code/runtime/browser/design/git/external/orchestration) via signal regexes, and only the relevant tool schemas are sent — reduces prompt overhead and (this session) was found to have a related frontend-side bug (a `needsTools()` heuristic was routing genuine investigative questions to a zero-tools endpoint before the backend classifier ever ran) — fixed and verified.
- **Task-contract system** (task.py): classifies user intent (CREATE/MODIFY/DELETE/RUN/ANALYZE/SEARCH/EXPLAIN/CONVERSATION), generates a contract of required tools + success criteria + suggested workflow, injects it into the system prompt, and **validates post-hoc** that the required tool was actually called before accepting the model's final answer — if not, injects a correction and forces another round. This directly targets "model describes a fix instead of making it" failure mode.
- **Context compaction mid-task**: bulky tool payloads (design-guidance dumps, full file contents in write/edit calls) are collapsed in the conversation history a few rounds after they were used, since the file itself (not the transcript) is the source of truth — keeps a long multi-file scaffolding task from re-paying full token cost for old payloads every round.
- **Delegation**: a `delegate_task` tool lets the primary (heavy) model hand a mechanical, fully-specified multi-step plan to a cheap/fast "light" tier model, which executes with a restricted tool subset (no judgment calls, no recursive delegation) — the calling model's context grows by one call + one summary instead of every intermediate round.
- **Prompt caching**: system message + tool schemas are annotated with `cache_control: ephemeral` for providers that support prefix caching.

## 3. LLM routing layer (backend/agents/llm.py)
- Multi-provider (NVIDIA NIM, Groq, Google Gemini, z.ai/GLM, OpenRouter, TokenRouter) behind one client, via litellm.
- Models registered with **real documented context windows** and a capability tier (heavy/balanced/light); routing is keyed by task type (architecture/graph/reasoning/coder → heavy; docs/summary/retrieval → light; chat → balanced) so cost isn't uniformly paid at the most expensive tier.
- A model is only offered if its provider API key is configured (self-describing availability).
- Per-model **sliding-window rate limiter** (token bucket) for providers with hard RPM caps — sleeps to stay under the limit instead of eating a 429.
- Real per-request token accounting including a **reasoning-token breakout** (so a model's internal "thinking" tokens don't masquerade as a mysteriously long visible response).

## 4. Memory system (backend/memory/)
- 4 memory types: semantic, episodic, procedural, organizational — all genuinely populated on every repository load (not demo-only), each with real write sites (project digest, load-event record, build/run instructions, stack/conventions/health).
- **Type-aware retrieval weighting** (built this session, memory/context.py): query phrasing ("how do I run this" vs "what tech stack" vs "when was this loaded") biases ranking toward the memory type most likely to answer it, on top of keyword-overlap scoring — previously all 4 types were ranked in one undifferentiated pool.
- **Graph-anchored context retrieval**: resolves a chat question to specific graph nodes (symbols/files) by name/path matching, pulls each match's LLM-derived semantic annotation plus immediate call/import neighbors, and only falls back to generic repo-digest facts when nothing resolves — a targeted-neighborhood retrieval instead of flat top-k memory dump.

## 5. Knowledge graph + auto-reindex (built/verified this session — backend/repository/api.py, backend/graph/)
- Full-repo static analysis on load (files, symbols, imports, call edges) plus **git-mined change-coupling edges** — files with no import/call relationship that historically break together (CodeScene-style hidden coupling), added symmetrically so blast-radius analysis catches it too.
- Previously: the graph was built once at load time and never touched again — any agent-driven file edit silently went stale (lookup_symbol/find_references kept returning pre-edit results indefinitely).
- Fixed this session: the graph is now reindexed once per agent turn (not per tool call) whenever the turn touched files, via a clear-then-full-rebuild of that repository's graph nodes/edges (avoids the alternative bug of deleted files/symbols lingering as zombie nodes forever). Verified: wrote a new function via chat, `lookup_symbol` found it immediately with correct file/line, no manual reload.
- Temporal edges (valid_from/valid_to) support point-in-time graph snapshots — a "Time Machine" view.

## 6. Blast-radius / planning agents (backend/agents/planner.py, coder.py, research.py — made real this session)
- **Planner**: BFS blast-radius traversal over the graph (confidence-weighted, depth-bounded) for "what breaks if I change X" — pure graph algorithm, no LLM. Separately, a real LLM-backed `plan()` endpoint turns a plain-language goal into a concrete ordered implementation plan.
- **Coder**: reads the named files' real current content, asks the LLM to produce a structured diff + rationale (JSON-mode prompt with a regex/parse fallback so a non-conforming model response never crashes the request), persists it as a graph-attributed event.
- **Research**: runs a live web search (Tavily) when configured, asks the LLM to synthesize a recommendation with real citations (falls back to an explicit "no web search configured, reasoning from own knowledge" citation otherwise), persists recommendation + citation nodes with DERIVED_FROM edges.
- All three previously existed as API-only "record a result someone else computed" stubs with zero LLM calls and zero frontend callers; now wired end-to-end with a live UI panel in the Agent Network dashboard.

## 7. Change-impact ("blast radius") analysis (backend/agents/impact.py)
- Real algorithm, most substantial non-LLM piece in the system. Fuzzy-matches a free-text change description against graph node names/paths/stable-ID tokens (word-boundary regex), then runs a **reverse-BFS over dependency edges** (imports/depends_on/calls/flows_into/correlates_with) with `min()`-propagated confidence along each path and depth-capped traversal, reconstructing representative dependency chains via a parent map. Risk level/score is a hand-tuned bucket function over affected-count × confidence.
- Called from the chat UI *before* any code-change request executes — the user sees "N downstream components affected, risk level X" and must approve before the agent proceeds.

## 8. "Digital Twin" simulation, chaos premortem, sandbox execution (backend/simulation/, backend/execution/) — heuristic, not ML
- **Simulation** ("Digital Twin"): runs the real blast-radius traversal, then applies regex pattern matching against the diff text (schema-change / destructive-schema patterns) and hardcoded linear formulas for confidence/performance-delta. Not a real execution simulation.
- **Content-binding integrity check** (the one genuinely distinctive mechanism here): the diff text is SHA-256 hashed and stored on the simulation record; the sandbox execution stage re-hashes the diff at run time and refuses to execute if it doesn't match the hash captured at simulation time — a cryptographic guarantee that "what was simulated" and "what is about to run" are byte-identical.
- **Chaos premortem**: gated on a risk-score threshold; returns a static hardcoded list of 4 canned fault-injection scenarios (dependency-down, DB-drop, CPU-spike, network-partition) — no actual fault injection or measurement.
- **Sandbox** itself never actually invokes Docker in the current code — it constructs the `docker run --rm --network none --read-only` argument list and gates on simulation-passed + hash-match, returning SCHEDULED/BLOCKED.

## 9. Trust & safety layer (backend/trust_safety/) — deterministic scoring + immutable audit trail
- Six services (confidence calibration, cost-of-change economics, repository health, incident learning, execution-gate policy, verification) — each a deterministic formula or rule-set over graph data, not ML. Individually simple (weighted linear sums, mean aggregation, boolean gates, regex checks).
- The **distinctive pattern is architectural, not algorithmic**: every trust/safety decision (confidence score, policy gate verdict, incident causal chain) is written as an immutable, timestamped graph node/event — producing a queryable, auditable decision trail across the whole pipeline (why was this change blocked/approved, on what basis, derived from what prior incident).
- Incident learning specifically writes a fixed causal chain — incident → root_cause → fix → regression_test → prevention_rule — as connected graph nodes with CAUSES/MITIGATES edges, directly linking a past failure to a standing prevention rule.

## 10. Prompt-injection isolation at the trust boundary (backend/perception/trust_boundary.py)
- Real (regex-based) content sanitization applied specifically to content tagged EXTERNAL_UNTRUSTED/PUBLIC_SCRAPED: line-by-line scanning against 4 categorized instruction patterns (prompt override, tool invocation, secret exfiltration, destructive instruction), with matching lines stripped and replaced with a marker, findings logged. A structural prompt-injection defense gate sitting between "artifact ingested from outside" and "content reaches the LLM."

## 11. Architecture trend projection (backend/understanding/architecture_evolution.py)
- Real time-series analysis: sorts metric observations by timestamp, computes slope-per-day, and linearly extrapolates a **bottleneck ETA** — the projected number of days until a coupling/complexity metric crosses a defined threshold. A genuine (if simple) predictive mechanism, distinct from the mostly-descriptive scoring elsewhere in the system.

## 12. Multi-store consistency reconciliation (backend/graph/consistency.py)
- Computes drift between the Postgres source-of-truth and its downstream projections (count-based), and emits concrete `replay_outbox_to_{store}` repair actions — a real, minimal event-sourcing reconciliation check for a system that treats Postgres as source of truth and other stores (Neo4j/Qdrant per the docs) as projections.

## 13. Hybrid documentation generation (backend/docs_gen/)
- Deterministic path introspects the *live* FastAPI route table and Pydantic schemas via `inspect` to generate always-accurate endpoint/schema docs; an optional LLM pass rewrites only the prose overview on top, with safe fallback to the deterministic version if the LLM call fails. Real reflection-based accuracy + optional LLM polish, not a static template.

## 14. What's NOT real (important for a patent/differentiation pass to exclude)
Several subsystems present a plausible-sounding name but are currently thin: nightly architecture review (string-templated, no LLM despite the name), policy distillation (hardcoded if/elif string selection), causal-graph/data-flow/org-intelligence services (graph-write plumbing over caller-asserted facts, no independent inference), chaos premortem (static canned scenario list). Worth knowing which parts are real engineering vs. scaffolding before spending research effort on them.

## 15. Frontend — pages & UI mechanisms (graph-viz/, Next.js)

10 routes under `app/(workspace)/`:

- **Chat** (largest page): multi-conversation sidebar, model picker, file attachments, live tool-call transcripts, "thinking" trace panel, blast-radius approval card before any change executes. SSE token streaming; a running agent job can be reattached across page reloads/tab switches via a persisted job id (built this session).
- **Codebase (IDE)**: file-tree + tabbed syntax-highlighted viewer, client-side file export. Read-only against the repo.
- **Knowledge graph**: real 3D force-graph (`@react-three/fiber`/three.js) — glow-sprite nodes, bezier edges, animated particle "flow" trails along active edges, idle random-node breathing pulses, a time-scrubber that filters edges by validity window to replay graph state at any point in history.
- **Agent network**: hand-laid-out SVG DAG across 7 pipeline layers (Perception→Learning) with animated dependency edges and pulsing "active" halos, polled every 4s. The only page (besides Chat/Docs) with real backend-triggering actions — a detail-drawer "Run it now" form for Planner/Coder/Research (built this session).
- **Usage**: token/cost dashboard — daily bar chart with a stacked reasoning-vs-visible-completion split, per-agent/per-model breakdowns.
- **Architecture**: auto-layout SVG diagram (modules placed into source/middle/sink columns by in/out-degree), animated flow edges, per-module trend lines, projected-bottleneck ETA callout (surfaces the linear-extrapolation mechanism from §11).
- **Repository score**: animated circular health gauge, per-metric bars, generated prose analysis with ranked suggestions.
- **Memory**: 4-column live view of the semantic/episodic/procedural/organizational memory store.
- **Time machine**: history replay — area-chart of edge-count-over-time with a synced scrub slider, clickable snapshot chips, live event ledger.
- **Documentation**: dual-mode — live-introspected API reference for the platform's own repo, LLM-generated markdown docs for any loaded repo; both have a real "Regenerate" action.

**Client-side state**: two Zustand stores with localStorage persistence — one for all chat conversations/turns/token totals/in-flight job id (enabling the crash-and-reattach architecture in §1 to work from the browser side too), one for the single active-repository selection shared app-wide.

**Design system**: a shared `PageHeader`/loading/error/empty-state component set plus centralized framer-motion easing constants, reused consistently across all 10 pages rather than a formal component library.

**Real-time patterns**: true SSE streaming is Chat-only; Agents (4s) and Usage (15s) poll on an interval; every other page fetches once per navigation.

---

## Suggested angles for the patent-worthiness research pass
Ranked by how much this session's own investigation suggests is genuinely novel vs. well-known technique combined competently:

1. **The job checkpoint/resume/reattach architecture** (§1) — decoupling an LLM agent's multi-round tool-calling loop from both the HTTP connection AND the client session, with disk checkpointing after every round/tool-call and transparent mid-task provider-fallback, is the most distinctive engineering in the system. Worth checking prior art specifically for "agentic LLM task durability across process crash" and "SSE job reattachment with full event-log replay."
2. **Task-contract post-hoc tool-call validation** (§2) — classifying intent → generating a machine-checkable contract → validating the model's tool calls against it before accepting a final answer, with automatic correction-and-retry, is a specific mechanism worth a prior-art check against "agent output verification" / "tool-use grounding" patents.
3. **Graph-anchored, type-weighted memory retrieval combined with live auto-reindexing** (§4, §5) — the combination (not each piece alone) of a temporal code graph, 4-typed memory with phrasing-driven type weighting, and turn-scoped reindex-on-edit is a fairly specific integration.
4. **Simulation/sandbox hash-binding** (§8) — cryptographically binding a "simulated" change to the exact bytes later executed is a small but concrete, checkable mechanism.
5. Most of the trust_safety/simulation/learning layer (§8-9, §14) is deterministic scoring/gating over a graph, not inference — likely too generic (weighted sums, boolean gates) to be independently patent-relevant on its own, though the "every decision is an immutable graph-attributed event" audit-trail pattern across the whole pipeline might be worth a systems-level claim rather than a per-formula one.
