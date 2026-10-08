# Research Paper Plan — Code-Anchored Memory for Coding Agents

> **SUPERSEDED (2026-09-25):** the primary plan is now [`strong_paper_design.md`](strong_paper_design.md)
> (Memory Rot: prevalence → harm → prevention). This file is kept for history.
>
> **REVISION REQUIRED (2026-09-25):** three 2026 papers pre-empt C2/C3 (Anand *Impact Is Not
> Invalidation*, EA-Graph, ECK). See [`novelty_matrix.md`](novelty_matrix.md) §4 for the revised thesis
> (claim-class routing + anchor-gated cascade), new tasks P0.7–P0.9 and gate G1′. Where they conflict,
> §4 of the matrix overrides this plan.

Status: final plan, 2026-09-25. Supersedes the Quorum-centred recommendation in
[`paper_gap_analysis.md`](paper_gap_analysis.md) §3.2. **Quorum/debate is out of scope.**
Implementation and preliminary numbers: [`anchored_memory_experiments.md`](anchored_memory_experiments.md),
[`anchored_memory_results.md`](anchored_memory_results.md).

---

## 0. The paper in one paragraph

Coding agents increasingly keep persistent memory about a repository: what a function does, how to
build the project, what was tried last time. Code changes underneath that memory. Today's systems
either never expire it (and serve stale facts) or wipe it on change (and pay to rebuild everything).
Some let an LLM judge each update, which is slow, costly and unreliable.

