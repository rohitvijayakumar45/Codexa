# Codexa OS — Final Plan (synthesizing two independent research passes)

*Supersedes the open questions in `semantic_memory_layer_proposal.md`. This is the decision document, not another options list.*

---

## 0. Verdict on the two source reports

Two independent "second opinion" research reports were commissioned on the semantic-memory-layer proposal. Both converge on the same diagnosis (every competitor does index→retrieve→generate; nobody keeps a persistent, verified, forward-looking model), but they differ sharply in rigor:

- **Report B** ("A Decade-Ahead Design & Roadmap Report") is the more trustworthy of the two: it names real figures with sourcing (Cursor ~$3B ARR by May 2026, Augment 51.8% on SWE-bench Pro vs Cursor's 50.21%, CodeScene's peer-reviewed 30,737-file study, Moderne's deterministic LST at 38,000 call sites/zero regressions), and — critically — it includes an explicit **Caveats** section admitting which numbers are vendor-sourced and unverified. It also directly answers every open question left in the prior proposal doc (annotation trigger → async with cost ceiling; storage → graph-node properties + MemoryStore for cross-cutting facts; consensus policy → cascade routing on disagreement; staleness → lazy re-verify + eager batch for high-risk nodes; vector fallback → yes, as a fallback only).
- **Report A** ("The Operating System for Autonomous Software Engineering") is higher-glamour but lower-rigor: Counterfactual Execution Graphing (spin up a sandbox, have an adversarial LLM generate failing inputs, execute them, feed runtime traces back into the graph) and Spectral Semantic Uncertainty Routing (sample N solutions, execute them, build a behavioral-agreement matrix, eigen-decompose it to detect "mixed state" uncertainty) are both real, citable research directions — but both assume infrastructure this project doesn't have: a sandboxed execution cluster, GPU budget for repeated parallel sampling, and engineering time closer to a funded research team's than a solo/small-team app. They belong in the vision section of a pitch deck, not the next quarter's roadmap.

**Decision: adopt Report B's grounded roadmap as the backbone. Keep Report A's ideas (CEG, SSUR, BOAD-style future-simulation swarms, the "Repository Immune System") as named, patent-worthy long-range vision — explicitly deferred, not built yet.**

## 1. Category positioning (decided)

Stop describing Codexa as "an AI coding assistant with blast radius." Adopt Report B's framing:

> **Codexa is an Engineering Digital Twin / Repository Operating System** — it maintains a live, verified, causally-grounded model of a codebase that reasons forward (what will decay, what will break, what will be forgotten), not just backward from a query, and it refuses to let an agent act without provable grounding.

The demo beat that sells this: ingest a repo → show the live graph → propose a change → blast radius + risk lights up → force a claim the model can't cite → the model refuses instead of hallucinating → export a signed grounding record. Report B is right that "refusal" is the memorable moment competitors don't have.

## 2. Reality check against the actual codebase

Both reports were written by researchers who don't have visibility into what's actually running. Before committing to their roadmaps, here's the real starting point:

- Graph: **in-memory**, Python objects, no Neo4j/Memgraph/persistent graph DB. Survives restart only because `rehydrate_repositories()` rebuilds it from disk clones + digest memory (fixed this session).
- Static analysis: **regex-based** (`backend/repository/analyze.py`), not a real parser. No AST, no data-flow edges, no GNN.
- Memory: **flat top-12 record injection** per chat turn, no ranking, no relevance scoping.
- Blast radius: real reverse-BFS over structural edges (`imports`/`calls`/`depends_on`/`flows_into`), confidence-weighted risk grading, now with a breakdown by type/files/call-edges (built this session) — genuinely ahead of "just BFS," but still purely structural, single-repo.
- LLM layer: 4 providers via litellm (NVIDIA, Groq, Gemini, Z.ai/GLM), task-tier routing already exists — this is the one piece that's already at "enterprise-plausible" maturity.
- No sandboxed execution environment for running generated code beyond a 10-second subprocess (`run_python` tool).
- No vector store of any kind.
- Single Windows dev machine, no deployed cloud infra.

This matters because Report B's "quick wins (weeks)" are realistic *for this codebase specifically* — tree-sitter, async annotation, graph-anchored memory are all additive to what exists. Report A's CEG/SSUR require capabilities (sandbox orchestration, parallel model sampling at scale, spectral computation pipelines) that would need to be built from zero, with real compute cost, before the *idea itself* could even be tested.

## 3. The final plan

### Phase 1 — Foundation hardening (do first, buildable now with current stack)

1. ~~**Replace regex static analysis with tree-sitter.**~~ **DONE.** `backend/repository/analyze.py` rewritten on tree-sitter (Python/JS/TS/TSX grammars via `tree-sitter`, `tree-sitter-python`, `tree-sitter-javascript`, `tree-sitter-typescript`), same `Symbol`/`Analysis`/`analyze_repo()` interface so `repository/api.py` needed zero changes. Verified end-to-end: standalone run on Auralis (133 symbols vs the old regex's 109 — now correctly captures class methods, which the old line-anchored regex never matched at all) and on the codexa-os backend itself (700 symbols incl. 85 real Python classes, 2.6s for 260 files); full rehydration on backend restart re-ran all 3 loaded repos through it with no errors; blast radius, fresh `/repository/load`, and persisted docs all re-verified working against the new graph. Note: `useServices`' blast-radius affected-count dropped from 23 → 4 — expected and correct, not a regression: the old regex's "call graph" was scoped by "text until the next symbol line" and inflated matches; tree-sitter's real AST scoping (a call only attributes to the function whose actual body contains it) is more conservative and accurate.
2. ~~**Async semantic annotation pass with a cost ceiling.**~~ **DONE.** New `backend/repository/semantic.py`: one LLM call per symbol (light tier, cost-capped at 80 symbols/run), stored as a single consolidated JSON blob per repo in `MemoryStore` (same pattern as the docs-persistence fix, not one record per symbol). Wired into `POST /repository/load` via FastAPI `BackgroundTasks` (confirmed the load response returns in 55ms — annotation genuinely doesn't block it) and a new `POST /repository/annotate?repository=X` for on-demand/manual runs on already-loaded repos. Frontend excludes this blob from the flat per-turn chat context (it's for graph-anchored lookups, not a top-12 dump — that's item 4 below).
3. ~~**Content-hash staleness.**~~ **DONE, shipped with #2.** Each `Symbol` now carries a `content_hash` (sha256 of its AST byte span) and `end_line`. Verified precisely: edited one function's source, re-ran — exactly 1 of 133 symbols re-annotated, 132 reused untouched; reverted the edit, re-ran — the 1 flipped back to stale and re-annotated correctly. Also found and fixed a real bug while testing: the light-tier model (Groq) hit its rate limit mid-run and was silently swallowing ~40% of annotations as "skipped" with no visibility. Added `LLMClient.models_for_task()` + a scoped fallback in the annotation loop that tries the next available light-tier model before giving up on a symbol — re-ran clean afterward (80/80 succeeded up to the cost ceiling, 0 silent failures). Full-repo coverage confirmed on Auralis: 133/133 symbols annotated with real, specific descriptions (e.g. "reads a stream of data from an S3 body stream, converting non-buffer chunks to buffers, and returns a single concatenated buffer" — not generic filler), queryable via the existing `/memory/records` API.
4. ~~**Graph-anchored ranked memory.**~~ **DONE.** New `backend/memory/context.py` (`GET /memory/context?repository=X&query=...`): resolves the question to real graph nodes (same name/path matching approach `impact.py` uses for blast-radius targets), pulls each matched symbol's semantic annotation from the Phase-1-item-2/3 blob plus its immediate call/import neighbors, and only falls back to the old flat digest-facts list when nothing resolves. Frontend (`chat/page.tsx`) now calls this per-turn keyed on the actual outgoing message instead of a memoized flat top-12. Verified end-to-end in the browser, not just at the API: asked "explain what useServices does and who calls it" against Auralis — the answer precisely matched the stored annotation and listed the exact 4 real callers from the graph (`UploadPage`, `DashboardPage`, `AccountCard`, `AuthPage`), with **zero tool calls and zero file searches** — this is the original ask from the semantic-memory-layer proposal working end-to-end. (Side note surfaced during testing, not a bug in this feature: the 8B model sometimes tries to "call" a symbol name as a tool instead of just answering from the provided context — a pre-existing tool-calling-eagerness quirk of that specific small model, not something this change introduced; GLM 5.2 handles it correctly.)
5. ~~**Git-mined change-coupling weights on blast-radius edges.**~~ **DONE — Phase 1 complete.** New `backend/repository/coupling.py`: mines `git log --name-only` for files that historically change together with no import/call link between them at all — CodeScene's peer-reviewed "hidden coupling" insight. Required also fixing the clone depth (`--depth 1` → `--depth 250`; a 1-commit shallow clone has no history to mine). Added as `CORRELATES_WITH` edges (an existing, previously-unused schema value — no schema change needed), stored in **both directions** since change-coupling is symmetric unlike imports/calls, and added to blast radius's traversed edge set. Verified on Auralis: found a real coupling pair (`UploadPage.tsx` ↔ `services/adapters/awsApi.ts`, 100% co-change strength across 3 shared commits) with zero manual tuning. End-to-end confirmed through the actual blast-radius summary sentence: *"Changing src/services/adapters/awsApi.ts propagates to 5 downstream components (5 files, 1 hidden coupling link) within 2 hops."* Also added a `coupling_edges` count to the impact breakdown (the call/import breakdown built earlier this session had no bucket for it — would have silently undercounted the exact thing this feature exists to surface).

### Phase 2 — Differentiators (medium effort, still buildable without new infra)

6. **Cross-repo blast radius** — resolve shared-dependency edges (package.json/pyproject) across all loaded repos, not just within one. Named by both reports as the sharpest technical differentiator; nothing in the competitive set does this well (Sourcegraph Cody caps at ~10 repos per query and is structural-only).
7. **Consensus-graded, drift-aware confidence** — upgrade from Phase 1's binary staleness (hash matches / doesn't) to Report B's continuous decay: an annotation's confidence erodes as its *neighbors* change, before its own hash even breaks. Cheap to add once #2+#3 exist (it's a propagation pass over already-stored confidence values).
8. **Socio-technical / ownership-fused risk** — git-blame-derived ownership on graph nodes; blast radius flags when the affected set crosses into code owned by someone not in the current conversation. This is the most concrete version of Report B's "Conway-fused blast radius" patent claim, and it's realistic to build with git-log parsing alone — no org chart integration needed for v1.
9. **Verifiable grounding record** — turn the existing "answer strictly from facts" prompt discipline into a mechanical, exportable artifact: every claim traces to a node ID + valid content hash + confidence, exportable as JSON/PDF. This is Report B's highest-willingness-to-pay item (regulated industries) and is realistic once #2–#4 exist, since the data it certifies already exists — it's a serialization/export feature, not new infrastructure.

### Phase 3 — Forward reasoning (the category-defining wedge, higher effort)

10. **Lightweight architecture-health forecasting** — *not* Report A's full multi-agent-swarm-simulates-a-year-of-tickets version (BOAD-style digital twin). Start with simple trend extrapolation over the metrics the platform already computes and stores as `ArchitectureTrend` nodes (coupling, complexity, churn) — linear/exponential projection forward, same math already backing the existing "projected bottleneck: 65 days" figure, just generalized and made an active alert instead of a passive dashboard number. This earns the "digital twin" positioning claim honestly without requiring a simulation engine that doesn't exist yet.
11. **Intent Graph (rationale capture)** — a new node type linked to CodeSymbols, populated by mining PR/commit descriptions the agent already has read access to via its tools, plus an explicit "why this change?" prompt at high-blast-radius moments. Both reports independently converge on this as the highest-value, least-addressed problem in the industry (institutional knowledge loss). Buildable with existing tool-calling infra; the hard part is UX (getting engineers to actually answer the prompt), not backend architecture.

### Explicitly deferred (named, patent-worthy, not on the near-term roadmap)

- **Counterfactual Execution Graphing** (Report A) — adversarial sandboxed execution to detect dynamic/runtime blast radius. Needs a real sandbox orchestration layer first; revisit once Phase 1–2 ship and there's a reason to invest in execution infra.
- **Spectral Semantic Uncertainty Routing** (Report A) — eigenvalue-based multi-model consensus. Interesting research direction, but Phase 2's simpler "flag disagreement between two providers on high-stakes symbols" gets ~80% of the practical benefit at a fraction of the engineering cost. Keep SSUR as a possible v2 of the consensus mechanism once basic disagreement-flagging is live and its limitations are actually felt.
- **Full Monte-Carlo digital twin / BOAD agent-swarm simulation** — superseded near-term by Phase 3's simpler trend extrapolation. Revisit only if trend extrapolation proves insufficiently predictive in practice.
- **Repository Immune System / AIxCC-style autonomous patching** — a strong award-pitch narrative, not a near-term engineering target. Requires the sandbox + CEG infra above as a prerequisite.

## 4. What to file as patent claims now, build later

Per both reports' Section-3-equivalents, the claims worth writing up and filing provisionally *before* any public demo, even though full implementation is Phase 3+:
- Causal-temporal forward simulation over an event-sourced code graph (Phase 3, simplified version ships first; full claim scope covers the eventual richer version).
- Socio-technical congruence gating (Phase 2, #8 — this one is close enough to shipping that filing should happen alongside Phase 2, not deferred).
- Verifiable grounding certificate (Phase 2, #9 — same, file alongside implementation).
- Consensus-graded drift-aware confidence decay (Phase 2, #7).

## 5. Immediate next action

Start Phase 1, item 1 (tree-sitter replacing regex) — it's the dependency everything else in Phases 1–3 sits on top of, it's a bounded, well-scoped piece of work, and it doesn't require any new infrastructure decision to begin.

---

*This plan intentionally does not adopt either source report wholesale. Report A's most ambitious ideas are preserved as named, deferred vision (useful for pitch/competition framing) rather than discarded, but the buildable roadmap follows Report B's more grounded sequencing, adjusted against the actual state of this codebase rather than an idealized one.*
