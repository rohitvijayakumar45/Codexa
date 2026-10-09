# Codexa: conference-paper research assessment

Assessment date: 7 October 2026. Repository inspected at `0ea016a` on `main`, including existing uncommitted work. This assessment is independent of the repository's earlier research plans. Quorum mode is excluded from the assessment, comparisons, experiments, and recommendations.

No application code changed. No live model requests, paid APIs, training, or large benchmark runs started. Only this report was added. Existing research results were preserved.

Evidence labels throughout: **Observed** means inspected code or saved artifacts; **Recomputed** means arithmetic independently checked from saved results, not a rerun of the original experiment; **Reported** means documentation without sufficient underlying evidence; **Interpretation** means an assessment; **Proposed** means work not performed.

## 1. Executive verdict

**Interpretation: useful research artifact; insufficient evidence for a strong full research paper today.** The implemented repository graph, memory freshness mechanisms, replay harness, and execution telemetry offer a credible starting point. The broad “engineering brain” architecture is a useful integration, with several incomplete subsystems, rather than an established novel method.

**Strongest direction:** a bounded empirical study of how stale repository memory changes coding-agent behavior and whether claim-specific freshness checks reduce that harm at acceptable cost. Focus initially on paths, commands, signatures, and structural relationships. This is stronger than a paper claiming that code graphs save tokens or that content hashes establish semantic truth.

**Largest gap:** no controlled, independently graded downstream evaluation links the new memory mechanisms to task success, harmful actions, latency, or actual cost. The best saved experiment measures changes in facts extracted by Codexa's own parser. It does not measure arbitrary memory truth, natural context-file prevalence, or agent performance.

**Publication readiness:** current evidence can support an honest technical report and a prototype demonstration. A short empirical paper becomes plausible after independent oracle validation, reproducible packaging, and a bounded pilot. A full paper needs substantially broader held-out evidence. Neither acceptance nor novelty is guaranteed.

