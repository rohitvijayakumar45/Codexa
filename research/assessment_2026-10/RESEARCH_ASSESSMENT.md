# Codexa OS — Research Potential Assessment

> **Update (2026-10-07):** Direction 1 has been executed. The study, results and paper draft are in `research/navbench/` (`paper/paper_draft.md`, `results/main/analysis/report.md`). Several pilot numbers below were superseded.


Date: 2026-10-07. Scope: whole repository at commit `0ea016a`, plus a lightweight local re-measurement
(no paid API calls, no training). "Quorum mode" is excluded throughout by instruction; it is not
analysed, compared, or proposed.

Labels used below:
- **[OBS]** observed fact, checked directly in code or saved artifacts.
- **[DOC]** stated in repository documentation, not independently verifiable from saved artifacts.
- **[RAN]** test or measurement executed during this investigation.
- **[INT]** interpretation.
- **[PROP]** proposed work, not done.

---

## 1. Executive verdict

**Current paper potential: low as the project stands. A credible workshop or short paper is
realistic after about 2–4 weeks of focused measurement work.** Do not frame the paper around the
system architecture or the "85.8× fewer tokens" headline.

- **The headline claim does not hold up as stated.** The 85.8× (98.8%) reduction compares a graph
  lookup with reading *whole files*, on symbols sampled from the graph's own edges, without checking
  correctness. In a 3-repo pilot, a plain `grep -rnw` arm gave much smaller median ratios than the
  whole-file arm [RAN, pilot]. The pilot's recall figures are affected by selection bias, oracle bias
  (jedi) and task-definition bias (references vs. call sites). Neither the magnitude nor the direction
  of a corrected effect is established (see §3.3 and `PROTOCOL.md`).
- **The same idea is already published.** A Tree-sitter knowledge graph exposed to agents through
  tools, with claims of ~10× fewer tokens, is covered by Codebase-Memory (Vogel et al., 2026). That
  paper reports 83% vs 92% answer quality against an agent using file reading *and grep*, i.e. the
  graph loses some quality. Xu (2026) measured LSP (language-server) vs grep token use, including
  reference completeness against pyright, and found the answer is "conditional and usually negative".
  RepoGraph, CodexGraph and LocAgent are all peer-reviewed. "Code Isn't Memory" (2026) and ARISE (2026)
  add structural indexes inside agents.
- **Strongest defensible contribution (recommended direction):** a measurement study of how
  baseline choice, query sampling and reference completeness affect the measured token efficiency of
  repository-navigation tools (grep, language server, two Tree-sitter graphs), under equivalent output
  contracts. The result direction is open; see `PROTOCOL.md`. The repo already has most of the machinery. The study needs little or no
  API spend, and the field currently has many unverified "99% fewer tokens" tool claims.
- **Largest evidence gap:** no saved experiment measures *answer correctness*. In the agentic
  runs, the recorded `answer` is a mid-trajectory sentence, not the final answer. Many "done" runs have
  empty answers. All token comparisons are therefore unanchored to quality.

---

## 2. Repository findings

### 2.1 Problem and intended users
Codexa is an LLM coding agent and "engineering intelligence" workspace for developers working on a
repository. It ingests the repo into a structural graph, adds persistent project memory, and runs a
tool-calling agent loop over it, with a 3D/strata visualisation frontend [OBS: `README.md`,
`backend/`, `graph-viz/`]. In practice, most logged agent work was single-file HTML generation and
code-navigation Q&A on small personal repos [OBS: `BENCHMARK_LOG.md`, `PROBLEMS.md §0`,
`tests/benchmarks/memory_graph/questions.json`].

### 2.2 Architecture and data flow (as implemented)
1. **Ingest:** `backend/repository/api.py:_ingest` / `reindex_repository` (`:998`) →
   `backend/repository/analyze.py`. Tree-sitter queries for Python/JS/TS/TSX extract files,
   symbols, imports and calls. Calls are resolved **by name** (within-class first, ambiguous calls left
   unresolved), capped at 12 calls per symbol and 8000 edges [OBS: `analyze.py:22-60`].
2. **Graph store:** `backend/graph/service.py` + `repository.py`. In-memory by default, Postgres
   optional. Edges carry `confidence`, `source_type` and validity intervals, which enables the time
   machine [OBS; verified by the existing audit test]. **Neo4j and Qdrant are not implemented.** They
   exist only in compose files and docs [OBS: no driver imports; also `CODEXA_CLAIMS_AND_PROOF_AUDIT.md §6`].
3. **Memory:** `backend/memory/store.py` is a JSON-file store with four typed memories.
   `memory/context.py` does keyword-overlap ranking plus a regex type bonus (+0.35), and
   name/path resolution to graph neighbours [OBS].
4. **Agent loop:** `backend/agents/jobs.py` (2.2k LOC) runs background jobs with per-round disk
   checkpoints. `controller.py` + `plan.py` + `validators.py` form a task state machine: completion is
   decided by filesystem/exit-code validators, with forced-tool interventions, per-task round,
   reasoning and intervention budgets, and non-recursive recovery tasks [OBS: `controller.py:1-92`,
   `validators.py:1-70`].