We show that for memory about code, staleness can be decided **deterministically**. Each memory
record carries *anchors*: hashable projections of the repository its claim depends on (file bytes, a
symbol's source span, or the answer to a graph query). A record is invalidated exactly when an
anchor changes. We formalise when this is sound, and build a git-history replay benchmark with exact
staleness ground truth. We then measure three things:

1. detection quality across anchor granularities;
2. the downstream effect of stale memory on agent answers;
3. how to spend a fixed budget of LLM-written symbol glosses, the most expensive memory to rebuild.

**Working title:** *Anchored Memory: Deterministic Invalidation of Coding-Agent Memory under Code Evolution*

**Alternative:** *When Does Agent Memory About Code Go Stale? Anchors, Replay, and Budgeted Grounding*

---

## 1. Scope

| In | Out (do not mention beyond one line of future work) |
|---|---|
| Anchored memory: formalism, anchor families, sweep semantics per memory type | Quorum / multi-agent debate / sycophancy |
| Git-history replay benchmark with exact ground truth (released) | The "85.8× token reduction" headline (pre-empted by Codebase-Memory, and a strawman baseline). Tokens appear only as a *cost* metric |
| Downstream: stale memory → wrong answers; anchoring vs. never/wipe/TTL/LLM-judge | Graph-distance context eviction (separate paper, P2) |
| Budgeted symbol-gloss selection: policies, a learned ranker, real demand, downstream localisation | Trust boundary, blast-radius gating, graph visualisation, Time Machine UI |
| Experiential memory from verified tool traces (**secondary**: included only if gate G4 passes) | Neo4j, Qdrant, MCP, Docker sandbox (not implemented; do not claim) |

---

## 2. Contributions (each maps to one experiment)

| # | Contribution | Evidence |
|---|---|---|
| **C1** | **Formalism.** A memory record is a claim plus anchors. *Anchor sufficiency* gives sound invalidation (no stale record served), and *anchor minimality* gives the fewest false invalidations. Semantics differ by memory type: descriptive records are invalidated, episodic records are flagged outdated. | Propositions 1–2 (§3); E1 confirms them empirically |
| **C2** | **Replay benchmark** (working name *MemDrift*): exact, LLM-free staleness labels for 6 fact types over real commit histories of 15 repositories in 2 languages. Released as a dataset plus a harness. | E1 |
| **C3** | **Anchor families compared**: file, symbol span, normalised syntax tree, graph query, and a hybrid (span + query). Hybrid anchors make claims that cannot be recomputed (LLM glosses) nearly sound, at low false-invalidation. | E1, E2 |
| **C4** | **Downstream study**: without invalidation, agents adopt stale memory. Anchoring removes stale adoption at a fraction of wipe's rebuild cost. | E3 |
| **C5** | **Budgeted gloss selection**: which K symbols get an LLM gloss. Hand-written policies are far from the oracle. A leave-one-repo-out learned ranker closes part of the gap, measured against real demand (SWE-bench gold patches, agent traces) and downstream localisation. | E4 |
| C6 (secondary) | Experiential episodic and procedural memory, written from verified tool traces and anchored, which helps on repeated tasks. | E5 (gate G4) |

---

## 3. Formalism (Section 3 of the paper; write this first)

**Definitions**

| Term | Definition |
|---|---|
| Snapshot | S, the repository at a commit |
| View | π : S → V, a deterministic projection of a snapshot. Examples: bytes of file *f*; the source span of symbol *x*; `callers(x)` in the static call graph; the sorted path list |
| Memory record | r = (c, τ, A, t_w): claim c, memory type τ, anchors A = {(π_i, π_i(S_{t_w}))}, write time t_w |
| Predicted stale at S′ | some π_i(S′) ≠ π_i(S_{t_w}) |
| Claim | c(S) is the claim's truth-relevant content as a function of the snapshot |

**Proposition 1 (sufficiency ⇒ soundness).** If c = f ∘ (π_1, …, π_n) for some f (the claim is
determined by its anchored views), then any change in c implies a change in some π_i. The policy
therefore never serves a stale descriptive record (recall = 1).

**Proposition 2 (minimality).** Let π_a = g ∘ π_b; that is, π_a is computable from π_b, so π_b is
finer. Then every change detected by π_a is also detected by π_b. Among sufficient anchors, the
coarsest one has the fewest false invalidations. For any claim, the coarsest sufficient view is the
claim itself (π = c), which yields zero false invalidations.

**Consequences, each tested in E1 and E2**

1. **Graph-derivable facts** (callers, callees, imports, signatures). The claim *is* a deterministic
   query, so anchor on the query result: exact, with recall 1 and FIR 0.
2. **Claims that cannot be recomputed** (LLM glosses, "what X does"). c depends on the span of X
   **and** on the behaviour of what X calls. A span-only anchor is *insufficient*, so recall < 1 is
   predicted. A span + callees-query hybrid restores sufficiency under a stated assumption.
3. **Coarse anchors** (file, repository) are sufficient but not minimal. They are predicted to
   produce high FIR, and the repository wipe gives FIR = 1.
4. **Episodic records** state history ("at t the agent edited f"). They stay true forever, so they
   are flagged as outdated and never invalidated.

State the assumption explicitly: *sufficiency is relative to the static analyzer's views*. Dynamic
dispatch, reflection and DI are outside the views, which is a threat to validity (§9).

---

## 4. Research questions and hypotheses (pre-registered)

Write these into the repository *before* running E3–E5. Each has a pass threshold. A failed
threshold changes the framing, not the honesty of the report (§8).

| RQ | Hypothesis | Pass threshold |
|---|---|---|
| **RQ1** Detection quality by anchor granularity (E1) | H1: query anchors are exact on graph facts; symbol/hybrid anchors beat file anchors, repository wipe and TTL on F1 at every k | Hybrid: recall ≥ 0.95, FIR ≤ 0.10, pooled over ≥ 12 repositories. The ranking holds in ≥ 80% of repositories |
| **RQ2** Do anchor refinements work? (E2) | H2a: hybrid fixes the recall loss of span-only anchors on callers-dependent claims. H2b: normalised-AST anchors cut FIR against byte anchors | H2a: recall +≥ 0.2 over span-only on F2/F3 proxies. H2b: FIR −≥ 25% relative, recall unchanged within CI |
| **RQ3** Does stale memory hurt, and does anchoring fix it? (E3) | H3a: with no invalidation, agents adopt stale values. H3b: anchored policies match wipe's accuracy at much lower rebuild cost | H3a: stale adoption ≥ 15% on changed-fact questions (memory-only mode). H3b: accuracy within 2 pts of wipe (paired CI), rebuild LLM calls ≤ 30% of wipe |
| **RQ4** Which symbols deserve a gloss? (E4) | H4a: the learned ranker beats every hand-written policy on demand coverage. H4b: coverage translates into localisation accuracy | H4a: +≥ 5 pts Coverage@K=80 over the best hand-written policy, leave-one-repo-out, CI excludes 0. H4b: Acc@5 rises monotonically with coverage; ranker > random at equal K |
| **RQ5** (secondary) Does experiential memory help repeated tasks, and does anchoring keep it safe? (E5) | H5: fewer rounds and tokens on sibling tasks; outdated flags prevent reuse of stale procedures | −≥ 15% rounds at equal success; no success drop after code change |
| **RQ6** Overhead (E6) | Sweep and check cost is small against agent cost | Sweep ≤ 5 s on a 5k-symbol repository; per-retrieval file check ≤ 20 ms |

---

## 5. Datasets

### 5.1 Repositories (E1, E2, E4)

15 public repositories, histories at their default branches:

- **Python, SWE-bench Verified repositories.** These give real demand for E4 through gold patches:
  django, flask, requests, pytest, sphinx, sympy, astropy, xarray, scikit-learn, matplotlib,
  seaborn, pylint.
- **TypeScript/JavaScript:** zod, axios, date-fns, prettier, vite. Pick **3** to keep a 12 + 3 mix.
- **Already local:** httpx (and Codexa itself as a sanity repository, reported separately).

Selection rules, fixed before running:
- ≥ 300 first-parent commits;
- ≥ 1k symbols after exclusion;
- parser coverage ≥ 95% of source files.

Exclude generated, minified and vendored files, and data files over 200 KB. For large repositories
(django, sympy, scikit-learn), **restrict to the main package directory** and state this.

### 5.2 Commit pairs

- Distances k ∈ {1, 5, 20, 50}, 30 pairs per k per repository, sampled evenly over history with a
  fixed seed. That is 1,800 pairs in total.
- Up to 300 subjects per fact type per pair.
- Expected scale: about 3M labelled (fact, pair) instances.

### 5.3 Questions (E3)

Questions are generated from the replay facts at t+k. Gold answers are therefore exact, and the
facts that changed between t and t+k are known.

Templates, 3 paraphrases each:

| Fact | Template |
|---|---|
| F1 | "What parameters does `X` take?" |
| F2 | "Which functions call `X`?" |
| F3 | "What does `X` call?" |
| F4 | "Which modules does `f` import?" |
| F5 | "How do I run the tests / dev server?" |
| F6 | "Which version of dependency D is required?" |
| G | "What does `X` do?", graded against the regenerated gloss by an LLM judge, with a human spot-check of 200 |

Mix and size:
- 50% changed facts (stale-sensitive) and 50% unchanged (control).
- 12 repositories × 3 k-values × 40 questions = **1,440 questions**.
- Power: McNemar at α = 0.05 detects a 7–8 point paired difference with 80% power at n ≈ 700 per
  stratum.

Answer-graph validity: F2/F3 gold depends on our call graph. Validate a 300-edge sample against
**PyCG** (Python) and a manual TypeScript sample, and report precision and recall. If edge precision
is below 0.85, restrict E3 to F1/F4/F5/F6 plus G, and keep F2/F3 in E1 only, where analyzer
self-consistency is exactly what is measured.

### 5.4 Real demand (E4)

| Signal | Definition |
|---|---|
| D_patch | symbols modified by the **SWE-bench Verified gold patch** at the task's base commit (500 tasks over the 12 Python repositories). Public, large, reproducible |
| D_agent | symbols an agent actually looked up or read (range reads mapped to enclosing symbols) while solving 150 SWE-bench Verified tasks with a fixed model |
| D_edit | symbols edited in the next N commits (already implemented). Kept as a third, weaker signal |

---

## 6. Experiments

### E1 — Anchor granularity on replay (C1–C3)

- **Policies:**
  - A0 never invalidate
  - A1 repository wipe
  - TTL-{5, 20} (time-based expiry)
  - A2 file anchors
  - A3 symbol-span anchors
  - A3n normalised-AST anchors
  - A4 span + 1-hop files
  - A5 graph-query anchors
  - **A6 hybrid**: span plus callees query, and plus callers query for claims about usage
- **Optional baseline, A7 LLM-judge:** show the old record and the diff, and ask whether the record
  is still true. Run on a 2,000-instance subsample; report accuracy and cost. This is the Mem0/Zep
  style of update.
- **Metrics:**
  - precision, recall and F1 of staleness detection
  - **FIR** (false-invalidation rate: still-true facts thrown away)
  - **SSR** (stale-served rate: stale facts still served)
  - anchors per record
  - check time
- Reporting granularity: per repository, per fact type and per k.
- **Statistics:** cluster bootstrap over commit pairs, 95% CI. Per-repository win/loss counts.
  Never pool alone.
- **Proxy for claims that cannot be recomputed:**
  - "gloss-relevant change" = the span changed **or** a callee's span changed, both computed exactly.
  - Measure A3 vs A6 recall against it.
  - Validate the proxy: on 300 symbols, regenerate glosses at t and t+k and have a judge and a human
    label whether the old gloss is still accurate. Report the proxy's agreement (Cohen's κ).

