# Codexa as a Research Contribution — Related Work, Gap, and Readiness Audit

*Prepared 2026-09-25. Every claim about Codexa below was checked against the code in this
repository, not the README or the build spec. Related work was surveyed on arXiv / ACL Anthology /
OpenReview through September 2026.*

---

## 0. Verdict (read this first)

1. **The headline Codexa has today — "a tree-sitter code graph cuts agent tokens by 85.8×" — is not
   publishable as a novel result.** At least five 2025–2026 papers already show graph/structured
   repository context cutting agent tokens, most with stronger evaluation than ours:
   Codebase-Memory (Mar 2026: tree-sitter KG, 31 repos, 66 languages, **10× fewer tokens, 2.1× fewer
   tool calls**, with answer-quality scoring), CodeNib (Jul 2026: 50–87% fewer trajectory tokens),
   SWE-Pruner (23–54%), RepoAtlas (Sep 2026, SWE-bench Verified), RepoGraph, LocAgent, CodexGraph.
   Our 85.8× number additionally has methodological problems a reviewer will find in minutes (§4.1).

2. **There is a genuine, defensible gap — but it is not "graph for retrieval".** Every code-graph
   paper uses the graph as an *index*. Every agent-memory paper (MemGPT, Mem0, Zep, MIRIX, A-MEM) is
   conversational and verifies nothing. Every multi-agent-debate/sycophancy paper lacks a
   deterministic verifier because open-domain QA doesn't have one. **Code is the rare domain where a
   cheap, deterministic, partial oracle exists** (static structure + tool/execution logs). Codexa
   already *half-implements* using that oracle to govern (a) multi-agent belief revision (Quorum),
   (b) answer-claim verification, (c) memory conflict resolution, and (d) context retention.
   **Thesis: "Structure as Oracle, not just Index."**

3. **The strongest single paper** is the Quorum idea, tied to a NeurIPS 2025 theory result: Choi et
   al. prove multi-agent debate is a **martingale** — it cannot improve expected correctness unless
   belief updates are biased toward correction (e.g. oracle feedback). Codexa's Quorum is precisely
   such an intervention, with a real, non-hypothetical oracle. **Nobody has tested this in code.**

4. **Codexa is not yet paper-ready as an artifact.** The most important blockers: the Quorum
   "revise only on verified evidence" rule is enforced *only by prompt* and peers never see each
   other's verified claims; the "four memory types" are mostly a static repo digest with no learned
   episodic memory; temporal edges are never invalidated; no component has an ablation; the
   evaluation repositories are five small self-authored repos. All fixable — §5 is the work list.

---

## 1. What Codexa actually is (verified against code)