5. **Answer verification:** `backend/agents/verification.py`. An LLM extracts ≤8 positive claims
   from the final answer. Each claim is then checked deterministically against the graph
   (symbol exists / usage count), the disk (file exists) or the turn's tool log (test passed / action
   performed). The check fails *open* on errors [OBS].
6. **Context management:** stale-payload compaction in `jobs.py`. `context_window.py` extends grace
   ×3 for files within 2 reverse-dependency hops of the most recently touched file (graph-anchored
   eviction) [OBS].
7. **Simulation/execution:** `simulation/engine.py` does reverse-BFS blast radius, regex schema
   detection and a linear confidence formula. `witness.py` hashes the witnessed subgraph.
   `execution/sandbox.py` builds a `docker run` command line but **runs no container** [OBS; agrees
   with the existing audit].
8. **Trust boundary:** `perception/trust_boundary.py` uses four line-level regexes that replace
   matching lines in untrusted content [OBS].
9. **LLM routing:** `agents/llm.py` uses litellm across many free-tier providers, with key rotation
   and error-classified failover [OBS].

### 2.3 Feature status

| Feature | Status | Evidence |
|---|---|---|
| Tree-sitter structural graph (Py/JS/TS) | Implemented; name-based call resolution | `analyze.py`; [RAN] recall numbers in §3.3 |
| Graph query tools (`lookup_symbol`, `get_dependencies`, `find_references`, outline) | Implemented; outputs truncated (10–30 items) | `tools.py:1894-2400` |
| Temporal edges / time machine | Implemented | `graph/service.py:list_edges_at`; audit test |
| Postgres persistence | Implemented, optional | `graph/repository.py` |
| Neo4j / Qdrant projections, RQ | **Not implemented** | no drivers/deps |
| 4-type memory + conflict resolution | Implemented (heuristic) | `memory/*` |
| LLM symbol annotations | Implemented, cached by content hash | `repository/semantic.py` |
| Task contracts + filesystem validators | Implemented, heavily unit-tested | `task.py`, `validators.py`, `controller.py` |
| Claim verification of final answers | Implemented; LLM extraction + deterministic resolution; fails open | `verification.py` |
| Graph-anchored eviction | Implemented; **never evaluated** | `context_window.py` |
| Simulation engine | Heuristic; not a digital twin | `simulation/engine.py` |
| Docker sandbox | Command synthesis only | `execution/sandbox.py` |
| Trust boundary | Regex line stripping | `trust_boundary.py` |
| Local semantic search (embeddings) | Present (`semantic_search`); orphaned from tool groups (failing test) | `tools.py:1844`; test failure below |

### 2.4 Standard vs potentially distinctive
- **Standard:** Tree-sitter repo graphs (RepoGraph, LocAgent, CodexGraph, Codebase-Memory), BFS
  impact analysis (CodePlan-style), keyword memory retrieval, litellm failover, regex injection
  filters, round/char budgets, checkpointed job loops.
- **Possibly distinctive, all unevaluated:** (a) deterministic, graph- and disk-grounded checks of
  final-answer claims, combined with filesystem-decided task completion; (b) graph-distance-aware
  context eviction; (c) a witness hash of the dependency subgraph binding simulation to execution;
  (d) an unusually detailed engineering record of failure modes of reasoning models in agent loops
  (`PROBLEMS.md`, `AUDIT.md`, `SECOND_OPINION.md`).

### 2.5 Limitations and assumptions
- Name-based call resolution gives low recall on dynamic, attribute and imported calls (§3.3). The
  analysis is capped at 1,500 files / 4,000 symbols / 8,000 edges.
- Graph tools truncate output (`callers[:10]`, `outgoing[:20]`), so token counts are capped at the
  cost of completeness.
- Multi-provider free-tier models were the default. This adds availability noise and model drift to
  every agentic measurement (`docs/token_bench_results.md` notes dead endpoints mid-run).
- The cost claim assumes cost is linear in input tokens. This ignores prompt caching, which dominates
  agent spend (Weinberger & Hozez 2026).

### 2.6 Test suite [RAN]
I ran `python -m pytest --ignore=tests/benchmarks` in a fresh venv (Python 3.13).
Result: **1079 passed, 7 failed, 2 skipped, 1 xfailed in 36 s.**
- 5 failures in `test_delegate_build.py::TestUltraHeavyTierIsolation`, caused by stale model-registry
  expectations (e.g. `glm-5.3-free` was removed in commit `dd1af29`).
- `test_tool_groups.py::test_all_tools_covered_by_at_least_one_group`: `semantic_search` is orphaned.
- `test_intent_fidelity.py::...test_the_substitution_page_fails`.

These are **software-correctness tests**. They support the claim that the mechanisms behave as
specified. They are not research evidence of benefit.

---

## 3. Existing evaluation audit

### 3.1 Inventory