### E2 — Anchor refinements (ablation inside E1)

- A3n: normalised-AST hash, which ignores comments, whitespace and docstring-only edits.
  Implemented as a tree-sitter token stream without comment nodes.
- A6: sufficiency repair for glosses.
- Report the recall/FIR trade-off curve across A2 → A3 → A3n → A6 → A5.

### E3 — Downstream effect of stale memory (C4)

- **Setup per (repository, pair):**
  - Build memory at t: digest records, NL fact records rendered from the F1–F6 templates, and LLM
    glosses for the sampled symbols.
  - Apply the invalidation policy at t+k.
  - Ask the questions at t+k.
- **Policies:** A0, A1, TTL-20, A3, A6, A5 where applicable, and the A7 subsample.
- **Mode M (memory-only):** one LLM call with the retrieved active memory and no tools. This
  isolates memory, and it is the main table.
- **Mode T (tool agent):**
  - Memory plus `read_file`/`grep`, a fixed budget of 15 rounds and 60k tokens.
  - 300 questions × 4 policies × 1 model.
  - Shows whether tools rescue stale memory, and at what token cost.
- **Metrics:**
  - accuracy (exact or set-F1 for F1–F6; judge for G)
  - **stale adoption**: the answer matches the old value
  - abstention
  - tokens
  - **rebuild cost**: LLM calls and tokens needed to regenerate the invalidated records
  - $ per correct answer