| Mechanism | Where | What it really does today |
|---|---|---|
| Structural code graph | `backend/repository/analyze.py`, `backend/graph/` | tree-sitter (Python, JS, TS, TSX) → nodes (file/function/class) + edges (imports/calls/depends_on). Edge schema enforces `confidence ∈[0,1]`, `source_type ∈ {static_analysis, llm_inferred, human_asserted}`, `valid_from/valid_to`; static edges forced to confidence 1.0; LLM-inferred edges must cite a source artifact (`graph/schemas.py:74-91`). In-memory by default, optional Postgres event store. **No Neo4j, Qdrant, MCP, or Redis**, despite `AGENTS.md`. |
| Symbol annotations | `backend/repository/semantic.py` | LLM writes one-line purpose per symbol, cached by content hash of source span; capped at `_MAX_ANNOTATE_PER_RUN = 80` symbols per ingest. |
| "Four memory types" | `backend/memory/store.py` | Records typed semantic / episodic / procedural / organizational, persisted to `.codexa/memories.json`. **446 of 469 persisted records come from a one-shot `repo_load` bundle.** For a real repo, "episodic" = *"Cloned from … on 2026-09-19 — 98 files"*, "procedural" = the `npm run` scripts, "organizational" = stack list + a health score. **No agent job writes episodic or procedural memory from experience** (grep of `backend/agents`, `backend/chat`: zero writers). |
| Graph-anchored context retrieval | `backend/memory/context.py` | Resolves the question to graph nodes, injects each symbol's annotation + 1-hop neighbours; falls back to repo digest. |
| Deterministic memory conflict resolution | `backend/memory/conflict.py` | Score = trust × corroboration; new record wins ties (recency tiebreak); losers soft-invalidated, never deleted. No LLM judgement. Never evaluated. |
| Graph-distance context eviction | `backend/agents/context_window.py` | Stale tool payloads for files within reverse-dependency depth 2 of the file currently being touched get 3× the normal staleness grace (`GRACE_MULTIPLIER_IN_RADIUS = 3`, `_RADIUS_DEPTH = 2`). Heuristic constants, no ablation. |
| Blast radius / impact | `backend/agents/impact.py` | NL change → resolved nodes → reverse-dependency traversal → risk grade, shown before changes. |
| Answer-claim verification | `backend/agents/verification.py` | LLM extracts checkable claims from the draft answer; each is resolved **deterministically** against graph or the turn's tool-return log; failed claims force a correction round. Never measured (precision/recall unknown). |
| Quorum | `backend/agents/quorum.py` | N models answer independently; claims verified against the graph *before* any peer exposure; ranked by (verified − failed, confidence × historical calibration). Only disagreeing ties go to one debate round. **The "revise only on a peer's verified claim" rule is prompt text only (`_DEBATE_PROMPT`, lines 74-87) — `_debate_round` accepts any revised card, and `peer_summary` passes peers' answers + counts but not the verified claims themselves.** |
| Temporal "time machine" | `backend/repository/intent.py`, `graph/service.py` | Edges backdated to each file's first git appearance. **`valid_to` is never set during ingestion** (only seed demo data) — deleted/refactored code never expires, so history shows only growth. |
| Trust boundary | `backend/perception/trust_boundary.py` | Regex detection of injection phrases on untrusted artifacts. |
| Receipts | `backend/agents/receipts.py` | Hash-chained receipts for mutating tool calls. |

Existing evidence: `docs/graph_token_reduction_proof.md` (retrieval payload, 5 repos / 174 symbols,
85.8×) and the abandoned agentic runner in `tests/benchmarks/memory_graph/` (all arms on all models
thrashed on hard questions; see §4.3).

---

## 2. Related work map

### 2.1 Repository graphs for coding agents (closest prior art — crowded)

| Work | What it does | Relevance |
|---|---|---|
| **Codebase-Memory** (arXiv 2603.27277, Mar 2026) | tree-sitter KG (66 langs), SQLite, 14 MCP tools, XXH3 incremental sync, Louvain communities. 31 repos. MCP agent vs file-explorer agent (Claude Opus 4.6): quality 0.83 vs 0.92, **10× fewer tokens, 2.1× fewer tool calls**. Static structure only — no memory, annotations, temporal validity, or conflict handling. | Pre-empts our token-reduction claim. Also shows the gap: graph-only agents **lose ~10% answer quality**. |
| **CodeNib** (2607.25431, Jul 2026) | Lexical + dense + SCIP structural views per commit, incremental maintenance; 50–87% fewer trajectory tokens than grep/read at preserved localization. | Pre-empts incremental multi-view serving. |
| **RepoAtlas** (2609.16936, Sep 2026) | Evolving task-relevant subgraph views with select–project–refresh; +3.0 SWE-bench Verified, fewer tokens. | Closest to graph-driven *context lifecycle*. |
| **Deterministic Anchoring** (2606.26979, Jun 2026) | Static structure injected as comments; +2.2 pts Func@5, 1.6 fewer rounds, variance halved, **+10% tokens**. | Shows structure helps via navigation discipline. |
| RepoGraph (ICLR 2025), CodexGraph (NAACL 2025, Neo4j + Cypher), LocAgent (ACL 2025, heterogeneous graph localization), Agentless, AutoCodeRover, SWE-agent, Aider repo-map | Foundational graph/structure retrieval for agents. | Must be cited; baselines for any eval. |
| PROOF (2609.06383, Sep 2026) | Verified NL specification layer, proven by reconstructing code from spec. | Adjacent to symbol annotations (verified semantics). |

