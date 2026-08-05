# Codexa OS — Engineering Brain Build Prompt (v5 Synthesis)

> **Purpose of this document:** This is an execution prompt, not a pitch deck. It synthesizes the accepted v4 Master Design Document with three independent architectural reviews. It tells the building agent (human or AI) exactly what to implement, in what order, and — just as importantly — what *not* to build in this phase.

---

## 0. Role Definition

You are the lead systems architect and implementation agent for **Codexa OS**, an Engineering Intelligence Platform. The product is the **Engineering Knowledge Graph and the reasoning/verification/learning systems built around it** — not a chat UI wrapped around an LLM. Every subsystem you build should read from and write to the graph.

Treat this document as the authoritative spec for this build phase. Where it conflicts with the original v4 document, this document wins — it is a strict superset with corrections.

---

## 1. Scope Boundary

**In scope (this phase):** everything backend — perception/ingestion pipelines, the knowledge graph engine and schema, memory systems, the multi-agent reasoning layer, the trust & safety / verification pipeline, the simulation engine, and all the new subsystems in Section 5.

**Out of scope (this phase):** general application frontend — auth screens, dashboards, settings pages, marketing site, Next.js page shell/routing, component libraries.

**Explicit exception — the one frontend piece you *do* build:** the **Interactive Knowledge Graph Visualization** (Section 7). It is a flagship deliverable, not a chart. Treat it with the same seriousness as the graph engine it renders.

If a task doesn't clearly serve one of these, don't build it yet — flag it for the roadmap instead.

---

## 2. Stack Confirmation (do not deviate without a written tradeoff)

- **Backend:** FastAPI
- **Storage:** PostgreSQL (JSONB) as source of truth; Neo4j as graph projection; Qdrant as vector projection; Redis + RQ for queues/scheduling
- **Parsing:** Tree-sitter
- **Execution/Sandbox:** Docker
- **Protocol:** MCP
- **Models:** Qwen3 14B, Qwen2.5 Coder, via Ollama

MongoDB and Express.js were evaluated and rejected in the prior review cycle. Nothing in this document reintroduces them, including the data-flow tracing feature below, which is written against Postgres/FastAPI.

---

## 3. Updated Cognitive Architecture

```
Perception
   ↓
Trust Boundary & Content Isolation   ← NEW
   ↓
Understanding
   ↓
Engineering Knowledge Graph (v2 schema)
   ↓
Memory
   ↓
Planning
   ↓
Engineering Simulation Engine        ← NEW
   ↓
Execution
   ↓
Verification
   ↓
Reflection
   ↓
Continuous Learning → Policy Distillation   ← NEW closes the loop
```

The Simulation Engine sits between Planning and Execution: nothing gets executed against the real repo without first being run against the simulated one.

---

## 4. Engineering Knowledge Graph v2

### 4.1 New/expanded node types
`ArchitectureTrend`, `SimulationScenario`, `CausalEvent`, `Decision`, `Tradeoff`, `RejectedAlternative`, `OnboardingPath`, `HealthMetric`, `PreventionRule`, `ConventionProfile`

### 4.2 New/expanded edge types
`causes`, `mitigates`, `increases_risk_of`, `correlates_with`, `derived_from`, `supersedes`, `flows_into` (data-flow tracing), `traces_to_decision`

### 4.3 Every edge now carries
- `confidence: float [0,1]`
- `source_type: enum(static_analysis | llm_inferred | human_asserted)`
- `valid_from`, `valid_to` — temporal versioning (this is what makes the Time Machine possible)

Static-analysis-derived edges (`calls`, `imports`, `depends_on`) get `confidence = 1.0`, `source_type = static_analysis`. LLM-inferred edges (`introduced_by`, `fixed_by`, causal edges) must carry a real confidence score and a citation back to the source artifact — never asserted as fact without one. This is what makes Section 7 (Explainability) in the original doc actually mean something instead of a floating "confidence: 92%."

### 4.4 Full-stack data-flow tracing (adapted to your stack)
Introduce `flows_into` edges that trace a Postgres/JSONB schema field through the FastAPI route(s) that serve it to every downstream consumer. A migration or field change should let the Planner instantly compute cross-boundary blast radius — this generalizes the "trace a schema field to its consumers" idea without assuming a specific frontend framework, since frontend build-out isn't in scope here.

---

## 5. New Subsystems

### 5.1 Trust Boundary & Content Isolation Layer
Every ingested artifact (issue body, PR description, comment, scraped doc) gets tagged with a trust level: `repo_owner`, `verified_contributor`, `external_untrusted`, `public_scraped`. Text from `external_untrusted`/`public_scraped` sources is treated as data, never as instructions — it cannot directly trigger a tool call. Anything instruction-shaped found inside these fields gets flagged and stripped before it reaches agent context. This closes the indirect-prompt-injection surface created by agents with filesystem/git/terminal/cloud access reading attacker-controllable text.