- **Models:** 2 open-weight models (e.g. Qwen3-Coder and DeepSeek-V3.x through NIM) and 1 closed
  model (solar-pro4). Pin the model ID and date. Temperature 0 for M, 3 seeds for T. Cache every
  call.
- **Statistics:** McNemar per policy pair on per-question correctness; paired bootstrap on accuracy
  and cost.

### E4 — Budgeted gloss selection (C5)

- **Policies:** callers, callers_exact, pagerank, degree, git_churn, file_order, random, lazy,
  oracle, and **learned**.
- **Learned ranker:**
  - Model: logistic regression or LightGBM over per-symbol features, predicting membership of
    D_patch ∪ D_agent.
  - Features: in-degree, out-degree, PageRank, public/private, test/library, kind, span length,
    file churn over the last 10/50/200 commits, recency of last edit, depth in the directory tree,
    and whether the symbol is exported.
  - Training: leave-one-repository-out. Report feature importances.
- **Metrics:**
  - Coverage@K for K ∈ {20, 40, 80, 160, 320}
  - area under the coverage–budget curve
  - invalidated share within 20 commits
  - prompt-token cost
- **Downstream check:**
  - Task: function-level localisation on 150 SWE-bench Verified tasks (LocAgent setup, Acc@1/5/10).
  - Glosses available for the top K under {none, random, callers, learned, all}.
  - One model, 3 seeds.
  - This tests H4b: does coverage buy accuracy?
- **Lazy policy:** report it as a latency/cost trade-off. Coverage is always 100% at query time,
  but the calls move onto the critical path; report the added latency per first lookup.

### E5 — Experiential memory (C6, gated)

- **Setting:** sibling tasks on the same repository. Two runs of task families: the same build/test
  command with different code edits, drawn from SWE Context Bench or a constructed set of 60 task
  pairs.
- **Conditions:**
  - no experience
  - experience with anchoring
  - experience without anchoring, after an intervening commit that breaks the old procedure
- **Metrics:** success, rounds, tokens, and the rate at which the stale procedure is reused.
- **Gate G4:** include it in the paper only if the pilot shows H5. Otherwise move it to future work
  with one sentence.

### E6 — Overhead

Measure sweep time and memory against repository size, per-retrieval check latency, and anchor
storage bytes per record, on all 15 repositories.

---

## 7. Engineering work, in order (prerequisites before any new numbers)