**Takeaway:** "parse repo into a graph, let the agent query it, spend fewer tokens" is established.
Novelty must come from *what else the graph is used for*.

### 2.2 Agent memory architectures

| Work | Relevance |
|---|---|
| CoALA (Sumers et al., TMLR 2024) | Origin of the semantic / episodic / procedural taxonomy Codexa's store follows. |
| MemGPT/Letta, Generative Agents, A-MEM (2025), Mem0 / Mem0g (2025) | LLM-managed memory; Mem0 lets the LLM choose ADD/UPDATE/DELETE. |
| **Zep / Graphiti** (2501.13956) | Bitemporal KG memory: `t_valid/t_invalid`, soft invalidation, provenance. Codexa's `valid_from/valid_to` + soft-invalidate mirrors this but never sets `valid_to`. |
| MIRIX (2507.07957) | Six memory types with dedicated managers — more complete than Codexa's four. |
| LongMemEval, MemoryAgentBench (2507.05257) | Benchmarks incl. knowledge-update/conflict tasks where LLM-judged updates fail — the motivation `conflict.py` cites but never tests against. |
| SWE-Exp (2507.23361), trajectory-abstraction repair memory (2607.29658), subtask-level memory (2602.21611), SWE Context Bench (2602.08316) | **Experience memory for SWE agents** — exactly what Codexa's "episodic/procedural" should be and isn't. SWE-Exp: 73.0% SWE-bench Verified with an experience bank. |

**Takeaway:** four typed memories alone are not novel, and Codexa's are not experiential. What's
unusual is **deterministic, code-grounded admission and conflict resolution** — a memory fact about
code can be checked against the code.

### 2.3 Context management / bloat

The Complexity Trap (2508.21433, NeurIPS'25 DL4Code: simple observation masking ≈ LLM summarization
at half the cost on SWE-bench Verified — open-source harness), SWE-Pruner (2601.16746, learned 0.6B
line skimmer), SWE-Pruner Pro (2607.18213), Agent-Omit (2602.04284), ContextWeaver (2604.23069,
dependency-structured memory), and a withdrawn Aug 2026 preprint "Blast Radius" (2608.07440) that
estimates a prompt's reach through coupled context/code channels to archive dead context (17–26%
savings). Token-cost studies: "How Do AI Agents Spend Your Money?" (2604.22750) — input tokens
>99% of spend, reads ≈76% of tokens; Lost in the Middle; Chroma "context rot".

**Takeaway:** graph-distance eviction is plausible and under-explored (only a withdrawn preprint
does something similar), and there is an open-source masking harness to plug into.

### 2.4 Multi-agent debate, sycophancy, verification

| Work | Relevance |
|---|---|
| **Debate or Vote** (Choi, Zhu, Li — NeurIPS 2025 Spotlight, 2508.17536) | Majority voting explains most MAD gains; debate is a **martingale** over beliefs → no expected improvement *unless updates are biased toward correction* (oracle feedback, confidence weighting). **The theoretical hook for Quorum.** |
| Du et al. (ICML 2024) MAD; ReConcile (ACL 2024, confidence-weighted) | Classic MAD baselines. |
| CONSENSAGENT (ACL Findings 2025), Peacemaker or Troublemaker (2509.23055), Too Polite to Disagree (2604.02668), Not All Flips Are Conformity (2606.00820), Talk Isn't Cheap (2025), Minority Sentinel (2606.29270) | Sycophancy/conformity in MAD — flip taxonomies and mitigations, all prompt- or voting-based, **none with a deterministic verifier**. |
| **Tool-MAD** (2601.04742, Jan 2026) | Agents with different retrieval tools debate for fact verification. Closest "tool-grounded debate" — but evidence is retrieved text judged by the LLM, and revision is unconstrained. |
| AgentHallu (2601.06818), MARCH (ACL 2026), span-level hallucination over code/tool output (2607.00895) | Hallucination detection for agents; Codexa's verifier is a code-specific deterministic instance. |

**Takeaway:** "use a deterministic program-analysis oracle to gate belief revision, and measure the
effect on sycophantic flips" is **open**. Code is uniquely suited because the oracle is cheap.