| Experiment | Question | Setup | n / reps | Status of evidence |
|---|---|---|---|---|
| E1 Retrieval payload (`tests/benchmarks/memory_graph/retrieval_payload.py`, `payload_results/*.json`) | Tokens for graph lookup vs reading files | 5 private repos, 40 symbols each (MOMENTUM 14), seed 7, tiktoken cl100k | 174 symbols, 1 deterministic run | **Verified**: JSONs match the README table. Repos not in the repo, so third parties cannot reproduce. |
| E2 Agentic GLM (`raw_runs/`) | Tokens, raw vs graph vs full | Exam-Proctoring, 4 questions, 3 modes | n=1 per cell | Verified files; anecdotal |
| E3 Agentic Solar (`raw_runs_solar/`) | Same | `upstage/solar-pro4`; modes A/B ×4 questions ×8 reps; mode C only q1 ×6 | 70 runs | Verified files; see 3.2 |
| E4 "Memory+graph vs raw" (`docs/token_bench_results.md`) | Tokens, full vs raw | `scratchpad/bench_matrix.py` (not in repo), solar-pro4 | full n=5, **raw n=1** | **[DOC] only**: harness and raw data absent |
| E5 Memory A/B (`.overnight/PROGRESS.md` round 7) | With vs without memory | GLM 5.3, 4 questions | n=1 | [DOC] only (`ab_results.json` in a scratchpad, not saved) |
| E6 2×2 reasoning cause (`scripts/experiment_2x2.py`) | Artifact vs output size as trigger of runaway reasoning | 4 arms | results not saved | Design only |
| E7 Overnight build benchmark (`BENCHMARK_LOG.md`) | Can jobs finish builds | 3 HTML products | operational log | Qualitative; no outcome metric |
| E8 Claims audit (`tests/audit/codexa_claims/`, `CODEXA_CLAIMS_AND_PROOF_AUDIT.md`) | Do features exist | unit-level probes | 31 assertions | Correctness, not benefit |

### 3.2 What the experiments actually establish
**E1 (headline).** [OBS]
- The question measured is "where is X defined and who references it". The "raw" arm reads the
  *whole* defining file plus every file the *graph* says references X. Median referencing files per
  symbol = **1** in 4 of 5 repos (FitQuest: 2). So "raw" is mostly "read one whole file", and the
  ratio mostly reflects file size (gods-eye-view files are huge → 216×).
- No arm is checked for correctness. The graph answer is the reference set by construction, so the
  comparison cannot detect missing callers.
- **Selection bias:** only symbols that already have ≥1 incoming graph edge are sampled. Symbols
  whose callers the graph missed are excluded.
- **Missing baselines:** no grep, ctags or LSP arm, although the agent's own raw toolset includes
  `search_code`.
- The dollar figure assumes linear token pricing.
- [INT] The measurement is internally consistent, but it shows that a symbol-level index is smaller
  than whole files, which is known. It does not show that Codexa's architecture reduces agent cost.

**E3 (agentic, the only replicated agentic data).** [OBS, computed from the 70 JSONs]

| Mode / question | n | done with non-empty answer | median total tokens |
|---|---|---|---|
| A raw / q1 structural | 8 | 0 | 910K |
| A raw / q2 impact | 8 | 6 | 113K |
| A raw / q3 conventions | 8 | 4 | 19K |
| A raw / q4 cross-system | 8 | 5 | 116K |
| B graph / q1 | 8 | 0 | 1.09M |
| B graph / q2 | 8 | 2 | 14K (4 runs logged 0 tokens + error) |
| B graph / q3 | 8 | 4 | 6K |
| B graph / q4 | 8 | 5 | 78K |
| C full / q1 | 6 | 2 | 237K |

Further observations from the same runs:
- **Graph tools were barely used.** In mode B, graph tools made 41 of 601 tool calls (7%). In mode C
  they made **0 of 178**: only `search_code`/`read_file` were called.
- The `answer` field is the last non-empty assistant message, and is at most 308 characters. Examples
  are mid-trajectory narration ("Now let me check where…") or a system correction message. **Final
  answers were not captured and answer quality was never graded.**
- The variance is very large: the q2 raw arm ranges from 8.5K to 284K tokens. This matches the
  ~30× run-to-run variance Bai et al. (2026) report.
- [INT] E3 cannot support "graph/memory reduces tokens". Arms differ more by chance than by
  treatment, and the treatment (graph tool use) was mostly not applied.

**E4 (the 8–16× claim)** is contradicted by E3. Raw q2 is reported as **1,029,264 tokens (n=1)**,
while E3's 8 raw q2 runs on the same model and repo have median 113K and max 284K. E4 was also run
while fixes were being made to the system (the doc lists 5 fixes "made this run"), which confounds
the before/after comparison. Its harness is not in the repo. **Treat it as unverifiable.**

**E5–E7** are useful engineering diagnostics, but each is n=1 or unsaved. They can motivate
hypotheses, not support claims.

### 3.3 Re-measurement executed in this investigation [RAN]
Scripts and outputs are in `research/assessment_2026-10/{scripts,results}`.

**Setup:**
- Same sampling as E1: symbols with ≥1 incoming edge, seed 7, n=40.
- Public repos at pinned HEADs:
  - httpx `b5addb6`
  - click `2247b35`
  - axios `2b169bb`
- Added arms and checks:
  - A **grep arm**: `grep -rnw <name>` over source files, lines clipped to 200 chars.
  - **File-level precision/recall** of the graph's referencing-file set, against two reference providers (both limited; see caveats below):
    textual occurrences, and jedi `get_references` (Python only).