| # | Task | Why | Size |
|---|---|---|---|
| P0.1 | Commit the current implementation | checkpoint | 5 min |
| P0.2 | **Analyzer caps configurable; record truncation; fail the replay if truncated.** Exclude generated/minified/data files | `_MAX_SYMBOLS = 4000` silently truncated gods-eye-view. A truncated symbol looks "deleted", which **pollutes ground truth**. Must fix before reporting anything | ½ day |
| P0.3 | A3n normalised-AST anchor and A6 hybrid anchor (production and replay) | E2 | 1 day |
| P0.4 | Gloss-relevant-change proxy and its validation script | E1 | ½ day |
| P0.5 | Clone script for the 15 repositories (pinned SHAs), dataset manifest, deterministic sampling | reproducibility | ½ day |
| P0.6 | Postgres-dependent tests behind a marker; the 9 pre-existing failures fixed or marked | artifact evaluation | ½ day |
| P1.1 | Fact → NL record renderer; question generator with paraphrases; answer parser/grader | E3 | 1.5 days |
| P1.2 | E3 harness: M and T modes, budgets, LLM cache, stale-adoption scoring, cost accounting | E3 | 2 days |
| P1.3 | PyCG comparison for call-graph precision/recall | E3 validity | 1 day |
| P2.1 | SWE-bench demand extractor (gold patch → symbols at base commit) | E4 | 1 day |
| P2.2 | Trace-logging agent run for D_agent | E4 | 1 day + run |
| P2.3 | Learned ranker plus leave-one-repository-out evaluation | E4 | 1 day |
| P2.4 | Localisation harness with gloss injection | E4 downstream | 2 days |
| P3.1 | E5 task pairs and harness (only if running E5) | E5 | 2 days |

---

## 8. Timeline with go/no-go gates (≈ 10 weeks)

| Week | Work | Gate |
|---|---|---|
| 1 | P0.1–P0.6. Re-run E1 on the 5 local repositories with no truncation | **G0**: results reproduce, no truncation, and the tests are green except marked ones |
| 2 | Clone 15 repositories; full E1 and E2 | **G1**: H1/H2 thresholds. *If A6 does not reach recall 0.95, report the frontier and reframe C3 as a trade-off rather than a solution* |
| 3 | P1.1–P1.3. **E3 pilot**: 1 repository, 120 questions, 1 model, mode M | **G2**: stale adoption under A0 ≥ 15%. *If under 5% (models ignore memory), the paper's downstream claim becomes cost: anchoring avoids wipe's rebuild cost at equal accuracy. E3 stays, and the framing changes* |
| 4–5 | Full E3 (M on 3 models, T on 1 model) | — |
| 5–6 | P2.1–P2.4; full E4 | **G3**: H4a. *If the learned ranker does not beat the best hand-written policy, report the negative result plus the oracle gap. That is still a finding: "static centrality predicts demand poorly"* |
| 7 | E5 pilot (gate G4), E6 | **G4**: include or drop E5 |
| 8–9 | Writing (outline §10); figures; artifact packaging | — |
| 10 | Internal review against the §9 objection list; submit to a workshop, or hold for the full venue | — |

**Venues:** check the current calls for papers; the dates below are not verified.
- **Workshop first** (6–8 weeks): LLM4Code (ICSE), DL4Code, or a NeurIPS/ICLR agent/memory workshop.
- **Full paper:**
  - **MSR** fits best: git-history mining, a replay benchmark and a dataset release.
  - Alternatives: ICSE, FSE or ASE (SE framing), or ACL Rolling Review (agent-memory framing).
- Pick one framing per submission. The SE framing leads with C2 + C3 + C5; the ML framing leads with
  C1 + C4.

**Compute and cost estimate:**
- E3 mode M: about 1,440 questions × 6 policies × 3 models ≈ 26k calls × ~3k tokens ≈ 80M tokens.
- E3 mode T: 300 × 4 × 3 seeds × ~40k tokens ≈ 145M tokens.
- E4 downstream: 150 tasks × 5 conditions × 3 seeds × ~40k tokens ≈ 90M tokens.
- Mostly open-weight through NIM. Cache everything; budget a 2× margin.

---

## 9. Threats to validity and pre-emptive answers to reviewers