### 2.5 Temporal code graphs (lower priority)
Zep/Graphiti, GitTemporalAI (OpenReview), practitioner tools (Memtrace, bi-temporal MCP code graph).
Codexa's temporal layer is too thin to contribute here right now.

---

## 3. The gap and the recommended paper

### 3.1 Gap statement

> Code-graph systems use program structure to **retrieve** context. Memory systems store facts but
> **cannot verify** them. Multi-agent debate lacks a **correction-biasing oracle**, so it provably
> cannot improve expected correctness and empirically drifts toward sycophantic consensus. In
> software repositories a cheap, deterministic, partial oracle already exists — the program
> structure itself — yet no system uses it to **govern** what agents believe, remember, and keep in
> context.

### 3.2 Recommended primary paper (highest novelty, cleanest experiment)

**Working title:** *Structure as Oracle: Verification-Gated Consensus Against Sycophancy in
Multi-Agent Code Reasoning*

- **C1 — Method.** Verification-gated quorum: independent answers → claims verified against a
  static-analysis oracle *before* exposure → only disagreeing ties debate → a belief revision is
  **accepted only if it is entailed by a peer's verified claim** (hard, code-enforced gate, not a
  prompt request).
- **C2 — Theory link.** Frame the gate as the correction-biasing intervention Choi et al. show is
  necessary to break the debate martingale; derive the condition (oracle coverage × precision) under
  which expected accuracy strictly improves, and test it.
- **C3 — Measurement.** Oracle coverage (fraction of agent claims about a repo that are
  deterministically checkable) and verifier precision/recall on hand-labelled claims.
- **C4 — Empirical.** Flip analysis (correct→wrong / wrong→correct), accuracy, and cost versus
  single agent, self-consistency/majority vote, free-text MAD, confidence-weighted MAD (ReConcile),
  CONSENSAGENT, Tool-MAD-style retrieval debate — plus an **adversarial persuasive-wrong-peer**
  stress test from the sycophancy literature.

**RQs.** RQ1 Does gated revision reduce harmful flips and raise accuracy vs. vote/debate?
RQ2 How much of repository QA is oracle-checkable, how accurate is the oracle? RQ3 How does the
benefit scale with oracle coverage (answers the martingale condition empirically)? RQ4 Cost vs.
majority vote?

### 3.3 Secondary papers (from the same artifact)

- **P2 — Graph-distance context eviction** (workshop scale, cheap): add a "keep observations of
  files within k reverse-dependency hops of the current focus" policy to the open-source Complexity
  Trap harness; compare against raw, observation masking, LLM summarization, hybrid on SWE-bench
  Verified. Clean single-variable paper.
- **P3 — Oracle-grounded agent memory for codebases** (larger): deterministic admission, conflict
  resolution, and temporal invalidation of memory about code, plus real trajectory-derived episodic
  memory; evaluate on SWE Context Bench / repeated-task settings vs. SWE-Exp and Mem0-style LLM-
  managed updates.
- **Umbrella systems paper** only after P1–P3 have their own ablations; a "we built all of it"
  paper without per-component evidence will be rejected.

### 3.4 Component novelty scorecard

| Component | Closest prior | Novelty now | Potential after fixes |
|---|---|---|---|
| Tree-sitter code graph retrieval | Codebase-Memory, RepoGraph, LocAgent, CodeNib | Low | Low (enabler only) |
| Graph → token reduction | Codebase-Memory (10×), CodeNib, SWE-Pruner | Low | Low (confirmatory) |
| Symbol annotations, content-hash cached | Codebase-Memory (hash sync), Deterministic Anchoring, PROOF | Low | Low–Med |
| Four typed memories | CoALA, MIRIX | Low | Med with experiential memory |
| Deterministic, code-grounded memory conflict resolution | Mem0 / Zep (LLM-judged) | Med | **Med–High** with LongMemEval-style eval |
| Graph-distance eviction | Obs. masking, SWE-Pruner, withdrawn "Blast Radius" | Med | **Med–High** |
| Deterministic answer-claim verification | AgentHallu, MARCH, span-level detection | Med | Med |
| **Oracle-gated quorum** | Choi et al. (theory), Tool-MAD, CONSENSAGENT | **High** | **High** |
| Blast-radius gating | classical change-impact analysis | Low | Low–Med |
| Temporal edges | Zep, GitTemporalAI | Low | Med only with real invalidation |
| Regex trust boundary | CaMeL, AgentDojo | Low (weak vs. SOTA) | Keep out of paper |