### 5.2 Engineering Simulation Engine (Digital Twin)
Takes a proposed diff + current graph state as input. Simulates, before anything touches the real repo:
- dependency/service failure propagation
- schema change impact
- deployment sequencing
- rollback path viability

Output: predicted blast radius, predicted test failures, predicted performance delta, confidence — all written to the graph so Explainability can show *why* a plan was approved or blocked.

### 5.3 Architecture Evolution Engine
Tracks coupling, cohesion, cyclomatic complexity, dependency fan-in/out, ownership fragmentation, and file churn over rolling time windows. Forecasts trends (simple statistical regression is enough here — don't over-engineer with heavy ML for an academic-scope build) and raises alerts like "this module's coupling has grown 40% over 3 months; on current trend it becomes your largest bottleneck in ~5 weeks." Writes `ArchitectureTrend` nodes.

### 5.4 Causal Engineering Graph
Chains `CausalEvent` nodes: commit → PR → deployment → incident → telemetry signal → (optionally) customer-facing impact, each edge carrying a causal-confidence weight. Lets the system answer "what did this bug actually cause" instead of only "what does this code call."

### 5.5 Organizational Intelligence
Mines PR review comments and merge patterns per team/author into `ConventionProfile` nodes (e.g., "this team rejects PRs over 400 lines," "backend team avoids inheritance"). Retrieved as context by the Reviewer and Architect agents so recommendations match team culture, not just correctness.

### 5.6 Intent Graph
Extracts `Decision → Tradeoff → RejectedAlternative` chains from ADRs, PR discussions, and issue threads via LLM extraction — every extraction cited back to its source artifact with a confidence score. Lets the system answer "why didn't we use Kafka here" with an actual citation instead of a guess.

### 5.7 Engineering Time Machine (backend)
A query/replay API over the temporal edges in 4.3: reconstruct the graph as it existed at time T, or replay an entity's full history. This is pure backend — the replay *visualization* lives in Section 7.

### 5.8 Engineering DNA
Infers per-repo conventions (naming, error handling, test style, folder organization) from static analysis + LLM reading, stored in Organizational Memory with confidence scores, and used to steer the Coder agent's generation style so output matches the repo instead of generic idioms.

### 5.9 Evidence-Based Confidence Calibration
Replace the placeholder "confidence: X%" with a real weighted formula:
```
confidence = f(evidence_coverage, repo_familiarity, test_coverage_overlap,
                historical_similarity, verification_pass_rate, dependency_certainty)
```
The breakdown, not just the number, gets returned in the explainability trace.

### 5.10 Engineering Economics
Estimates implementation effort, maintenance cost, and future technical debt from historical PR size / review time / test-delta regression features. Attaches tradeoff statements to Planner output, e.g. "this shortcut saves ~2 hours now, ~12 hours of projected future maintenance."

### 5.11 Autonomous Nightly Architecture Review
Scheduled RQ job: run smell detection + knowledge-gap detection, prioritize by impact, generate a draft RFC in markdown, optionally open a draft PR — always gated by the existing human-approval policy in the Trust & Safety pipeline. This doesn't bypass Section 6 of the original doc; it feeds into it.

### 5.12 Incident Learning
Structured chain: `Incident → RootCause → Fix → RegressionTest → PreventionRule`. Prevention rules become permanent policy checks feeding the Risk Score model — the platform should never make the same mistake twice without at least raising a flag.

### 5.13 Engineering Research Agent
Refines the existing "Research" agent role: scoped external search (GitHub, RFCs, framework docs, release notes) summarized into repo-relevant recommendations attached to Planner context. Every output must cite its source.

### 5.14 Repository Health Score
Composite score from maintainability, testability, coupling, doc coverage, architecture stability, deployment safety (DORA: deployment frequency, lead time, change failure rate, MTTR), ownership clarity, tech-debt index, and confidence. Continuously updated, surfaced as a node the graph visualization can render prominently.

### 5.15 Pre-Mortem / Chaos Testing
Extends the sandbox hardening already in the plan: for changes above a risk-score threshold, the QA/Security agents run fault injection (dependency down, DB connection drop, CPU spike, network partition) in an ephemeral Docker sandbox before merge, logging results to Episodic Memory.

### 5.16 Retrieval & Context Assembly Policy
Hybrid retrieval: bounded-hop Neo4j graph traversal for structural relevance + Qdrant vector search for semantic relevance, under an explicit per-agent token budget. When the relevant subgraph exceeds budget, fall back to graph summarization rather than silently truncating.

### 5.17 Multi-Store Consistency
Postgres is the source of truth via an event log / outbox pattern. Neo4j and Qdrant are read-optimized projections rebuilt from that event stream (RQ workers). A reconciliation job periodically detects and heals drift between the three stores.

### 5.18 Continuous Learning → Policy Distillation
Close the loop the original doc left open. A periodic job converts accepted/reverted changes, review comments, and incident outcomes into: (a) updated per-repo prompt/context templates in Organizational Memory, (b) adjusted risk-calibration weights, (c) retrieval re-ranking weights. All versioned so a bad update can be rolled back.

---

## 6. Explicitly Deferred (not this phase)

- **Cloud State & Security Posture nodes** (AWS Inspector / GuardDuty / Macie integration) — assumes a committed live cloud deployment target you haven't specified. Belongs in the existing Version 2 bucket alongside production telemetry.
- **Figma-to-code drift detection** — design-tooling/frontend-adjacent; out of scope given the frontend exclusion in Section 1.
- **Full bidirectional design↔code sync** — same reason.

Don't build stubs for these yet. Note them in the roadmap and move on.

---

## 7. The Graph Visualization — Spotlight Feature

This is the one frontend deliverable in this phase, and it should look like the flagship demo of the whole platform, not a debugging tool.

**Rendering:** Force-directed layout (2.5D/WebGL — Three.js, react-force-graph, or d3-force + custom shaders). Dark theme, consistent with the rest of the platform's aesthetic.

**Required behaviors:**
- **Live agent traversal:** when an agent (Planner, Coder, Reviewer, etc.) is actively reasoning, the nodes and edges it touches light up and pulse along the traversal path in real time — the user should be able to *watch the system think*.
- **Confidence-mapped edges:** edge thickness and opacity map to the `confidence` attribute from Section 4.3 — low-confidence LLM-inferred relationships should visually read as tentative next to solid static-analysis edges.
- **Causal propagation particles:** for `causes`/`increases_risk_of` chains, animate particles flowing along the edge to show cause-effect propagation (e.g., commit → deployment → incident).
- **Time-scrubber:** a draggable timeline that replays the graph's evolution using the Time Machine API (Section 5.7) — watch architecture drift, ownership change, and technical debt accumulate over real history.
- **Cluster drift visualization:** modules flagged by the Architecture Evolution Engine (5.3) visually swell/destabilize/cluster-shift as their trend worsens, rather than just showing a static warning badge.
- **Interactive inspection:** click a node → explainability trace panel (evidence, confidence breakdown, graph path). Right-click → "why does this exist" reveals the linked Intent Graph (Decision/Tradeoff/RejectedAlternative) chain.
- **Cinematic camera:** smooth eased transitions when focusing/zooming into a subgraph, not instant jumps.

This component consumes the Time Machine, Confidence Calibration, Causal Graph, and Architecture Evolution Engine APIs directly — build those backend pieces first, since the visualization is only as good as the data feeding it.

---

## 8. Updated Sprint Mapping

| Sprint | Original Scope | Additions from this document |
|---|---|---|
| 0 | Architecture, docs, infra | — |
| 1 | Repository Intelligence | **Trust Boundary & Content Isolation (5.1)** |
| 2 | Live Knowledge Graph | KG v2 schema (Section 4), data-flow tracing (4.4) |
| 3 | Memory + Explainability | **Intent Graph (5.6), Organizational Intelligence (5.5), Engineering DNA (5.8)** |
| 4 | Planner + Blast Radius | — |
| 5 | Coder + Verification | — |
| 6 | Policy Engine + Adversarial Review | **Engineering Simulation Engine (5.2)** |
| 7 | Sandbox + Git + Execution | **Chaos/Pre-mortem testing (5.15)** |
| 8 | Interactive Knowledge Graph | **Graph Visualization Spotlight (Section 7)** — elevated to flagship deliverable; **Architecture Evolution Engine (5.3)** |
| 9 | Risk Calibration | **Causal Graph (5.4), Confidence Calibration (5.9), Engineering Economics (5.10), Health Score (5.14), Incident Learning (5.12), Research Agent (5.13), Nightly Review (5.11)** |
| — | Multi-store consistency (5.17), retrieval policy (5.16), policy distillation (5.18) | Cross-cutting — implement incrementally starting Sprint 1, not a single sprint |
| V2 | Production telemetry, cross-repo learning | **Cloud State & Security Posture nodes (deferred, Section 6)** |
| V3 | Org-wide, multi-project reasoning | Figma/design-sync (deferred, Section 6) |

---

## 9. Deliverable Expectations

For this phase, produce:
1. Updated KG schema definitions (Postgres tables + Neo4j constraints/indexes)
2. Module interfaces/stubs for every subsystem in Section 5, each wired to read/write the graph
3. The graph visualization component (Section 7), built against real Time Machine / Confidence / Causal Graph APIs — not mock data
4. No general application frontend (auth, dashboards, settings, page shell) in this phase

If a request during implementation doesn't map cleanly to something in this document, stop and flag it rather than improvising scope.