| Objection | Answer / mitigation built into the plan |
|---|---|
| "Query anchors are exact by construction — trivial." | Yes, and Proposition 2 says why that is optimal. The contribution is the *framework* telling you which anchor to use per claim class, and the hard case (claims that cannot be recomputed) is where E1/E2/E3 show non-trivial results |
| "Ground truth comes from your own analyzer." | For invalidation (E1) that is the point: the memory is about the analyzer's graph. For answers (E3), F2/F3 are validated against PyCG (§5.3), with a fallback to analyzer-independent facts. Glosses are validated by human and judge labels (κ reported) |
| "Staleness prevalence is tiny (~2%), so any policy looks good on accuracy." | Accuracy is never reported for detection. We report precision, recall, FIR and SSR, stratify by k, and balance the E3 questions 50/50 changed/unchanged |
| "Toy repositories." | 15 public repositories, the SWE-bench Verified set among them; per-repository results; selection rules fixed in advance (§5.1) |
| "Truncation / parser failures fake staleness." | P0.2: truncation is recorded and fails the run; parser coverage ≥ 95% is a selection rule |
| "An LLM could just judge staleness." | A7 baseline: accuracy and $ on 2k instances |
| "Why not just re-read the code every time?" | Mode T measures exactly this, with token cost. Wipe is also the re-read-everything policy at memory scale; its rebuild cost is measured |
| "D_edit is not real demand." | D_patch (SWE-bench gold patches) and D_agent (traces) are the primary signals; D_edit is secondary |
| "Model churn / irreproducible." | Open-weight models, pinned IDs, an LLM-call cache released with the artifact, temperature 0 or 3 seeds |
| "Dynamic languages break static views." | Stated assumption (§3); an error analysis of E1 false negatives by cause (dynamic dispatch, re-exports, decorators) |
| "Related work: Zep/Graphiti, Mem0, Codebase-Memory, CodeNib, RepoAtlas, SWE-Exp." | Related work covers temporal KG memory (LLM-judged invalidation), code graphs (no memory invalidation) and experience memory (no staleness handling). Our deterministic, claim-class-aware invalidation is the missing piece. Draft the comparison table in week 1 |

**What we will not claim:**
- that anchoring prevents hallucination in general;
- token-reduction multipliers;
- four-type memory as novel (CoALA and MIRIX precede it);
- anything about Quorum.

---

## 10. Paper outline (8–10 pages + appendix)

| § | Content | Pages |
|---|---|---|
| 1 | Introduction: a motivating example (a stale gloss misleading an agent after a refactor), the gap, contributions C1–C5, headline numbers | 1.25 |
| 2 | Background and related work: agent memory (CoALA, MemGPT, Mem0, A-MEM, Zep, MIRIX), code graphs for agents (RepoGraph, CodexGraph, LocAgent, Codebase-Memory, CodeNib, RepoAtlas), experience memory (SWE-Exp and others), knowledge-update benchmarks (LongMemEval, MemoryAgentBench) | 1 |
| 3 | Anchored memory: formalism, Propositions 1–2, anchor families, per-type semantics | 1.25 |
| 4 | System: how anchors are written, swept and checked in a working agent (Codexa); experiential memory writes | 0.75 |
| 5 | The replay benchmark: construction, fact types, labels, statistics, release | 0.75 |
| 6 | RQ1–2: detection (E1/E2); trade-off frontier figure | 1.25 |
| 7 | RQ3: downstream (E3); stale-adoption and cost figure | 1.25 |
| 8 | RQ4: budgeted glosses (E4); coverage–budget curves, learned-ranker features, localisation | 1 |
| 9 | (RQ5 if G4 passes) and RQ6 overhead; threats; limitations | 0.5 |
| 10 | Conclusion | 0.25 |
| App. | Proofs, templates, per-repository tables, prompts, cost ledger, reproducibility checklist | — |

**Figures:**
1. Motivating example.
2. Architecture (record → anchors → sweep).
3. Recall–FIR frontier across anchor families.
4. F1 against k.
5. E3 accuracy and stale adoption by policy, with rebuild cost.
6. Coverage–budget curves with the oracle.
7. Localisation Acc@5 against K.

---

## 11. Artifact and reproducibility package

- A pinned repository list (URL + SHA) and a clone script.
- The replay harness plus the full labelled dataset, as a JSONL of (repository, t, t+k, fact type,
  subject, old value, new value, stale) and anchors per policy.
- The question set with gold answers; the E3 and E4 harnesses; the LLM-call cache; raw logs.
- One command per table (`make e1`, `make e3-m`, …); a CPU-only path for E1/E2/E4 coverage (no LLM).
- An archive DOI (Zenodo) at submission; artifact-evaluation badge targets: Available, Reusable.

---

## 12. Immediate next actions (this week)

1. P0.1: commit the current work.
2. P0.2: make analyzer caps configurable, fail the replay on truncation, and add the
   generated/data-file exclusion.
3. P0.3: implement the A3n and A6 anchors, with tests.
4. P0.5: write the clone script and fix the repository list, with pinned SHAs.
5. Draft §3 (the formalism) and the related-work comparison table. These can be written now and
   don't depend on results.