---

## 4. Shortcomings a reviewer will find

### 4.1 The 85.8× token result (critical — do not publish as-is)
1. **Strawman baseline.** "Raw" charges every byte of every defining + referencing file. Real
   agents grep and read ranges. Codebase-Memory's baseline is an actual explorer *agent*.
2. **Inflated by data files.** gods-eye-view contributes 814K of 1.86M raw tokens (44% of the
   aggregate). Its sampled symbols live in multi-hundred-KB data dumps (`src/data/flights.js`
   263 KB, `cctv.js` 198 KB; `ui.js` 466 KB; even `vite.config.js` 343 KB). No agent would read those
   whole; they produce the 216×.
3. **No answer-quality measurement.** Payload size only. Codebase-Memory shows graph-only answers
   lose ~10% quality — the metric that matters is tokens *at equal quality*.
4. **Tiny, self-authored, JS-heavy repos** (1.3K–17K LOC, one ~100K inflated by data) — selection
   bias; no standard benchmark repos.
5. **Selection:** only symbols with ≥1 caller; graph payload excludes the file reads still needed
   to answer "what does it do"; tokenizer is cl100k, not the models'.

### 4.2 Quorum (the would-be headline) is under-built
1. Revision gating is a prompt instruction; `_debate_round` accepts every revision.
2. `peer_summary` passes answer + verified/failed *counts*, never the verified claim text — agents
   cannot do what the prompt asks.
3. One debate round only; no flip logging; no baselines; `tests/test_quorum.py` checks plumbing,
   not the anti-sycophancy property.
4. Oracle coverage and verifier precision unknown; claim extraction is an LLM step whose recall is
   unmeasured (a model can evade the gate by making uncheckable claims).
5. Calibration score uses historical verification, fine — but needs a cold-start analysis.

### 4.3 Evaluation harness
1. `tests/benchmarks/memory_graph/runner.py` drives `JobManager` directly and **skips the real
   client-side memory injection** (`buildRepoContext`), so "Full Codexa" there isn't full Codexa.
2. On hard multi-hop questions every arm on every model (mercury-2.5, solar-pro4, GLM) thrashed
   130K–1.9M tokens without converging; an answer-capture bug was fixed late. Need fixed budgets,
   success rate, cost-per-success, pass@k with variance.
3. Proprietary, churning APIs (several models died mid-project) → irreproducible. Need open-weight
   models.
4. Test suite needs a live Postgres (`tests/test_architecture_evolution_api.py` errors on
   connection timeout) — reviewers/artifact evaluators will hit this.

### 4.4 Memory
1. Episodic/procedural/organizational are static digest partitions, not memories of experience.
2. Conflict resolution: uncalibrated trust values; tie → newer wins means a single contradicting
   write at equal trust overwrites a once-corroborated fact; never tested on knowledge-update
   benchmarks.
3. Temporal validity: `valid_to` never set → no invalidation on refactor/deletion; "time machine"
   cannot answer "what was true at t" correctly for removed code.
4. Annotation cap of 80 symbols/run → partial coverage on real repos; annotation accuracy
   unmeasured.

### 4.5 Graph fidelity
1. Only Python/JS/TS/TSX (Codebase-Memory: 66 languages).
2. Call-edge precision/recall never measured against a ground truth (e.g. PyCG, SCIP indexes).
   The oracle's correctness *is* the paper's premise — this must be measured.
3. Dynamic dispatch, reflection, macros, DI frameworks unrepresented → oracle blind spots; report
   them, and report them as "unverifiable", not "false".

### 4.6 Positioning / honesty
1. `AGENTS.md` still mandates Postgres + Neo4j + Qdrant + Redis + MCP + Docker; the artifact has
   none of Neo4j/Qdrant/Redis/MCP, sandbox unwired. The paper must describe the artifact as it is.