- **Tokenizer caveat:** the egress proxy blocked tiktoken's vocabulary download. Tokens are therefore
  approximated two ways: a regex word/punctuation count, and chars/4. The conclusions agree under both.

| Repo | raw/graph (regex · c/4) | grep/graph aggregate | **grep/graph median** | Graph P / R vs jedi (conditioned sample) |
|---|---|---|---|---|
| httpx | 91× · 77× | 8.8× · 5.3× | **1.8× · 1.2×** | 0.97 / 0.82 (n=39) |
| click | 192× · 162× | 8.2× · 5.1× | **2.0× · 1.3×** | 0.91 / 0.97 (n=31) |
| axios | 67× · 61× | 19.2× · 12.8× | **2.9× · 2.3×** | n/a (JS) |

**Selection-bias check:** I drew 120 random Python symbols per repo, with no conditioning on graph
edges.
- httpx: of 53 symbols that jedi says are referenced, **23 (43%) have no incoming graph edge**.
  Mean file-level recall is **0.46**.
- click: 26 of 51 (51%) have no incoming edge. Mean recall is **0.37**.
- Caveats: this "unconditioned" sample was still drawn from graph-discovered symbols, so it excludes
  symbols the parser never found. jedi is an incomplete reference provider (Xu 2026 abandoned it for
  pyright). jedi references include imports, attribute accesses and annotations, while the graph
  returns callers, so the two answer different questions. Global parser caps were not hit in these
  repos, and no caller hit the 12-calls cap. That excludes truncation, but not parse failures,
  ignored files, extraction omissions or lookup ambiguity.
- Output contracts also differ: `lookup_symbol` / `get_dependencies` return caller *names* without
  locations, while grep returns `file:line:text`. Payload sizes are therefore compared at unequal
  information content.

**Interpretation [INT]:**
- The whole-file ratio replicates (61–192×), so the whole-file baseline drives that number.
- Pilot estimates are affected by selection, oracle and task-definition bias. Neither the magnitude
  nor the direction of a corrected effect is established. The grep ratios and recall figures are
  hypotheses for the protocol in `PROTOCOL.md`, not findings.

---

## 4. Related-work matrix

**Access limitation:** the network policy blocked arxiv.org, aclanthology.org, neurips.cc,
conf.researchr.org, Hugging Face and Semantic Scholar for direct fetching. Details below come from
search-engine abstracts and snippets, *not from reading full papers*. Every item was located with a
URL. Before citing any of them, read the full text. Peer-review status is marked as known.