Closest competition already establishes artifact anchoring and claim-relative invalidation: [EA-Graph](https://arxiv.org/html/2608.04278v1), [Executable Code Knowledge](https://arxiv.org/html/2608.16295v1), and [Impact Is Not Invalidation](https://arxiv.org/html/2609.25130v1). Context-file staleness is already studied in [Context Rot](https://arxiv.org/html/2606.09090v1). The opportunity is a carefully differentiated empirical question and evaluation, not claiming ownership of these mechanisms.

## 2. Repository findings

### Problem, users, and actual data flow

**Observed:** Codexa helps developers navigate a repository, answer structural questions, assess change impact, and run LLM tool-use jobs with persistent project context. Its intended engineering-intelligence platform is specified in `docs/codexa_os_build_prompt_v5.md`, Sections 0–9. The running implementation is narrower than that specification.

Actual principal path:

1. Repository load/reindex parses Python, JavaScript, TypeScript, and TSX into files, symbols, imports, and approximate call edges (`backend/repository/analyze.py:242`; ingestion in `backend/repository/api.py:801`).
2. Graph nodes/edges feed impact queries and repository memory. Optional LLM symbol glosses are cached by content hash (`backend/repository/semantic.py:125`).
3. The UI asks `/memory/context` for a targeted map and injects it into a chat request (`graph-viz/app/(workspace)/chat/page.tsx:125,710`; `backend/memory/context.py:163`).
4. `JobManager` plans, streams model rounds, executes tools, validates tasks/claims, checkpoints, and emits telemetry (`backend/agents/jobs.py`). Model routing and fallback are handled by `backend/agents/llm.py`.
5. New experience hooks record job episodes and successful commands into memory (`backend/agents/jobs.py:1193`; `backend/memory/experience.py:174`). Ingestion sweeps anchors; retrieval rechecks file-only anchors.

Separate APIs expose graph-based proposals, simulation, policy, sandbox scheduling, trends, and incident knowledge. They should not be mistaken for a single fully wired production pipeline.

### Implemented versus partial

| Component | Observed implementation and evidence | Research interpretation / limitation |
|---|---|---|
| Structural repository graph | Real tree-sitter grammars, file/symbol extraction, imports, approximate calls. `backend/repository/analyze.py:25,242,350`. | Established technique. AST extraction does not make call resolution complete or correct. No independent precision/recall evaluation found. |
| Graph schema and persistence | Edge confidence/source/temporal fields validated (`backend/graph/schemas.py:74`); in-memory or optional Postgres repositories (`backend/main.py:120`; `backend/graph/repository.py`). | Real storage/API implementation. Node/edge writes and event appends are separate operations (`backend/graph/service.py:23,32`), not a demonstrated transactional outbox. |
| Graph projections / consistency | Infrastructure declares Neo4j, Qdrant, Redis. Consistency API compares supplied counts and returns suggested repair names (`backend/graph/consistency.py:35`). | No operational projection/reconciliation pipeline established. Container declarations are not implemented store integration. |
| Time queries | Temporal edge filtering and node creation-time filtering (`backend/graph/service.py:63`). | Not full historical node-property reconstruction. Stable-ID upserts overwrite properties (`backend/graph/repository.py:105`). |
| Memory store | Four typed records, JSON persistence, corroboration/conflict handling, soft invalidation (`backend/memory/store.py:20`; `backend/memory/conflict.py:25`). | Useful engineering. Conflict resolution is a trust/count/recency heuristic, not evidence that conflicting statements were semantically resolved correctly. |
| Memory anchors | File, symbol span, tree, symbol-index, and query-result hashes; episodic records retained with outdated markers (`backend/memory/anchors.py:1,111,204,252`). | Functional new working-tree implementation. Support changes and truth changes differ. Query anchors are exact only relative to the represented query and graph. |
| Memory retrieval | Name/path matching, nearby graph relations, glosses, keyword/type weighting; file-only freshness checks (`backend/memory/context.py:74,98,167`). | No general learned semantic retrieval here. Structural anchors await reindex; annotation blob reads do not independently revalidate live source bytes. |
| Annotation allocation | Callers, exact callers, PageRank, degree, churn, random, parser order, lazy policies (`backend/repository/annotation_policy.py`). | Real configurable policy comparisons. Centrality and budgeted repository maps are established; useful new application alone is weak novelty. |
| Experience memory | Tool transcript-derived episodes and zero-exit commands (`backend/memory/experience.py:110,174`). | An attempted write is listed as modified without checking its successful tool result. A zero exit at one time does not prove a command will succeed later. Manifest anchors omit source/environment changes affecting tests. |
| Impact and answer checking | Reverse dependency traversal (`backend/agents/impact.py`); final-answer claims checked against graph/tool exits (`backend/agents/verification.py:81,210`). | Deterministic partial checking is useful. LLM claim extraction/unsupported claims and incomplete graph introduce coverage gaps; invocation alone does not prove an action succeeded. |
| Task orchestration | Plans, required tools, completion validators, progress tracking, receipts, persisted jobs/events and round telemetry (`backend/agents/plan.py`, `controller.py`, `jobs.py`, `receipts.py`, `round_telemetry.py`). | Substantial working harness. Historical looping/provider failures are engineering evidence, not a controlled advantage over other harnesses. |
| Simulation and sandbox | Heuristic blast-radius/schema-risk scoring with diff hash; scheduling gate (`backend/simulation/engine.py:48`; `backend/execution/sandbox.py:46`). | Does not apply diffs or execute containers. Main tool loop directly executes tools outside this API gate (`backend/agents/jobs.py:1900`). Do not claim universal simulation-before-execution. |
| Graph witness | Hashes selected node identities/types/properties (`backend/simulation/witness.py:22`). | Node mutation/deletion checks are real. Hash excludes edge changes and newly reachable nodes; it cannot establish complete dependency-subgraph freshness. |
| Trust boundary | Trust-tagged ingestion and instruction-shaped line stripping (`backend/perception/trust_boundary.py:14`). | Local filtering, not validated prompt-injection isolation for every input path. Not a security contribution without separate adversarial evaluation. |
| Intent, conventions, causal and incident knowledge | APIs persist cited chains/profiles; incident chain links affected files (`backend/memory/services.py`; `backend/graph/causal.py`; `backend/trust_safety/incident.py`). | Many facts are supplied by callers. Automatic ADR/PR mining and complete agent consumption are not established. |
| Trends, economics, health, learning, nightly review | Deterministic services over supplied inputs; RFC generation; in-process distillation versions (`backend/understanding/architecture_evolution.py`, `nightly_review.py`; `backend/trust_safety/economics.py`, `health.py`; `backend/learning/policy_distillation.py`). | No demonstrated automatically collected longitudinal signals, calibrated predictive validity, applied learning updates, or RQ nightly scheduler. |
| Visualization | Three.js graph and deterministic Strata/focus/matrix representations, provenance/confidence/time styling (`graph-viz/components/graph/GraphScene.tsx`; `graph-viz/lib/strata/model.ts:129`; `layout.ts`; `components/strata/StrataView.tsx`). | Potential demo asset. No developer task/user study or comprehension benefit established. No browser usability verification performed in this assessment. |

### Limitations that affect scientific validity

**Observed parser caps:** 1,500 source files, 4,000 symbols, 8,000 edges, 12 calls per symbol, 1 MB per file (`backend/repository/analyze.py:25–35`). Definitions and calls can be silently skipped. The gods-eye-view annotation result has mean exactly 4,000 symbols, consistent with hitting the cap. Unresolved calls, dynamic dispatch, external code, receiver identity, traversal order, and language coverage limit graph fidelity.

**Observed freshness distinction:** `anchors.py` describes changed support as implying false descriptive memory. That inference is invalid for arbitrary prose: a comment/body edit can preserve the claim; a callee/environment change can falsify it while its own span stays identical. Unknown anchor kinds match and unanchored records remain untouched. These are coverage/availability decisions, not proof of validity. For an exact structural query, a matching digest establishes unchanged extracted answer, conditional on faithful parsing and a complete query domain.

**Observed reproducibility limits:** current source and new memory experiments are partly uncommitted; `main`/HEAD does not identify the complete evaluated artifact. `pyproject.toml` uses dependency ranges. LLM requests do not pin sampling settings/model revisions; provider fallback can change the treatment. Normal provider usage and estimated tokens are mixed across pathways, and interrupted attempts lack complete usage (`backend/agents/llm.py:657,701`; `jobs.py:1450`; `round_telemetry.py:66`).

## 3. Existing evaluation audit

### Evidence inventory and what each experiment establishes

| Evidence | Question / setup / sample | Saved result and verification | What it does and does not establish |
|---|---|---|---|
| Memory anchoring replay | Six extracted fact families: signatures, callers, callees, imports, scripts, dependencies. Five repositories; 144 saved snapshot-pair records at k=1,5,20; six anchor policies plus commit-age TTL5/20; deterministic seed. `tests/benchmarks/memory_anchoring/replay.py:241`; `anchoring_facts.py:1`; `results/*.json`. | **Recomputed:** 106,248 fact/snapshot observations per policy; confusion totals below. Original sampled git-history replay was not rerun. | Relative consistency/invalidation tradeoffs on sampled parser-defined facts. Not 106,248 independent natural memories. No downstream agent effect, general semantic validity, or representative staleness prevalence. |
| Annotation budget replay | Four repositories; bases 10/3/10/3, horizon20; K=0,20,40,80,160,all; random seeds0–4. Future source/file edits proxy demand; no gold questions. `tests/benchmarks/annotation_budget/run.py:97,188`; `results/*.json`. | **Observed:** at K80, Codexa callers covers .137 of future-edited symbols versus random .038; httpx parser order .177 exceeds callers .149; gods-eye callers .023 is below random .031. Tables in `docs/research/anchored_memory_results.md`. | No consistently best policy. Predicting edited symbols is not measuring actual lookup demand, gloss accuracy, agent quality, or paid annotation cost. |
| Deterministic retrieval payload | Five repositories, 174 graph-selected symbols with incoming dependencies; entire defining/referencing file tokens versus targeted graph response; `cl100k_base`; no LLM. `tests/benchmarks/memory_graph/retrieval_payload.py:50,93,111`; `payload_results/*.json`. | **Recomputed:** 1,860,803 versus 21,684 tokens, ratio85.8146, reduction98.8347%. | Correct arithmetic for selected payloads. Weak whole-file baseline; file selection is graph-derived; no answer quality, indexing/annotation amortization, or real agent cost equivalence. Do not claim 85.8× cheaper agents. |
| Original agent graph campaign | Raw/file-tool, graph-enabled, full-named arms × four authored questions on Exam-Proctoring; 12 saved runs; historical free GLM model. `memory_graph/configs.json`, `questions.json`, `runner.py`, `raw_runs/*.json`. | **Observed:** saved status, token, duration, output summaries. No correctness labels. | One attempt per cell; model instability and harness changes confounded. The graph arm retains file tools, so it is not a strictly graph-only modality. |
| Solar repeated agent campaign | 70 saved runs: A32, B32, C6 (C only q1); eight repetitions per A/B question, six C/q1. `raw_runs_solar/*.json`. | **Recomputed/inspected:** 47 done, 23 error, four zero-token; only two stored answers ≥200 characters. A nonempty or long answer is not a correctness verdict. | Unbalanced campaign with poor answer capture, no reference answers, and no complete three-arm pairing. No credible accuracy/cost-per-correct-answer result. |
| Later token report | `docs/token_bench_results.md` reports Solar full n5 per question versus raw, 8–16× reductions and universal completion. | **Reported:** referenced `scratchpad/bench_matrix.py` and corresponding raw campaign not found in repository inventory. | Cannot independently verify this report's efficacy/reliability conclusion. Do not substitute earlier raw JSONs from a different harness/campaign. |
| Build/incident logs and 2×2/planning scripts | HTML generation/refinement, provider failures, planner outcomes; `BENCHMARK_LOG.md`, `LIVE_BENCHMARK_LOG.md`, `PROBLEMS.md`, `AUDIT.md`, `scripts/experiment_2x2.py`, `scripts/plan_trials.py`. | **Observed/Reported:** valuable debugging chronology and scripts; no common controlled quality score, fixed intervention/version ledger, randomized conditions, or complete matched campaign identified. | Good failure-case discovery. Not independent design-quality wins or causal attribution to individual fixes. Provider changes and simultaneous prompt/lifecycle changes confound comparisons. |
| Saved feature audit | Dated 15 September2026 suite evidence under `tests/audit/codexa_claims/evidence/`; in-scope suite statuses inspected by investigator. | **Observed:** saved local contract/integration audit. Excluded suite omitted. | Correctness checks on fixtures; not research evaluation, production deployment proof, or current full-suite verification. |

### Independently recomputed anchor confusion counts

Positive class = extracted fact changed. Sum `overall` confusion fields across exactly five saved result JSONs, then recompute metrics.

| Policy | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| File anchors A2 | 1,779 | 22,650 | 284 | 81,535 | .0728 | .8623 | .1343 |
| Symbol anchors A3 | 1,573 | 8,606 | 490 | 95,579 | .1545 | .7625 | .2569 |
| Query-policy A5 | 2,062 | 1,991 | 1 | 102,194 | .5088 | .9995 | .6743 |

The rounded documentation table is arithmetically consistent. Its A5 recall1.000 and stale-served0.000 hide one false negative. A5 is a mixed policy: query hashes for F2–F4, symbol/manifest fallbacks elsewhere. Exact F2–F4 scores are self-consistency checks because labels and anchors use the same graph relationships. This is not fraudulent, but its construct must be stated correctly.

Per-repository A5 F1 ranges from .252 (gods-eye-view) to .833 (Codexa). One small repository has no positive stale facts, so recall/F1 are undefined there. Codexa+httpx supply69.9% of observations. Scripts and dependencies supply only137 observations each; repeated subjects/horizons are correlated. Pooling without repository-level uncertainty inflates apparent sample size.

TTL here is measured in commits. It is not equivalent to Copilot's documented inactivity-based 28-day timer that can reset after validation/use. A wall-clock TTL with reset semantics must be evaluated separately. [GitHub documentation](https://docs.github.com/en/copilot/concepts/agents/copilot-memory).

### Local verification executed during this assessment

Ran existing tests for memory anchors, synthetic history replay, annotation policies, experience memory, graph-aware context handling, trust-boundary filtering, and graph-state witness behavior:

```text
CODEXA_DATABASE_URL='' python -m pytest -q tests/test_memory_anchors.py tests/test_anchor_replay.py tests/test_annotation_policy.py tests/test_experience_memory.py tests/test_context_window.py tests/test_trust_boundary.py tests/test_graph_state_witness.py
90 passed, 1 warning in 16.63s
```

Environment assignment above is descriptive; Windows invocation set the process environment before running pytest. Warning: Starlette/httpx deprecation. Tests used existing isolation fixtures and synthetic/fake inputs. No provider requests were started. Full suite was not run; no claim of 823 tests or a current full-suite pass is made.

### Controls, leakage, and uncertainty still missing

Independent structural/semantic ground truth; real naturally authored memory; held-out repositories; full SHA/source/environment manifests; per-repository clustered intervals; parser truncation/unknown reporting; realistic grep+range-reading baselines; actual matched budgets; independently graded task outcomes; indexing/annotation/verification cost; complete failed/cancelled attempt accounting.

Annotation `oracle` explicitly uses future edits and is only an upper bound. Production policies should use past information only. Historical PR gold patches/tests must stay hidden from agents, memory extraction, repair, and prompts. “Done” cannot be used as the task-success label.

## 4. Related-work matrix

Primary sources checked online on 7 October 2026. Full-text methods/results/limitations inspected for closest anchor/context competitors and major context-management comparisons. Preprint status below means publication acceptance was not independently established; an arXiv DOI is not a conference acceptance.

| Work, authors, year, verified source/status | Method/evaluation and relevant finding | Precise overlap, difference, and implication |
|---|---|---|
| [RepoGraph: Enhancing AI Software Engineering with Repository-level Code Graph](https://arxiv.org/html/2410.14684v2), Siru Ouyang et al., 2025; ICLR2025 indicated by primary paper record. | Repository graph plugged into four SWE systems, SWE-bench and CrossCodeEval evaluation. | Graph-assisted repository navigation predates Codexa. Codexa adds persistent memory/lifecycle integration, whose incremental benefit is unmeasured. |
| [CodexGraph: Bridging Large Language Models and Code Repositories via Code Graph Databases](https://aclanthology.org/2025.naacl-long.7/), Xiangyan Liu et al., 2025; NAACL long paper. | LLM agents query repository graph databases for repository-scale tasks. | Graph tool interfaces and structured retrieval are established. Using another storage/API layout is not a new method. |
| [LocAgent: Graph-Guided LLM Agents for Code Localization](https://aclanthology.org/2025.acl-long.426/), Zhaoling Chen et al., 2025; ACL long paper, DOI10.18653/v1/2025.acl-long.426. | Heterogeneous code graph, multi-hop localization, downstream repair evaluation. | Strong localization/impact baseline. Codexa has neither comparable localization grading nor repair evidence. |
| [Codebase-Memory: Tree-Sitter-Based Knowledge Graphs for LLM Code Exploration via MCP](https://arxiv.org/html/2603.27277v1), Martin Vogel et al., 2026; preprint. | 66-language parser/tool system; Claude Opus4.6 graph-versus-explorer study across31 repositories/languages, author-graded responses; reports83% versus92% quality with10× fewer tokens. | Very close retrieval system. Demonstrates why Codexa's payload ratio cannot replace quality/cost comparison. Its subjective grading is a limitation to improve on, not a reason to omit it. |
| [Cognitive Architectures for Language Agents](https://arxiv.org/abs/2309.02427), Theodore R. Sumers, Shunyu Yao, Karthik Narasimhan, Thomas L. Griffiths, 2024; TMLR camera-ready version. | Framework organizing memory, actions, decision-making; not a code-memory freshness experiment. | Memory taxonomy is established conceptual architecture. Four named stores provide no independent novelty. |
| [Zep: A Temporal Knowledge Graph Architecture for Agent Memory](https://arxiv.org/abs/2501.13956), Preston Rasmussen et al., 2025; preprint. | Temporal graph memory evaluated on DMR and LongMemEval. | Historical validity/provenance already exist in memory literature. Codexa's code-state anchoring differs in domain, but full bitemporal reconstruction is not implemented. |
| [EA-Graph: Artifact-Anchored Verification Memory for Coding Agents under Upstream Drift](https://arxiv.org/html/2608.04278v1), Hwai-Jung Hsu, Cheng-Jan Chi, Hanna Everett, 2026; preprint. | Artifact/subpath anchoring; affected/unprovable classification on generated worlds,42 sessions, two model tiers. Smaller-model comparisons significant; stronger-model controls show ceilings. | Directly preempts artifact-anchored verification-memory novelty. Codexa could test natural histories and downstream work rather than only synthetic provability. Those differences have not been evaluated. |
| [Executable Code Knowledge: Code as a Native, Validation-Carrying Knowledge Representation for AI Coding Agents](https://arxiv.org/html/2608.16295v1), Xueping Gao, 2026; preprint, record says submitted to AgenticDev2026. | Source-bound authored knowledge/evidence units; three Python repos,26 controlled patches; independent changed-line labels and AST fingerprint tests. | Source binding, executable evidence, fingerprints, freshness are prior art. Codexa's automatically extracted facts and general memory store differ, without demonstrated advantage. |
| [Impact Is Not Invalidation: Ask About the Claim, Not the Diff](https://arxiv.org/html/2609.25130v1), Atul Anand, 2026; preprint. | Execution-grounded claim flips across23 Python libraries;10,369 claims,184 flips; compares content/symbol impact, testmon, diff-level and claim-level LLM judgments with held-out controls. | Closest invalidation experiment. Shows changed support is not false claim. Codexa needs exact-claim routing, independent labels and natural-base-rate evaluation; implementation alone adds little novelty. |
| [Context Rot in AI-Assisted Software Development: Repurposing Documentation Consistency for AI Configuration Artifacts](https://arxiv.org/html/2606.09090v1), Christoph Treude, Sebastian Baltes, 2026; preprint. | DOCER applied to356 repositories; reports23.0% with stale references; broader documentation-consistency roadmap. | Preempts discovery that context files rot. Controlled harm, claim-class effects and prevention cost remain distinct candidate questions, subject to further literature checks. |
| [On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents](https://arxiv.org/html/2601.20404v2), Jai Lal Lulla et al., 2026; preprint. | With/without files,10 repos and124 PR tasks; runtime/token comparison. | Presence and efficiency already studied. Hold presence, relevance and length fixed while altering correctness to isolate stale-memory harm. |
| [Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?](https://arxiv.org/html/2602.11988v3), Thibaud Gloaguen et al., 2026; preprint status verified via arXiv, acceptance not established here. | CTXbench138 tasks/12 repos plus SWE-bench; multiple agents/settings; context files generally fail to improve success and raise inference cost. | Strong counterevidence to assuming memory helps. Reuse executable tasks after checking license and hidden-test validity; accurate-versus-stale treatment is different from file presence. |
| [The Complexity Trap: Simple Observation Masking Is as Efficient as LLM Summarization for Agent Context Management](https://arxiv.org/html/2508.21433v2), Tobias Lindenbauer, Igor Slinko, Ludwig Felder, Egor Bogomolov, Yaroslav Zharov, 2025; DL4Code/NeurIPS workshop confirmed by [author repository](https://github.com/JetBrains-Research/the-complexity-trap). | SWE-agent/SWE-bench Verified comparison across model configurations; simple masking competitive with summarization at lower cost. | Mandatory simple baseline for Codexa's context grace policy. Existing code-level tests do not establish an advantage over recency masking. |
| [ContextWeaver: Selective and Dependency-Structured Memory Construction for LLM Agents](https://arxiv.org/html/2604.23069v1), Yating Wu et al., 2026; preprint. | Graph of interaction-step dependencies, summaries and execution feedback; SWE-bench evaluations and topology ablations. | Dependency-aware context selection is already studied. Codexa uses static repository distance rather than inferred trajectory dependencies; compare at equal budget before claiming value. |
| [SWE-Pruner: Self-Adaptive Context Pruning for Coding Agents](https://arxiv.org/html/2601.16746v4), Yuhang Wang et al., 2026; preprint status established here. | Task-guided0.6B neural line skimmer; code-agent and long-context evaluations. | Stronger pruning comparison if pursuing efficiency. Codexa's heuristic is simpler/no training, but a cost/quality advantage is hypothetical. |
| [Aider repository map](https://aider.chat/docs/repomap.html), Paul Gauthier/Aider; maintained software documentation, not peer-reviewed paper. | Budgeted code maps ranked with graph information/PageRank, dynamically sized. | Direct prior implementation for budgeted structural selection. Codexa's annotation-selection evaluation must show value beyond mapping/ranking existing symbols. |
| [A Safe, Efficient Regression Test Selection Technique](https://www.cs.purdue.edu/homes/xyzhang/spring07/Papers/p173-rothermel.pdf), Gregg Rothermel, Mary Jean Harrold, 1997; ACM TOSEM6(2),173–210. | Conditional safety argument for changed-code-based test selection. | Invalidation based on dependencies has classical foundations. Safe selection of potentially affected evidence is not exact truth invalidation. |
| [Build Systems à la Carte](https://simon.peytonjones.org/assets/pdfs/build-systems-original.pdf), Andrey Mokhov, Neil Mitchell, Simon Peyton Jones, 2018; PACMPL/ICFP, DOI10.1145/3236774. | Scheduling/rebuilding abstractions and traces for incremental build systems. | Hash/query checks are related to incremental recomputation. Do not frame query-result cache invalidation as a new general theory. |

Additional practical competitor: [AnchorDB](https://github.com/jolovicdev/anchor-db) already offers file/span/symbol-pinned notes and relocation/staleness workflows. This is author-maintained software evidence, not a scientifically evaluated benefit. [Copilot Memory documentation](https://docs.github.com/en/copilot/concepts/agents/copilot-memory) establishes cited repository facts, validation and inactivity expiry as a deployed comparison; an emulated citation-checking baseline must not be called an exact reproduction of proprietary internals.

Literature limitations: competing studies' raw results were not independently reproduced. Full-text availability does not establish their claims as universal facts. Search focused on code graphs, stale memory, context files, claim invalidation and pruning; it is not an exhaustive review of all agent research. New work may narrow the proposed gap. A failure to find an identical system is not evidence of novelty.

## 5. Novelty assessment

| Candidate claim | Implementation / closest prior | Actual difference and scientific significance | Evidence / confidence / likely objection |
|---|---|---|---|
| “Repository graphs reduce agent cost.” | Parser/query tools and payload experiment; RepoGraph, CodexGraph, LocAgent, Codebase-Memory. | Established idea. Efficient integration is useful but not itself novel. | Payload arithmetic only; high confidence in low novelty. Reviewer: unfair file baseline, missing quality and amortized costs. |
| “Persistent cognitive memory improves coding.” | Typed store plus experience hooks; CoALA/Zep and existing agent memory systems. | New implementation/testbed, not evidence of improvement. | Synthetic mechanics tests; high confidence claim is unsupported. Reviewer: no chronological task study or task quality. |
| “Anchors detect when code memory is false.” | Anchors/sweeps; EA-Graph/ECK/Anand. | Support-change detector with exact query subset. Conditional truth checking for selected claim classes could matter. | Current general formulation overclaims; high confidence in overlap, medium in potential incremental method. Reviewer: freshness ≠ truth; shared oracle; missing coverage. |
| “Claim-specific validation preserves useful memory under drift.” | Query hash and episodic/descriptive split; routing/cascade only proposed. | Potential practical contribution: cost/coverage tradeoff across real claim classes, measured at use time. | Replay gives motivation, not validation. Medium confidence candidate; depends on independent truth labels and strong claim-judge baseline. |
| “Stale memory causes avoidable agent errors/cost.” | Replay/store/jobs support experiment construction; Context Rot and context-file studies are closest. | Holding file presence fixed while changing historically grounded accuracy isolates harm and repair. Could be meaningful empirical contribution even without a new algorithm. | No current harm experiment. Medium confidence direction, low confidence effect exists/generalizes. Reviewer: unrealistic rot, irrelevant claims, contamination, small effective n. |
| “Graph distance improves observation retention.” | Two-hop reverse dependency neighborhood and3× grace (`context_window.py`); Complexity Trap/ContextWeaver/SWE-Pruner. | Cheap static relevance proxy rather than trace graph/neural compression. | Unit tests only; low-to-medium novelty, plausible workshop result after ablations. Reviewer: latest-read focus/noisy graph, extra memory budget explains gain. |
| “Budgeted gloss allocation outperforms existing maps.” | Annotation policies and future-edit replay; Aider/PageRank/classical ranking. | Separately optimizing paid gloss allocation is a possible empirical comparison. | No consistent winning policy or actual query-quality result; low confidence full-paper direction. Reviewer: edit proxy does not measure demand. |

Rejected now: first graph-based coding agent, novel memory taxonomy, semantic soundness from hashes,85.8× real-agent savings, universally safe autonomous execution, deployed Docker digital twin, operational multi-store consistency, learned confidence/economics, guaranteed hallucination prevention, or state of the art.

Earlier `strong_paper_design.md:251` writes proposed results as present-tense contributions, including “first” and dominance claims. Treat all those as hypotheses. Its “prevalence always publishable” and “significance on any primary metric” gates (`:289`) are not defensible acceptance criteria: relevance, novelty, validity and statistical planning still matter.

## 6. Ranked paper directions

All four are conditional directions, not four ready submissions. Ranking balances defensibility, significance, feasibility and work already present.

### Rank 1 — Stale Context, Real Consequences: Measuring and Preventing Memory Drift in Coding Agents

**RQ:** How does historically grounded, task-relevant stale context affect successful coding, recovery effort and actions, and can selective checks reduce its cost?

**Contribution/hypothesis:** paired harm benchmark plus claim-class failure analysis; optional small prevention method. Hypothesis: relevant stale paths/commands/interfaces increase wrong actions and effort; checking those claims recovers some loss while retaining valid context.

**Reuse:** anchors, git snapshots, context/memory hooks, tool telemetry, existing structural replay as a secondary detector sanity set. Current logs supply failure hypotheses only.

**Changes/experiments:** independent typed-claim labels; real historical context/task instances; equalized treatment injection; executable outcome grader; fixed external harness plus Codexa replication; accurate/stale/checked/no-context treatments. Add file-hash, selective deterministic, per-claim LLM and citation-verification comparisons. Ablate claim classes, granularity and episode handling.

**Data/metrics/statistics:** CTXbench or license-cleared historical PR tasks, relevant naturally outdated claims, hidden tests. Resolve rate, wrong stale-induced actions, recovery calls/time, total tokens and billed cost. Paired seeds; repository/task clustered bootstrap; paired success analysis with clustered sensitivity checks. Pilot20 tasks/5 repos×4conditions×1model×2repeats=160runs. This is feasibility/effect-size evidence, not adequately powered proof of small resolution gains. Scale from pilot uncertainty, not an arbitrary target n.

**Effort/cost:** planning estimate2–4weeks for measurement foundation and pilot setup, excluding model runs/manual labeling; fuller study likely longer. Main driver is160 agent runs, not anchor checking. At a hypothetical50k total tokens/run, pilot needs8M tokens before judge/extraction overhead; this is a scenario, not a price quote or budget authorization.

**Threats/reviewers:** scope matches existing context-file literature; task irrelevance, synthetic contamination, model/harness/provider confounds, test inadequacy and weak small-sample power. Controlled historical rot supports causality only for sampled treatments; observational prevalence is a separate question.

**Track:** short empirical/workshop first if pilot is sound; full SE empirical research only after representative, adequately powered held-out evaluation. Highest scientific value of these directions, with expensive downstream evidence still missing.

### Rank 2 — From Changed Support to Changed Facts: Evaluating Typed Freshness Checks for Repository Memory

**RQ:** Which claim classes can be revalidated cheaply and reliably without discarding true memory?

**Contribution/hypothesis:** reproducible typed drift dataset plus selective-check cost/coverage study. Exact path/manifest/query checks should reduce unnecessary invalidation compared with file hashes for their supported classes; residual prose should remain unknown or be sent to a claim judge.

**Reuse:** five-repo144-pair replay and confusion counts; query hashes; soft invalidation. **Required:** independent structural labels, parser coverage reporting, explicit unknown state, natural prose claims, signature/manifest-specific validators and optional judge cascade. Baselines: never/all invalidate, file/symbol/closure anchors, wall-time TTL, DOCER for applicable references, Anand-style claim judge; testmon for executable claims where comparable. No single baseline covers every class.

**Evaluation:** stratified double-label300 claims initially; diverse held-out histories, class-specific precision/recall/coverage, false withdrawal/stale delivery, CPU and judge cost. Bootstrap repositories/commit groups; no fact-level iid assumption. Deterministic cells need sampling uncertainty, not repeated identical runs. Judge arms need repeated calls and fixed settings.

**Effort/cost:** estimate1–3weeks measurement/tool packaging plus human labels; CPU replay mostly cheap, judge comparisons cause API expense. **Objection:** much of method is cache invalidation and prior anchoring. Best framed as narrow empirical/replication or artifact/short paper, not a new semantic-verification theory. Cheapest scientifically credible fallback if rank1 harm is absent.

### Rank 3 — Keeping the Right Observations: Repository-Distance Context Retention for Coding Agents

**RQ:** Does static graph proximity retain observations useful later at equal token budgets?

**Hypothesis:** graph distance improves quality/cost on tasks requiring revisits, compared with fixed recency; may harm localized tasks or parser-blind dependencies. **Reuse:** `context_window.py`, jobs compaction, tests. **Required:** switchable policy, reliable focus selection, full token instrumentation, budget equalization and external harness adapter.

**Baselines/ablations/data:** raw history, fixed masking, token-budget recency, LLM summary, Complexity Trap hybrid, ContextWeaver where feasible; graph radius0/1/2, direction, edge types, no-graph and random-retention controls. SWE-bench Verified stratified pilot50tasks,2models,3repeats; no new training required. Primary metric tokens at prespecified resolution non-inferiority margin, plus rereads, latency and graph construction cost. Paired clustered intervals and treatment-by-task-type analysis.

**Effort/cost:** estimate2–4weeks integration; many long agent runs. Current3× grace is extra budget and must not be allowed to explain the result. Main reviewer objection: established masking works; graph imprecision and most-recent-file heuristic may add complexity without benefit. Workshop/short paper plausible; full paper needs a clear robust gain and more than one harness.

### Rank 4 — Which Symbols Deserve a Gloss? Annotation Allocation Under an LLM Budget

**RQ:** Which selection policy maximizes downstream useful annotation coverage per real cost?

**Hypothesis:** task-conditioned/lazy allocation beats static popularity for some task distributions; no universal winner assumed. **Reuse:** configurable eight policies and26saved base snapshots. **Required:** real QA/localization demand; held-out repositories/tasks; independently judged gloss accuracy; actual token/latency and cache-cost measurement.

**Baselines:** random, parser order, callers, exact callers, PageRank/Aider-style map, degree, past churn, lazy; future oracle only an upper bound. Ablate budget and cache lifetime. Begin with200held-out questions/≥10repos; deterministic ranking plus repeated annotation/answer seeds when stochastic. Report macro repository coverage, successful answers, annotation errors, latency, amortized cost, and clustered intervals. Avoid training until simple policies justify it.

**Effort/cost:** estimate1–3weeks to produce real demand/grading plus limited annotation calls; downstream QA still incurs expense. Existing evidence is mixed and proxy-based. Main objection: known ranking, no distinctive method or agent benefit. Lowest priority; a carefully scoped negative/replication short paper is more credible than a flagship contribution.

## 7. Recommended roadmap and reproducible evaluation

**Recommendation:** rank1 as scientific destination; rank2 foundations first. Work within repository-memory subsystem, with separately scoped harness evaluation. Do not expand projections, learning, dashboards, cloud/design integrations or every subsystem to make a larger paper. The older3–5k-repository/multi-study plan is a later extension, not the minimum coherent contribution.

### Proposed modifications, in order

| Priority/change | Limitation/RQ and components | Experiment/success criterion | Meaning of negative result |
|---|---|---|---|
| Essential: freeze evaluated artifact and dataset manifest | Current uncommitted source/results; `pyproject.toml`, replay/annotation runners. Pin full repo SHAs/URLs, dirty source snapshot hash, parser/package versions, filters, seeds and configs. | Clean offline replay reproduces saved confusion counts where same inputs exist; declare unavailable snapshots and all exclusions. | Existing tables remain unauditable historical outputs until provenance is restored. |
| Essential: report incomplete analysis | Silent caps/parse failures; `repository/analyze.py`, replay snapshots. Proposed configurable caps plus completeness/unknown metadata. | Independent fixture tests for caps/errors; full-cap versus uncapped sensitivity audit. Never score dropped subject as false solely due parser omission. | Restrict language/repo/claim domain and report coverage, rather than claim general soundness. |
| Essential: separate support drift from false claim | General prose deletion on hash changes; `memory/anchors.py`, `store.py`, `context.py`. Proposed typed validators and statuses verified-valid / verified-false / needs-revalidation. Keep history distinct. | Independent labels; high precision for false verdicts, coverage and uncertainty by class. Pilot target≥.95 point precision on supported classes, with intervals, not a universal guarantee. | Changed-support detection remains a triage tool; automatic withdrawal is unjustified for residual claims. |
| Essential: verify represented facts independently | Shared graph/label oracle; `anchoring_facts.py`, `QueryIndex`, `analyze.py`. Manual references and independent parser/index where available. | Stratified300double-coded claims including positives/negatives/unknowns; agreement and adjudication; per-class error taxonomy. | Perfect self-consistency is not an external correctness result; parser corrections or narrower claims needed. |
| Essential: task/treatment/grader pipeline | No harm/repair experiment. Proposed evaluation adapter beside existing benchmark code, not application frontend. | Baseline tests pass at base, hidden tests distinguish known correct/incorrect patches; historically accurate/stale/checked/no-context payloads confirmed in traces. Equalize relevance and length; include harmless edits/placebo controls. | No causal harm inference if task relevance or manipulation failed; publish exclusions without fishing for successful examples. |
| Essential: complete trial accounting | Fallback/partial-attempt usage omissions; `llm.py`, `jobs.py`, `usage.py`, `round_telemetry.py`, evaluation runner. | Capture attempt/request/model revision, configs, elapsed time, observed usage vs estimates/unknown, budgets, termination, output patch and executable grade. Disable model fallback in efficacy comparison or report it as separate treatment. | Cannot claim cost superiority from partial token totals. Unknown costs remain explicitly unknown. |
| Valuable: use-time checks and batch indexing | Parse-requiring anchors checked mainly at ingestion; context/semantic retrieval. | Same snapshots with reload versus live edits; stale delivery rate/latency, revalidation cost included. | Checker accuracy does not translate into user-visible freshness. |
| Valuable: claim-judge cascade | Descriptive claims cannot be decided by local hashes. Anchors as triage, not verdict. | Compare judge-all versus selective judge at matched evidence/settings; plot quality/coverage versus real cost, include unsupported/unresolved rate. | Cascade adds no useful frontier point; publish simpler deterministic subset and retain judge baseline. |
| Valuable: second harness/model and natural memory | Codexa-specific context injection; experience hooks. | Replicate key comparisons externally; chronological memory written before later tasks. | Report effect as harness/model/domain-specific. |
| Optional: longitudinal prevalence and observational PR outcomes | Generalization of rank1; extend replay to real context-file claim histories. | Stratified history sample with human precision audit; time-to-first-false and time-to-repair with censoring. | Descriptive association, not causal agent harm. Defer thousands of repos and survival models until labeled pilot justifies them. |

### Pilot protocol

Predeclare a primary contrast: accurate versus stale, on a fixed primary outcome. Resolve rate is quality endpoint; total tokens/time and stale-induced actions are prespecified secondary endpoints. A small pilot estimates feasibility, variance and effect size; do not search several outcomes for any p<.05 and call that success.

Use20tasks across5repositories, balanced historical rot types, four conditions and two repeats for one fixed model/harness. Conditions: no context; accurate context; historically stale context; same stale context after selective validation. Keep agent instructions, tools, task, repository base, budgets and relevant information equivalent. Also check length-matched harmless perturbations on a smaller validation subset to distinguish staleness from editing/context-length effects.

Treat absent/unknown/outdated memory differently. Positive context must be validated at the task base; not silently assume today's file is correct. Keep gold PR commits, repaired hidden tests and future history outside agent visibility. Archive received prompt/context hashes so treatment availability is observable. Randomize run order to limit provider/time effects. Reset repository, browser and memory for every independent arm; intentionally shared memories belong only in chronological-memory experiments.

Every attempt counts, including timeout, provider error, no answer and incorrect patch. Only predetermined infrastructure/wiring failures are separately excluded, with counts and reason. Never retry until success or use model-declared completion as ground truth. Fixed round/time/token budgets apply to all arms.

Use executable grading of patch outcomes plus manually audited trace labels: stale command execution, nonexistent path access, obsolete symbol use, wrong edit and recovery. Measure information usefulness as well as false withdrawal: dropping everything can remove stale memory while destroying assistance.

### Scaling, statistics, and cost

Estimate effect and discordant-pair frequencies from pilot, then perform power/simulation planning for the minimum practically important effect before a held-out confirmatory run. More seeds do not replace more repositories. Bootstrap repository/task clusters; report macro repository and micro task effects, intervals and per-model strata. Use McNemar only with suitable independent task units and clustered sensitivity checks. Predeclare non-inferiority margins for efficiency claims; a nonsignificant success difference does not prove equal quality. Account for multiple secondary analyses.

A prospective40tasks×4conditions×2models×3repeats requires960runs; at hypothetical50k total tokens/run,48M tokens. This is an illustrative expansion, not a recommendation to execute without budget. Actual input/output/cache/judge prices, local GPU memory/runtime, and provider limitations determine cost. Obtain budget and compute authority before any such run. CPU graph replay and manual labels can proceed separately once modifications are approved.

Existing tests gate implementation mechanics. They cannot supply effect sizes or uncertainty for research hypotheses. Add tests only for measurement invariants and new functionality; independently verify experimental labels. Negative harm/prevention outcomes can support a bounded robustness or tradeoff finding if the study is adequately powered, not a claim that memory is universally harmless.

## 8. Publication track and paper outline

Most appropriate immediate framing: short empirical or work-in-progress contribution after independent validation; fuller empirical SE contribution if controlled harm and/or prevention results survive held-out evaluation. Demo is plausible for integrated graph/memory inspection after a reliable public artifact and reproducible walkthrough; it does not validate a method claim.

One concrete venue checked: [MSR2027 technical track](https://2027.msrconf.org/track/msr-2027-technical-papers) explicitly accepts scientifically evaluated new techniques/results and well-motivated replication; lists full10+2reference pages and short work-in-progress4+1. The published page also contains inherited2026submission links, so reconfirm final instructions/portal with organizers before submission. No deadline is assumed or recommended here. Other track types above are generic recommendations, not verified current CFPs.

Proposed paper outline:

1. **Problem and bounded contribution:** current-code assertions versus historical episodes; importance of stale context, existing prior methods. No “first” claim.
2. **Background/related work:** graphs and retrieval, documentation drift, anchored evidence and claim-relative invalidation.
3. **Artifact and claim model:** implemented parser/store/checker domain and unknown coverage. Figure1: ingest→claim support→use-time validation→agent→independent grader.
4. **Dataset/measurement:** repository/task sampling, historical rot, split/annotation protocol and graders. Table1: repos, languages, task/claim counts, positive base rates and exclusions.
5. **Detector study:** independent per-class validity/cost; existing replay as secondary self-consistency benchmark. Figure2: per-class precision/recall/coverage and false-withdrawal tradeoff. Existing tables are reusable only with provenance/cap caveats.
6. **Controlled harm and prevention:** accurate/stale/checked/no-context outcomes. Table2: paired quality, effort, failure and unknown-cost counts; Figure3: effect sizes/intervals by class. All these results remain unperformed.
7. **Mechanisms and failures:** traces plus representative counterexamples; separate generalization from case evidence. Table3: stale-induced actions/recovery and parser/judge errors.
8. **Threats/artifact availability:** incomplete parsing, sampling dependence, model versions, leakage, cost measurement, labels, licensing and replication.
9. **Conclusion:** only empirically supported scope; no invented successful results or premature abstract.

For a short paper, retain claim model plus one independently validated experiment; drop sprawling prevalence/observational/learning studies. A full paper must add enough evidence to substantiate its central claim, not additional product features.

## 9. Claim–evidence matrix

| Proposed paper statement | Code / saved evidence | Relevant prior | Remaining gap / permitted wording now |
|---|---|---|---|
| Codexa extracts a structural graph for four language forms. | `repository/analyze.py`; repository tests. | RepoGraph/LocAgent/Codebase-Memory. | Observed implementation, not complete call graph. Report caps and unresolved cases. |
| Typed records can be selectively invalidated or marked outdated. | `anchors.py`, `store.py`, `context.py`;90test local subset. | EA-Graph/ECK/Zep. | Mechanism established; record-type semantics do not establish arbitrary statement truth. |
| Granularity changes consistency-detection tradeoffs. | Five JSON replay results; recomputed A2/A3/A5 confusion counts. | Anand/EA-Graph; classical incremental checks. | Say “on parser-defined facts in sampled snapshots”; independent labels and clustered uncertainty missing. |
| Query hashes detect extracted query-result changes. | `QueryIndex`, `query_anchor`; F2–F4 replay and synthetic tests. | Query/cache invalidation, incremental computation. | Conditional construction property, not independent research accuracy or new theory. |
| Graph payloads were smaller than selected whole files. | Five payload JSONs,174symbols,85.8146ratio. | Codebase-Memory. | Payload accounting only; no equal-quality agent cost claim. |
| Stale relevant context harms coding agents. | No completed controlled result. Harness/replay provide infrastructure. | Context Rot, Lulla, Gloaguen. | Hypothesis only; need historic treatments, executable graders and paired runs. |
| Selective checks recover quality at lower cost than judge-all. | Routing/cascade largely absent. Existing anchors enable prototype. | Anand/ECK/Copilot validation. | Hypothesis only; detection frontier plus downstream recovery needed. |
| Static-distance retention improves quality/cost. | `context_window.py`, compaction tests. No efficacy result. | Complexity Trap/ContextWeaver/SWE-Pruner. | Hypothesis only; equal-budget baseline and downstream ablations required. |
| Annotation priorities improve useful coverage. | Annotation-policy source and future-edit results. | Aider/PageRank. | Evidence concerns edit proxy and mixed winners; actual demand/quality missing. |
| Execution always uses current simulation approval. | Separate simulation/scheduling API tests; witness hash. | Standard optimistic concurrency/change-impact gating. | Not permitted: main executor bypasses gate and node-only witness omits edge changes. |

## 10. Questions that materially affect next phase

These do not block this assessment; no model/compute spending is authorized by their inclusion.

1. May code, selected repository histories, tasks and labeled claims be released for artifact review? README currently says proprietary/internal use. Which benchmark repositories/results have redistribution permission?
2. What fixed token/compute budget and model access can support a 160-run pilot? Can an immutable open-weight model and isolated task environments be provided?
3. Is target a near-term short/demo paper or a longer full empirical study, and are two independent annotators available? This changes scale and timeline more than adding features.
4. Are later raw results and `scratchpad/bench_matrix.py` available outside this repository? They could upgrade the documentation-only campaign to auditable evidence; current recommendation does not assume they exist.

## Appendix: inspection and search record

**Repository instructions:** user instructions, root `AGENTS.md`, authoritative v5spec completely read. Existing caveman/cavecrew skills governed concise communication and parallel evidence gathering. Implementation paused when the latest user request required an initial read-only assessment.

**State/history:** inventory of first-party backend, frontend graph components, infrastructure, documentation, benchmark scripts, tests and saved output; `git status`, current branch/HEAD, recent model/runtime/documentation commits. Existing dirty tracked files: jobs/tools/memory context/store/repository api/semantic; new anchors/experience/annotation policies/tests/research results already present. Preserved throughout.

**Code inspected:** representative implementation paths across perception/trust, repository parser/ingestion/annotations, graph schema/storage/events/snapshot/consistency/causal/data-flow, memory store/conflicts/context/anchors/experience/services, agent planning/impact/retrieval/verification/tool loop/browser/receipts/context/telemetry/LLM routing, simulation/witness/chaos/execution gate, confidence/economics/health/incident/policy/learning/nightly services, and graph/Strata visualization data/layout/interaction. This is a systematic targeted audit; it is not a claim that every source line was executed or every UI flow manually tested. Generated/vendor directories skipped. No relevant first-party notebook dataset was identified beyond the benchmark scripts/JSONs.

**Documents/evidence inspected:** README/dependencies; earlier architecture/claims/audit/incident records; token-reduction proof and token campaign report; research plans/gap/novelty/memory-rot design; anchoring methodology/results; five anchor JSONs/four annotation JSONs/five payload JSONs;12original and70Solar run summaries; relevant synthetic tests and saved in-scope feature-audit evidence. Mixed documents were used only for in-scope material. Old conclusions were not adopted without code/artifact checks.

**Recomputations:** read-only JSON aggregation of TP/FP/FN/TN; pooled metrics; repository pair counts; payload token/symbol totals; Solar run/status/output coverage. No saved result files overwritten or original campaigns rerun.

**Search terms/mechanisms:** “Impact Is Not Invalidation,” “Context Rot Treude Baltes,” “coding agent memory stale code anchors EA-Graph ECK,” repository graph/RepoGraph/CodexGraph/LocAgent, observation masking/Complexity Trap, AGENTS.md presence/quality, code memory claim/cascade/invalidation, dependency context eviction, PageRank budgeted repository maps, safe regression test selection, incremental build traces, and MSRtechnical track.

**Citation traversal:** followed Anand's EA-Graph/change-impact foundations, Context Rot's documentation-consistency references, Codebase-Memory's graph/mapping comparisons, and context-management paper links to author code. Verified primary full texts/metadata via arXiv/ACL, classical papers via author/university PDFs, software baselines via official docs/repos, venue via official track page. Supplemental ContextWeaver/SWE-Pruner/PlaceMem searches checked broader overlap; only supported relevant details enter claims. No source search failure is treated as novelty proof.

**Limits:** no new model evaluation; no live container/Postgres/projection deployment verification; no reproduction of external papers; no current full-suite run; no manually double-labeled corpus; incomplete provenance for uncommitted experiments and missing later campaign harness. Existing evidence remains useful when these limits are stated plainly.