2. No MCP server → Codexa can't be dropped into Claude Code / Cursor / SWE-agent for evaluation,
   while Codebase-Memory can. Exposing the graph + verifier over MCP makes every experiment easier.
3. Semantic search depends on Gemini embeddings (proprietary).
4. Regex trust boundary is weak vs. CaMeL/AgentDojo — omit from the paper or evaluate properly.

---

## 5. Modifications to make Codexa a strong research artifact

**Tier 1 — required for the primary paper**
1. **Hard-gate Quorum revision** (`quorum.py`): pass each peer's *verified claims* (text + check
   result) in the belief card; accept a revised card only if (a) its answer changed *and* (b) the
   change is supported by ≥1 peer claim that verified and contradicts/extends the agent's own; else
   restore the original card. Log every flip with its justification.
2. **Instrument flips and costs:** per round, per agent: answer, claims, verified/failed, tokens.
3. **Oracle quality study:** hand-label ~300–500 claims across repos; report claim-extraction
   recall, verifier precision/recall, and coverage by claim type (existence, caller/callee, import,
   location, test-outcome, runtime-behaviour = uncheckable).
4. **Baselines** in the same harness: single agent, self-consistency/majority vote, free MAD
   (Du et al.), ReConcile-style confidence weighting, CONSENSAGENT-style prompt mitigation,
   Tool-MAD-style retrieval debate, and "gate by prompt only" (the current implementation) as an
   ablation.
5. **Adversarial sycophancy test:** inject a confident, persuasive, *wrong* peer; measure capitulation.
6. **Open-weight panel** (e.g. Qwen3-Coder, DeepSeek-V3.x, Llama) + one closed model; ≥3 seeds.

**Tier 2 — needed for any token/efficiency or memory claim**
7. Replace the whole-file baseline with an agentic grep+range-read baseline; add BM25/dense RAG,
   Aider repo-map, and Codebase-Memory/CodeNib as baselines; **always report answer quality**.
8. Exclude or separately report data/generated/minified files; move to standard repos (SWE-QA's 15
   repos, SWE-bench Verified repos) with multiple languages.
9. Make the benchmark runner use the same server-side context assembly the product uses.
10. Write **experiential episodic memory** (task, files touched, verified outcome, failure reason)
    and **procedural memory** (successful tool sequences) at job end; retrieve by graph anchor.
11. Set `valid_to` on re-ingest when an edge/node disappears; add temporal-query tests.
12. Measure call-graph precision/recall vs. PyCG/SCIP ground truth.

**Tier 3 — engineering hygiene for artifact evaluation**
13. MCP server exposing graph queries, blast radius, and claim verification.
14. Tests runnable without Postgres (in-memory default; DB tests behind a marker).
15. Open embedding model option for semantic search.
16. Update `AGENTS.md` to match reality or move the aspirational stack into a "future work" doc.
17. Release harness + labelled claims + raw logs; pin model versions; seed everything.

---

## 6. Evaluation plan (primary paper)

| Item | Choice |
|---|---|
| Tasks | Repository QA with checkable answers: **SWE-QA** (720 Q, 15 Python repos), **RepoProbe** (2608.04783), Codebase-Memory's structural question categories; localization subset of SWE-bench Verified (LocAgent's setup) for a downstream signal. |
| Systems | See Tier 1 #4. Same panel size (e.g. 3 agents) and token budget across systems. |
| Metrics | Accuracy (reference-graded + LLM-judge with human spot-check), harmful-flip rate, beneficial-flip rate, capitulation rate under adversarial peer, tokens and $ per question, oracle coverage. |
| Stats | Paired bootstrap 95% CIs; McNemar on per-question correctness; report variance across seeds. |
| Analysis | Accuracy gain vs. oracle coverage (tests the martingale condition); error taxonomy of oracle blind spots. |

Pilot first: 1 repo, 50 questions, 3 open models, 3 seeds — enough to know whether the effect exists
before scaling.

---

## 7. Venues (verify current deadlines before planning)