| # | Work | Status | Problem / method | Key reported result | Overlap with Codexa | Implication |
|---|---|---|---|---|---|---|
| 1 | Ouyang et al., **RepoGraph** — [ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/4a4a3c197deac042461c677219efd36c-Abstract-Conference.html) | Peer-reviewed | Line-level repo graph plug-in for SWE agents | +32.8% avg relative on SWE-bench / CrossCodeEval | Repo graph for agents | Graph-for-agents is not new |
| 2 | Liu et al., **CodexGraph** — [NAACL 2025](https://aclanthology.org/2025.naacl-long.7/) | Peer-reviewed | Agent writes graph-DB queries over a code graph | Competitive on CrossCodeEval, SWE-bench, EvoCodeBench | Graph DB + agent tools | Same |
| 3 | Chen et al., **LocAgent** — [ACL 2025](https://aclanthology.org/2025.acl-long.426) | Peer-reviewed | Heterogeneous code graph + multi-hop tools for localization | 92.7% file-level acc; ~86% cost reduction w/ fine-tuned 32B | Graph tools, cost claims | Gives standard localization benchmarks |
| 4 | Vogel et al., **Codebase-Memory** — [arXiv 2603.27277](https://arxiv.org/pdf/2603.27277) | Preprint (Mar 2026) | Tree-sitter KG exposed via MCP; call graph, impact analysis | 83% vs 92% answer quality vs an Explorer agent using file reading and grep (§4.1), ~10× fewer tokens, 2.1× fewer calls, 31 repos; answers graded by the first author against manually derived references | **Near-identical to Codexa's core claim** | Pre-empts the headline; also shows the quality cost. Its agent-level claim cannot be tested by single deterministic payloads |
| 5 | Xu, **Does a Language Server Save Tokens for Coding Agents?** — [arXiv 2608.13568](https://arxiv.org/abs/2608.13568) | Preprint (2026) | Five-arm ablation, grep vs LSP, tokens-to-success; Opus/Sonnet/Haiku | LSP costs +6% to +118% tokens on localization; agents use it 0–6% when free; on reference tasks LSP precision 1.00 vs 0.76, ~19% token premium; oracle switched from jedi to pyright because jedi was too incomplete | **Directly overlaps the recommended direction** and E3's low-uptake finding | Reference recall alone is not a contribution. Possible differentiation: cross-tool graph evaluation and independently sampled queries |
| 6 | **Code Isn't Memory** — [arXiv 2606.22417](https://arxiv.org/pdf/2606.22417) | Preprint (2026) | Structural index (semantic + lexical + call graph) inside a fixed harness, Opus 4.7 | Large localization gain; resolve +17.2pp Go, +2.1pp Python; no cost penalty; no regression vs agentic grep | Structural index vs grep | Benefit is language- and workload-dependent; Python gains small |
| 7 | **ARISE** (first author indexed as Seddik) — [arXiv 2605.03117](https://arxiv.org/pdf/2605.03117) | Preprint (2026) | Statement-level data-flow graph + 3-tier tools | +17.0 Function R@1, 22.0% Pass@1 on SWE-bench Lite | Graph toolset | Richer graphs than Codexa's |
| 8 | Chinthareddy, **Reliable Graph-RAG for Codebases** — [arXiv 2601.08773](https://arxiv.org/abs/2601.08773v1) | Preprint (Jan 2026) | AST-derived vs LLM-extracted KG vs vector RAG (Java) | Deterministic AST KG builds in seconds and has higher coverage | Deterministic graph | Supports structural-only design; not new |
| 8b | **CodeNib** — [arXiv 2607.25431](https://arxiv.org/html/2607.25431v1) | Preprint (2026) | Static navigation vs live language servers, 1,000 requests | 87.4% definition vs 39% reference output agreement with the live server (63.2% pooled); §9.4 states query positions come from the static graph, so results do not estimate arbitrary editor requests | Static-vs-live disagreement; graph-derived sampling | A contribution must *measure* how independent vs graph-conditioned sampling changes conclusions, not just acknowledge the bias |
| 9 | Sen et al., **Is Grep All You Need?** — [arXiv 2605.15184](https://arxiv.org/pdf/2605.15184) | Preprint (2026) | grep vs vector search across 4 harnesses, 5 models (LongMemEval) | grep often wins; the harness matters as much as the retriever | Grep as a strong baseline | Any graph claim must beat grep |
| 10 | **Deep Agentic Search for Repo-Level Code QA** — [arXiv 2608.01507](https://arxiv.org/pdf/2608.01507) | Preprint (Aug 2026) | Semantic search vs subagent grep on SWE-QA | 65.2% vs 46.2% correct; semantic at < ½ cost | Retrieval strategy vs correctness | Shows quality-graded evaluation on SWE-QA is feasible |
| 11 | **SWE-QA** — [arXiv 2509.14635](https://arxiv.org/pdf/2509.14635) (ACL Findings 2026 per [ACL Anthology preview](https://preview.aclanthology.org/ingest-acl/2026.findings-acl.402/)) | Peer-reviewed (Findings) | 576–720 repo-level QA pairs, 15 Python repos, multi-hop | — | Graded benchmark Codexa lacks | Use for quality anchoring |
| 12 | Bai et al., **How Do AI Agents Spend Your Money?** — [arXiv 2604.22750](https://arxiv.org/pdf/2604.22750) | Preprint (Apr 2026) | Token use in agentic coding | Up to 30× variance on the same task; input tokens dominate | Explains E3 variance | Requires many reps and paired designs |
| 13 | Weinberger & Hozez, **Token Reduction Is Not Cost Reduction** — [arXiv 2607.12161](https://arxiv.org/abs/2607.12161) | Preprint (Jul 2026) | 2,848 paired billed Claude Code runs | −38.4% tool-output tokens → +6.8% billed cost (caching); compression can lower completion | Invalidates linear cost claims | Cost must model caching |
| 14 | Lindenbauer et al., **The Complexity Trap** — [arXiv 2508.21433](https://arxiv.org/abs/2508.21433) | NeurIPS 2025 DL4C workshop | Observation masking vs LLM summarization in SWE-agent | Masking halves cost, matches solve rate | Codexa's compaction / eviction | Strong simple baseline for any eviction claim |
| 15 | SWE-Pruner [arXiv 2601.16746](https://www.arxiv.org/pdf/2601.16746); AgentDiet [arXiv 2509.23586](https://arxiv.org/pdf/2509.23586); **Beyond Compaction (CWL)** [arXiv 2606.11213](https://arxiv.org/abs/2606.11213); ReCAP [arXiv 2609.40118](https://arxiv.org/html/2609.40118) | Preprints | Learned, rule-based and dependency-structured eviction | 23–54% token reduction (SWE-Pruner); dependency-graph eviction (CWL) | `context_window.py` | Graph-aware eviction is a crowded space; Codexa's variant is unevaluated |
| 16 | Liu, **Evidence-Carrying Termination** — [arXiv 2608.23623](https://arxiv.org/abs/2608.23623) | Preprint (Aug 2026) | Agent may stop only when a typed certificate binds claims to trace evidence | 0/288 unsafe completions vs 252/288 for a critic | **Very close to controller/validators + verification.py** | Pre-empts the "deterministic completion gate" novelty |
| 17 | Advani, **From Confident Closing to Silent Failure** — [arXiv 2606.09863](https://arxiv.org/pdf/2606.09863); listed at [ICML 2026](https://icml.cc/virtual/2026/77904) | Peer-reviewed (ICML 2026 listing) | False-success rates on tau2-bench, AppWorld | False success is 45–76% of failures; LLM judges AUROC ≤ 0.65 | Motivates mechanical gates | Supports the problem, not Codexa's solution |
| 18 | Mehta, **Confident and Wrong** — [arXiv 2603.25764](https://arxiv.org/pdf/2603.25764) | Preprint (2026) | Silent failures in coding agents; loop detectors | 3-gram loop detector, step ceilings | Thrash detection (`progress.py`) | Prior art for thrash guards |
| 19 | Cuadron et al., **The Danger of Overthinking** — [arXiv 2502.08235](https://arxiv.org/pdf/2502.08235) | Preprint (2025) | Overthinking in reasoning models in agentic tasks; 4,018 trajectories | Analysis paralysis, rogue actions, premature disengagement; selecting low-overthinking runs gives +30% perf, −43% cost | `PROBLEMS.md §1, §4` | Codexa's observations are instances of a known taxonomy |
| 20 | Hou et al., **When Agents Do Not Stop (IAL)** — [arXiv 2607.01641](https://arxiv.org/pdf/2607.01641) | Preprint (Jul 2026) | Static detection of infinite agentic loops | 68 confirmed IALs, 91.9% precision | Recovery-recursion and hang bugs | Prior art for loop failures |
| 21 | Salis et al., **PyCG** — [ICSE 2021](https://2021.icse-conferences.org/details/icse-2021-papers/39/PyCG-Practical-Call-Graph-Generation-in-Python) | Peer-reviewed | Python call graphs | ~99.2% precision, ~69.9% recall | Ground truth / stronger resolver | Use as a call-graph ground truth or a stronger arm |
| 22 | Bairi et al., **CodePlan** — [FSE 2024](https://www.microsoft.com/en-us/research/publication/codeplan-repository-level-coding-using-llms-and-planning-2/) | Peer-reviewed | Incremental dependency + may-impact analysis driving LLM edit plans | Better ground-truth match on migrations | Blast-radius / simulation | Impact analysis for LLM edits is established |

Searches that returned nothing directly comparable: a *model-free*, cross-tool measurement of how
sampling and output contracts change graph-vs-grep-vs-LSP comparisons across many repos. This is
**absence of evidence, not proof of novelty**. Xu (#5) and CodeNib (#8b) are the nearest.

---

## 5. Novelty assessment

| Candidate claim | Evidence in repo | Closest prior work | Verdict | Confidence |
|---|---|---|---|---|
| "Graph retrieval cuts tokens 85.8×" | E1 (whole-file baseline) | #4, #5, #6 | **Rejected as stated.** Whole-file baseline, graph-conditioned sampling, no correctness check. A corrected effect size is not yet established | High |
| "Memory+graph cuts agent tokens 8–16×" | E4 [DOC] | #12, #13 | **Rejected.** Raw arm n=1; contradicted by E3; quality ungraded | High |
| Tree-sitter KG + agent tools as a system | Code | #1–4, #7 | **Standard / integration** | High |
| Four-type project memory | `memory/` | MemGPT-style memories, Codebase-Memory | **Standard engineering** | Medium-high |
| Filesystem-decided completion + graph-grounded claim checks | `controller.py`, `validators.py`, `verification.py`; unit tests | #16, #17 | **Incremental.** A coding-specific instance of evidence-carrying termination. Publishable only with an empirical study of gate accuracy and benefit | Medium |
| Graph-distance-aware eviction | `context_window.py`, no eval | #14, #15 | **Unproven, crowded.** Would need to beat observation masking with caching-aware cost | Medium |
| Simulation→execution witness hash | `witness.py`, sandbox not live | Optimistic concurrency / ETags | **Engineering pattern.** No eval, no live executor | Medium |
| Regex trust boundary | `trust_boundary.py` | Prompt-injection defenses (e.g. AgentDojo evaluations) | **Not a contribution.** Regex filters are known to be bypassable | High |
| Measurement study: how baseline, sampling and output contract change measured navigation efficiency | E1 data + §3.3 pilot | #4, #5, #8b, #9 | **Potentially publishable** as a narrow methodology contribution; significance depends on the resulting evidence | Medium |
| Failure-mode record of reasoning models in harnesses | `PROBLEMS.md`, `AUDIT.md`, commits | #17–20 | **Experience-report material**, only if backed by counted telemetry | Low-medium (depends on logs) |

No "first", "unique" or "state-of-the-art" claim is supportable.

---

## 6. Ranked paper directions

### Direction 1 (recommended): "Measuring Navigation Efficiency: How Baselines, Sampling and Output Contracts Shape Token Comparisons of Repository-Navigation Tools"
**Superseded in detail by `PROTOCOL.md`** (approved for drafting and a small validation pilot only).
- **Primary questions:**
  - Q1: How does baseline choice change measured payload ratios?
  - Q2: How does independent vs graph-conditioned sampling change coverage and tool rankings?
  - Q3: Which tools occupy useful token–quality operating points under equivalent output contracts?
- **Scope of the first study:** definition lookup and direct call-site retrieval; all-reference
  retrieval as a separately scored extension; multi-hop dependencies deferred.
- **Result direction is open.** The pilot does not establish a negative result.
- Optional later extension (agents): graph-tool uptake, which bounds realised savings.
- **Reusable:** `retrieval_payload.py`, `analyze.py`, `tools.py` graph tools, saved E1 JSONs, §3.3
  pilot scripts (as engineering checks only).
- **Arms, reference providers, sampling, metrics, statistics, threats and track:** see `PROTOCOL.md`.
- **Cost:** CPU only for the first study; no API spend.

### Direction 2: "Do Mechanical Completion Gates Help Coding Agents? Measuring False Success, False Rejection and Cost"
- **RQ:** On coding tasks, how often do agents falsely claim completion or make unverifiable claims?
  What fraction do filesystem/exit-code gates and graph-grounded claim checks catch, and at what
  false-rejection and token cost?
- **Reusable:** `controller.py`, `validators.py`, `verification.py`, `task.py`; logged "completion
  claim rejected" events; the `_bare_symbol` incident, where every rejected claim on httpx was true.
  That incident is a false-rejection case study.
- **Required:**
  - Task set with objective ground truth (SWE-bench Lite/Verified subset, or a small suite of
    file-producing tasks with checkers).
  - Arms: no gate; gate-only; claim-check-only; both; LLM-judge gate (cf. #17).
  - Final-answer capture fix in `runner.py`.
  - ≥3 models, ≥5 reps.
- **Metrics:** false-success rate, gate precision/recall vs ground truth, extra rounds/tokens, resolve rate.
- **Effort:** 3–6 weeks; API $300–1,500.
- **Objections:** ECT (#16) already formalises evidence-bound termination; benefit may be small for
  frontier models.
- **Track:** workshop/short.

### Direction 3: "Operating Reasoning Models in a Coding-Agent Harness: A Failure Catalogue from N Runs"
- **RQ:** Which harness-level failure modes do reasoning models produce, how often, and which
  lifecycle mechanisms fix them? Examples: indefinite reasoning, `tool_choice` gaming, task-boundary
  leakage, compaction-induced constraint loss, recovery recursion, silent hangs.
- **Reusable:** `PROBLEMS.md`, `AUDIT.md`, `SECOND_OPINION.md`, `round_telemetry.py`,
  `scripts/telemetry_report.py`, commit history (41 commits).
- **Required:**
  - Retained job and usage logs, which are git-ignored; their availability is unknown.
  - Systematic coding of incidents against existing taxonomies (#17–20).
  - Counts and before/after rates per fix.
- **Effort:** 2–3 weeks if logs exist; not viable without them.
- **Objections:** single system, free-tier models, anecdotal.
- **Track:** experience report / workshop only.

### Direction 4 (larger extension): "Structural Relevance for Agent Context Eviction"
- **RQ:** Does code-graph distance predict re-access of evicted observations, and does using it for
  eviction beat observation masking on cost-adjusted solve rate?
- **Cheap feasibility step first:** test predictive validity offline on public SWE-agent/OpenHands
  trajectories (no API).
- **Required:** SWE-bench Verified subset, masking baseline (#14), caching-aware billing (#13), ≥3 seeds.
- **Effort:** 6–10 weeks; API $1–5K.
- **Objections:** crowded field (#15); gains may vanish once caching is billed.
- **Track:** full paper only if strongly positive.

### Ranking

| Rank | Direction | Defensibility | Significance | Feasibility | Effort |
|---|---|---|---|---|---|
| 1 | D1 measurement validity | High | Moderate | High (no API) | Low |
| 2 | D2 completion gates | Medium | Moderate | Medium | Medium |
| 3 | D3 failure catalogue | Medium-low | Low-moderate | Data-dependent | Low |
| 4 | D4 graph-aware eviction | Uncertain | Moderate-high if positive | Low | High |

**Recommendation: D1.** It turns the project's weakest point (an inflated headline) into its most
defensible question, it can be done mostly offline, and the result is reportable whichever way it
falls. The cost of this choice: it is not a systems paper about Codexa, and Codexa appears as
one of the measured implementations. A later agentic extension of D1 can seed D2 or D4.

---

## 7. Roadmap for D1

Superseded by `PROTOCOL.md`: protocol first, then a small validation pilot, and scaling only after
task labels, sampling and output equivalence pass inspection. No benchmark implementation has started.

The other recommendations still stand: fix `runner.py`'s final-answer capture before any agentic work,
fix the 7 failing tests, and correct the README's 85.8× claim. Cite E4 and E5 only as anecdotes.

---

## 8. Paper outline (D1)

1. **Introduction:** graph-for-agents claims and their headline token ratios (#4, tool READMEs); the
   question is what those ratios measure.
2. **Background:** structural code graphs (#1–4, 7, 8); lexical agentic search (#9, 10); LSP (#5);
   token economics (#12, 13).
3. **Measurement protocol:** information need; arms; oracle; sampling; tokenization; caching model.
   *Fig. 1: protocol diagram.*
4. **Setup:** corpus (*Table 1*: repos, language, LOC, symbols, pinned SHAs); implementations
   (Codexa graph, codebase-memory-mcp, LSP).
5. **Results:** one section per protocol question (Q1 baseline choice, Q2 sampling frame, Q3
   operating points under equivalent output contracts). Figures and tables are listed in `PROTOCOL.md`.
   No results exist yet; the 3-repo pilot is an engineering check, not reportable evidence.
6. **Threats to validity:** oracle error, query type narrowness, tokenizer, language coverage,
   truncation.
7. **Related work.**
8. **Implications:** reporting guidelines for token-reduction claims (baseline, sampling, recall,
   caching).

No abstract or results text is drafted: apart from the 3-repo pilot in §3.3, every result is pending.

---

## 9. Claim–evidence matrix (proposed paper claims)

| Claim | Code | Results now | Prior work | Gap |
|---|---|---|---|---|
| C1 (Q1) Baseline choice changes measured payload ratios substantially | `retrieval_payload.py`, `tools.py` | Pilot only: whole-file 61–192× vs much smaller grep ratios (3 repos, proxy tokenizer, unequal output contracts) | #5, #9 | Protocol: equivalent output contracts, real tokenizer, repo-clustered CIs |
| C2 (Q2) Graph-conditioned vs independent sampling changes coverage estimates and rankings | `retrieval_payload.py` candidate filter | Pilot only; biased by graph-drawn frame, jedi oracle and task mismatch. Direction not established | #8b (CodeNib §9.4) | Declaration-based frame, audited reference sets, error taxonomy |
| C3 (Q3) Tools differ in token–quality operating points under equivalent contracts | `analyze.py`, `tools.py` | None valid yet | #4, #5, #8b | Formatting-controlled arms, thresholds fixed on dev split |
| C5 Agents rarely invoke graph tools unless steered | `runner.py`, `configs.json` | E3: 7% (mode B), 0% (mode C) of calls; one model, one repo | #5 (0–6% LSP uptake) | E-10 with graded answers |
| C6 Payload savings overstate $ savings under caching | — | None | #13 | E-9 |

---

## 10. Questions for you (only those that change the recommendation)

1. **Are the five E1 repos (gods-eye-view, Exam-Proctoring, Tourism-Management, MOMENTUM,
   FitQuest) public, and may they be released?** If yes, the original E1 can be a replication row. If
   not, the paper must rely on public repos only.
2. **Do you still have the git-ignored runtime data** (`.codexa/usage.jsonl`, `backend/data/jobs/*`,
   round telemetry, the `bench_matrix.py` / `memory_ab.py` scratchpad results)? This decides whether
   Direction 3 is viable and whether E4/E5 can be audited.
3. **API budget and permitted models.** $0 keeps D1 model-free. About $300+ enables an agentic
   slice or D2.
4. **Deadline vs strength.** Target LLM4Code / FORGE-D&B (mid-Nov 2026, pilot-scale), or a stronger
   full empirical paper later? (MSR 2027's search-indexed deadline, 23 Oct 2026, is too close; the next
   full-paper cycles would be FSE/ASE 2027 or MSR 2028.)

---

## Appendix A — Record of inspection
- **Read:** `AGENTS.md`, `README.md`, `PROJECT_OVERVIEW.md`, `CODEXA_CLAIMS_AND_PROOF_AUDIT.md`,
  `SECOND_OPINION.md`, `.overnight/PROGRESS.md`, `BENCHMARK_LOG.md` (head), `LIVE_BENCHMARK_LOG.md`,
  `PROBLEMS.md §0–4`, `AUDIT.md` (headings), `docs/graph_token_reduction_proof.md`,
  `docs/token_bench_results.md`, `docs/token_usage_investigation.md`.
- **Read (code):**
  - `tests/benchmarks/memory_graph/{retrieval_payload,runner,aggregate,isolation_checks}.py`,
    `configs.json`, `questions.json`; all `payload_results/*.json`, `raw_runs*/*.json`.
  - `backend/agents/{tools (graph tools), verification, context_window, controller (header),
    validators (header), task (header)}.py`.
  - `backend/simulation/{engine,witness}.py`, `backend/perception/trust_boundary.py`,
    `backend/memory/context.py`, `backend/repository/analyze.py` (header), `api.py:reindex_repository`,
    `backend/files/api.py:repo_root`.
  - `scripts/experiment_2x2.py`, `plan_trials.py` (headers); git log (41 commits).
- **Not inspected in depth:** frontend (`graph-viz/`, `client/`), generated/vendored files
  (`index.html`, `arch_extract.json`, `package-lock.json`), the doc generator scripts, and the
  excluded subsystem.
- **Executed:**
  - Unit test suite.
  - `scripts/payload_recheck.py` on httpx/click/axios under two token proxies.
  - `scripts/selbias.py` on httpx/click.
- **Searched (web):** RepoGraph; CodexGraph; LocAgent; Complexity Trap; grep vs graph token studies;
  overthinking; false completion / termination; code-graph MCP ablations; LSP token savings;
  Codebase-Memory; context eviction (dependency-aware); infinite loops; token-vs-cost; agent token
  spend; repo-level QA benchmarks; AST vs LLM KGs; ARISE; claim verification for code; PyCG; CodePlan;
  silent failures; Code Isn't Memory; deep agentic search; venue CFPs (FORGE 2027, LLM4Code 2027,
  MSR 2027).
- **Blocked:** direct fetch of arxiv.org, aclanthology.org, neurips.cc, conf.researchr.org,
  huggingface.co, semanticscholar.org, and tiktoken's vocabulary host (egress policy).