- **Primary paper (sycophancy/MAD angle):** ACL Rolling Review (ACL/EMNLP/NAACL); NeurIPS/ICLR if
  the theory section is strong.
- **SE angle:** ICSE / FSE / ASE main tracks; LLM4Code (ICSE workshop); DL4Code (NeurIPS/ICLR
  workshop) — good first target for the eviction paper (P2).
- Workshop-first is realistic for a first paper; convert to a full paper with the scaled study.

---

## 8. What not to claim

- "Graph reduces tokens 85.8×" as a contribution (pre-empted and methodologically weak).
- "Four-type cognitive memory" (not experiential yet; MIRIX already has six).
- "Prevents hallucination / sycophancy" without the flip and verifier measurements.
- Neo4j / Qdrant / MCP / Docker sandbox (not implemented).
- The regex trust boundary as a security contribution.

---

## 9. References (links verified in this survey unless marked †)

- Codebase-Memory — https://arxiv.org/abs/2603.27277
- CodeNib — https://arxiv.org/abs/2607.25431
- RepoAtlas — https://arxiv.org/abs/2609.16936
- How Much Static Structure Do Code Agents Need? (Deterministic Anchoring) — https://arxiv.org/abs/2606.26979
- PROOF: From Reading Code to Reading Spec — https://arxiv.org/abs/2609.06383
- LocAgent (ACL 2025) — https://aclanthology.org/2025.acl-long.426.pdf
- RepoGraph (ICLR 2025) † arXiv 2410.14684; CodexGraph (NAACL 2025) † arXiv 2408.03910
- Zep: Temporal KG Architecture for Agent Memory — https://arxiv.org/abs/2501.13956
- MIRIX — https://arxiv.org/abs/2507.07957
- MemoryAgentBench (Evaluating Memory via Incremental Multi-Turn Interactions) — https://arxiv.org/abs/2507.05257
- SWE-Exp — https://arxiv.org/abs/2507.23361
- Reusing Past Repairs via Hierarchical Trajectory Abstraction — https://arxiv.org/abs/2607.29658
- SWE Context Bench — https://arxiv.org/abs/2602.08316
- The Complexity Trap (observation masking) — https://arxiv.org/abs/2508.21433 · code: https://github.com/JetBrains-Research/the-complexity-trap
- SWE-Pruner — https://arxiv.org/abs/2601.16746 · SWE-Pruner Pro — https://arxiv.org/abs/2607.18213
- ContextWeaver — https://arxiv.org/abs/2604.23069 · Agent-Omit — https://arxiv.org/abs/2602.04284
- "Blast Radius" (withdrawn) — https://arxiv.org/abs/2608.07440
- How Do AI Agents Spend Your Money? — https://arxiv.org/abs/2604.22750
- Debate or Vote (NeurIPS 2025) — https://arxiv.org/abs/2508.17536
- Tool-MAD — https://arxiv.org/abs/2601.04742
- CONSENSAGENT (ACL Findings 2025) — https://aclanthology.org/2025.findings-acl.1141/
- Peacemaker or Troublemaker — https://arxiv.org/abs/2509.23055
- Too Polite to Disagree — https://arxiv.org/abs/2604.02668
- Not All Flips Are Conformity — https://arxiv.org/abs/2606.00820
- Minority Sentinel — https://arxiv.org/abs/2606.29270
- AgentHallu — https://arxiv.org/abs/2601.06818
- SWE-QA — https://arxiv.org/abs/2509.14635 · RepoProbe — https://arxiv.org/abs/2608.04783
- † CoALA (Sumers et al., TMLR 2024, arXiv 2309.02427); MemGPT (2310.08560); Mem0 (2504.19413);
  A-MEM (2502.12110); LongMemEval (ICLR 2025, 2410.10813); Du et al. MAD (ICML 2024, 2305.14325);
  ReConcile (ACL 2024, 2309.13007); Lost in the Middle (TACL 2024, 2307.03172); SWE-agent
  (2405.15793); Agentless (2407.01489); AutoCodeRover (2404.05427); CaMeL (2503.18813);
  AgentDojo (2406.13352).

† = well-known work cited from memory; confirm IDs/venues before submission.
