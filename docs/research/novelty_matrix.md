# Novelty Matrix — "Anchored Memory" Paper vs. Closest Prior Work

Date: 2026-09-25. Scope: the plan in [`paper_plan.md`](paper_plan.md) (C1–C6; Quorum excluded).

Sources were read on 2026-09-25. **Entries marked (v)** were verified against the paper text in this
pass. The others come from the earlier survey in [`paper_gap_analysis.md`](paper_gap_analysis.md) or
from well-established knowledge. Re-read every row before it is cited in the paper.

---

## 0. Headline — read first

A targeted search turned up **three 2026 papers that pre-empt the core of C1–C3**. None of them was in
the earlier survey:

| Paper | Why it matters |
|---|---|
| **Anand, *Impact Is Not Invalidation: Ask About the Claim, Not the Diff*** (arXiv 2609.25130, 20 Sep 2026) (v) | Git-history benchmark of 10,369 claims from 23 Python libraries. Compares **file anchors, symbol anchors, testmon, a diff-level LLM judge and a claim-level LLM judge**. **The claim-level LLM judge wins** (P 0.79 / R 0.72 vs. symbol anchor P 0.39 / R 0.54). Benchmark and code released. |
| **Hsu et al., *EA-Graph: Artifact-Anchored Verification Memory for Coding Agents under Upstream Drift*** (arXiv 2608.04278, Aug 2026) (v) | Anchors each verification claim to the **content hash of the exact artifact span** it was checked against. Distinguishes STALE / UNPROVABLE / RETAIN. Shows file-level invalidation flags ~88/96 behaviours when ~17 changed. Agent study (synthetic, 42 sessions). |
| **Gao, *Executable Code Knowledge*** (arXiv 2608.16295, Aug 2026) (v) | Source-bound knowledge units with **AST-bounded fingerprints** for freshness (50/50 stale changes detected, 17 same-file controls ignored) and exact changed-line impact. Explicitly targets *selected high-value units*, not every symbol. |

**Consequences:**

- "Hash-anchor memory to code and invalidate on change" is **already done**: EA-Graph (spans), ECK (AST
  fingerprints = our planned A3n), Anand (file and symbol anchor arms).
- "A git-history replay benchmark for claim staleness" is **already done**: Anand, released. Its
  ground truth is behavioural (test assertions), not structural facts.
- **Reviewers will point out** that on the only public benchmark, deterministic anchors *lose* to an
  LLM claim judge. Any paper that presents anchors as the answer, without engaging Anand, will be
  rejected.
- **What survives**:
  1. A **theory** of when anchors are sound or minimal, which explains *why* symbol anchors fail
     (Anand's recall 0.54, our callers recall 0.60).
  2. A **claim-class taxonomy** that routes each claim to the cheapest sound mechanism: graph-query
     anchors for structural claims (exact, free), dependency-closure anchors, and an LLM judge only
     where needed.
  3. The **cascade** (anchor prefilter → claim-level judge), *not evaluated by Anand*.
  4. **Downstream stale adoption by real agents on real repositories**: not studied by Anand; EA-Graph
     is synthetic and tiny.

  §4 revises the paper accordingly.

---

## 1. Paper-by-paper matrix

**Legend.** Overlap names the contribution(s) of ours each paper touches: C1 formalism · C2 replay
benchmark · C3 anchor families · C4 downstream stale study · C5 budgeted glosses · C6 experiential
memory.

### 1.1 Direct competitors (must be discussed in depth and used as baselines)

**Anand 2026 — *Impact Is Not Invalidation*** (v)

| | |
|---|---|
| **What they do** | 23 small Python libraries, 187 commits, 10,369 claims = test assertions; 184 execution-verified flips (1.8%). Arms: always invalidate, never invalidate, file anchor, symbol anchor, testmon, diff-level LLM judge, the same with claim text, and a **claim-level LLM judge**. 5 LLMs. Controls: shuffled diff, post-cutoff split, paraphrase. Released. |
| **Overlap** | C2, C3 (strong); C1 (partial) |
| **Already done — cannot claim** | File and symbol anchor baselines on git history; claim-level vs. diff-level judging; prose-claim variant; leave-one-repository-out robustness; at base rate the judge gives a 10× precision lift. |
| **Still novel for us** | They give no theory; their symbol anchor has **no callee or dependency closure**; they evaluate **no cascade**; **no downstream agent study**; Python only, small libraries; no structural facts, glosses or episodic memory. |
| **Reviewer attack** | "Anand shows an LLM claim judge dominates anchors — why propose anchors?" / "Your replay benchmark duplicates theirs." |
| **Required response** | Run **our anchors and the cascade on their released benchmark** as the head-to-head. Position anchors as a *sound, free prefilter and router*, not a replacement for the judge. Report the precision/recall/cost frontier. |

**EA-Graph (Hsu et al. 2026)** (v)

| | |
|---|---|
| **What they do** | Claims bound to content hashes of the specific artifact spans (store, path, subpath) used for verification; alias resolution; STALE/UNPROVABLE/RETAIN; evidence × freshness lattice. Synthetic worlds (7 × 96 behaviours), Haiku and Sonnet. Anchored memory gives F1 1.0 vs. prose 0.27 on Haiku. |
| **Overlap** | C3 (strong), C4 (partial), C1 (partial: the lattice) |
| **Already done — cannot claim** | Span-hash anchoring of agent claims; the finer-than-file argument, with numbers; an agent-level benefit of anchored memory; a "retain but mark" disposition (≈ our "episodic outdated"). |
| **Still novel for us** | Real repositories and real git history (theirs is synthetic, unversioned); scale (their effective n is tiny); structural query anchors; sufficiency theory; LLM-gloss memory; cost versus wipe. |
| **Reviewer attack** | "Span-hash anchoring is EA-Graph." |
| **Required response** | Cite EA-Graph as the span-anchor method; use it as our A3 baseline under its name. Our delta is claim-class routing plus theory plus a real-repository scale study. |

**ECK — Executable Code Knowledge (Gao 2026)** (v)

| | |
|---|---|
| **What they do** | Code-authored knowledge units (identity, semantics, contract, evidence, relations, provenance, validation state). AST-bounded fingerprints for freshness; exact changed-line impact. 3 Python repositories, 26 patch tasks. |
| **Overlap** | C3 (A3n), C5 (selection of units) |
| **Already done — cannot claim** | AST-bounded fingerprint freshness; the idea that only selected high-value units carry rich knowledge. |
| **Still novel for us** | Scale; automatic (unauthored) memory; a *budgeted selection policy* evaluated against demand; downstream agent effect. |
| **Reviewer attack** | "A3n is ECK's fingerprint." / "ECK already argues for selective units." |
| **Required response** | Cite it; present A3n as ECK-style fingerprinting. Frame C5 as *how to choose* the units ECK says to choose by hand. |

### 1.2 Agent memory architectures (framing and baselines)

**CoALA (Sumers et al., TMLR 2024)**

| | |
|---|---|
| **What they do** | Cognitive-architecture taxonomy: working, episodic, semantic and procedural memory; the decision cycle. |
| **Overlap** | Terminology only |
| **Already done — cannot claim** | The four-type memory taxonomy. |
| **Still novel for us** | That invalidation semantics differ per type (descriptive → invalid, episodic → outdated) under code change. |
| **Reviewer attack** | "Four memory types are not new." |
| **Required response** | Never claim the taxonomy. Use CoALA's terms and claim only the *per-type invalidation semantics*, and only lightly. |

**MemGPT (Packer et al. 2023)**

| | |
|---|---|
| **What they do** | OS-style paging between main context and external (recall/archival) memory; the LLM self-edits memory through function calls. |
| **Overlap** | Background |
| **Already done — cannot claim** | Persistent external memory for LLM agents; self-edited memory. |
| **Still novel for us** | MemGPT has no notion of an external world (code) changing under memory. |
| **Reviewer attack** | — |
| **Required response** | One-line background. |

**Mem0 (Chhikara et al., arXiv 2504.19413)**

| | |
|---|---|
| **What they do** | Extract → update pipeline; the LLM chooses ADD/UPDATE/DELETE/NOOP against similar memories. The graph variant marks conflicting relations invalid (LLM-decided). |
| **Overlap** | C1/C3 (the mechanism class) |
| **Already done — cannot claim** | LLM-judged memory update and invalidation. |
| **Still novel for us** | Mem0 triggers only on *new conversational input*. A code change that contradicts memory without any new message goes undetected. Deterministic triggers. |
| **Reviewer attack** | "Mem0/Zep already invalidate conflicting memory." |
| **Required response** | Show the trigger gap concretely. Implement a Mem0-style update (LLM compares memory with the diff) as a baseline; it is ≈ Anand's diff-level judge. |

**A-MEM (Xu et al., arXiv 2502.12110)**

| | |
|---|---|
| **What they do** | Zettelkasten notes with LLM-generated links. "Memory evolution": new notes trigger LLM rewrites of related notes. |
| **Overlap** | C1 (update propagation) |
| **Already done — cannot claim** | LLM-driven propagation of updates across linked memories. |
| **Still novel for us** | Propagation along *program* dependencies (callee closure, query anchors) is deterministic, not by semantic similarity. |
| **Reviewer attack** | "A-MEM propagates updates across linked notes." |
| **Required response** | Contrast semantic-link propagation with dependency-graph propagation; one sentence plus the A6 result. |

**Zep / Graphiti (Rasmussen et al., arXiv 2501.13956)**

| | |
|---|---|
| **What they do** | Bitemporal knowledge graph (t_valid/t_invalid plus ingestion times); LLM-detected contradictions invalidate edges while the history is kept. |
| **Overlap** | C1 (temporal semantics), C3 |
| **Already done — cannot claim** | Soft invalidation with history retained; bitemporality; LLM contradiction detection. |
| **Still novel for us** | Deterministic invalidation from code state; claim-class routing; a code-specific benchmark. |
| **Reviewer attack** | "Zep already has validity intervals and invalidation." |
| **Required response** | Adopt Zep's bitemporal vocabulary for our records; the contribution is *what triggers* t_invalid for code memory. |

**MIRIX (arXiv 2507.07957)**

| | |
|---|---|
| **What they do** | Six memory types, each with a dedicated manager. |
| **Overlap** | Terminology |
| **Already done — cannot claim** | Richer typed memory than ours. |
| **Still novel for us** | — |
| **Reviewer attack** | "MIRIX has more types." |
| **Required response** | Don't compete on the type count. |

**STALE (Chao et al., arXiv 2605.06527)** (v, abstract)

| | |
|---|---|
| **What they do** | Dialogue benchmark of implicit conflicts: 400 scenarios, 1,200 queries. Systems retrieve the updated state yet fail to adapt their behaviour (the "IPA gap"). |
| **Overlap** | C4 (conceptual) |
| **Already done — cannot claim** | Stale adoption measured in agents, in personal-assistant dialogue. |
| **Still novel for us** | The code domain, where staleness is decidable from repository state; structural and behavioural claims. |
| **Reviewer attack** | "Stale adoption is known (STALE)." |
| **Required response** | Cite it as motivation. Our E3 shows whether the IPA-style gap exists for code and whether deterministic invalidation closes it. |

**Nakayashiki 2026 — *Budgeted Verification Failures*** (arXiv 2608.25553) (v, abstract)

| | |
|---|---|
| **What they do** | Under a verification budget, agents rarely re-check stale inherited constraints (stale decisions in ~75% of episodes); forcing the critical path recovers most of that. |
| **Overlap** | C4, and the cascade idea |
| **Already done — cannot claim** | Agents under-verify stale memory when verification is budgeted. |
| **Still novel for us** | Deterministic freshness removes the need for the agent to choose what to verify. |
| **Reviewer attack** | — |
| **Required response** | Cite it as motivation for machine-side (not agent-side) freshness. |

**Helwig 2026 — *Memory as Infrastructure*** (arXiv 2609.05510) (v, abstract)

| | |
|---|---|
| **What they do** | N=1 operational record of a months-long Claude Code memory harness: health gates, telemetry. |
| **Overlap** | Motivation |
| **Already done — cannot claim** | — |
| **Still novel for us** | — |
| **Reviewer attack** | — |
| **Required response** | Optional motivation citation. |

### 1.3 Memory benchmarks

**LongMemEval (Wu et al., ICLR 2025, arXiv 2410.10813)**

| | |
|---|---|
| **What they do** | 500 questions over long chat histories; 5 abilities including **knowledge updates**, temporal reasoning and abstention. |
| **Overlap** | C2, C4 (question design) |
| **Already done — cannot claim** | A knowledge-update QA methodology; abstention scoring. |
| **Still novel for us** | Updates driven by an *external artifact* (code) rather than the conversation; exact recomputable gold. |
| **Reviewer attack** | "Why not evaluate on LongMemEval?" |
| **Required response** | Out of domain: its updates are conversational. Borrow its knowledge-update and abstention question types for E3. |

**MemoryAgentBench (Hu et al., arXiv 2507.05257)**

| | |
|---|---|
| **What they do** | 4 competencies, including **conflict resolution** (FactConsolidation); current memory agents do poorly, especially on multi-hop conflict. |
| **Overlap** | C4 |
| **Already done — cannot claim** | Evidence that LLM-managed memory handles conflicting updates poorly. |
| **Still novel for us** | Code-derived conflicts with deterministic resolution. |
| **Reviewer attack** | "Conflict resolution is benchmarked." |
| **Required response** | Cite it as evidence that LLM-judged consolidation is fragile, which motivates deterministic triggers. |

### 1.4 Repository graphs and code memory (the structural substrate)

**Codebase-Memory (arXiv 2603.27277)**

| | |
|---|---|
| **What they do** | Tree-sitter knowledge graph (66 languages), XXH3 **incremental re-sync by file hash**, MCP tools, 31 repositories; 10× fewer tokens with some quality loss. |
| **Overlap** | C3 (file-hash sync), substrate |
| **Already done — cannot claim** | A file-hash-driven incremental graph (≈ our A2 applied to the *graph*); graph-served structural answers. |
| **Still novel for us** | They keep the *graph* fresh, not *memory about* the code (glosses, notes, experience); no staleness evaluation. |
| **Reviewer attack** | "Codebase-Memory keeps its index fresh by hashing." |
| **Required response** | Distinguish index freshness (recompute the derivable) from memory freshness (keep or discard the non-derivable). That distinction *is* our claim-class taxonomy. |

**RepoGraph (ICLR 2025, arXiv 2410.14684)**

| | |
|---|---|
| **What they do** | Line-level definition/reference graph; k-hop ego-graph retrieval; plug-in for SWE-bench frameworks. |
| **Overlap** | Substrate |
| **Already done — cannot claim** | Structural graphs improve coding agents. |
| **Still novel for us** | No memory, no temporal validity. |
| **Reviewer attack** | — |
| **Required response** | Background. |

**CodexGraph (NAACL 2025, arXiv 2408.03910)**

| | |
|---|---|
| **What they do** | Code graph database; the agent writes graph queries (Cypher). |
| **Overlap** | Substrate; C3 (query anchors) |
| **Already done — cannot claim** | Graph *queries* as an agent interface. |
| **Still novel for us** | Using the *query result* as an invalidation anchor for memory. |
| **Reviewer attack** | — |
| **Required response** | Background; one line on "query ≠ query-anchor". |

**LocAgent (ACL 2025)**

| | |
|---|---|
| **What they do** | Heterogeneous code graph for localisation; Acc@k protocol on SWE-bench. |
| **Overlap** | C5 (downstream metric) |
| **Already done — cannot claim** | The localisation evaluation protocol. |
| **Still novel for us** | — |
| **Reviewer attack** | — |
| **Required response** | Reuse its protocol for E4 and cite it. |

**CodeNib (2607.25431), RepoAtlas (2609.16936), Deterministic Anchoring (2606.26979)**

| | |
|---|---|
| **What they do** | Incremental multi-view indexes; evolving subgraph views (select–project–refresh); static structure injected as comments. |
| **Overlap** | Substrate, context lifecycle |
| **Already done — cannot claim** | Keeping *retrieval views* fresh across commits (CodeNib, RepoAtlas refresh). |
| **Still novel for us** | Memory is not views: non-derivable content must be kept or discarded, not recomputed. |
| **Reviewer attack** | "RepoAtlas already refreshes." |
| **Required response** | Same derivable-vs-non-derivable argument. |

**Aider repo-map (tool, no paper)**

| | |
|---|---|
| **What they do** | Tree-sitter tags; **PageRank over the symbol/file graph** (personalised to chat files) to fit a token budget. |
| **Overlap** | **C5 (strong)** |
| **Already done — cannot claim** | Graph-centrality selection of symbols under a budget, widely deployed. |
| **Still novel for us** | Evaluation against real demand; learned ranking; the cost of glosses rather than of context. |
| **Reviewer attack** | "Budgeted symbol selection is Aider's repo-map." |
| **Required response** | Treat PageRank as the Aider baseline, explicitly named. |

**Cursor-style Merkle-tree indexing (industry)**

| | |
|---|---|
| **What they do** | Hash tree of files so that only changed chunks are re-embedded. |
| **Overlap** | C3 (A2) |
| **Already done — cannot claim** | File-hash invalidation of derived artifacts. |
| **Still novel for us** | — |
| **Reviewer attack** | "Industry already does this." |
| **Required response** | Acknowledge; A2 is folklore, and our contribution sits above it. |

### 1.5 Experience memory for software-engineering agents

**SWE-Exp (arXiv 2507.23361); trajectory-abstraction repair memory (2607.29658); subtask memory (2602.21611); SWE Context Bench (2602.08316)**

| | |
|---|---|
| **What they do** | Experience banks distilled from past trajectories improve issue resolution; a benchmark for context reuse. |
| **Overlap** | **C6 (strong)** |
| **Already done — cannot claim** | Experiential memory for SWE agents, with SOTA-level results. |
| **Still novel for us** | Staleness of experience after code evolves (to verify: none of these reports an invalidation mechanism). |
| **Reviewer attack** | "Experience memory is SWE-Exp." |
| **Required response** | Keep C6 only as "anchored experience does not go stale", evaluated on SWE Context Bench. Otherwise drop it. |

### 1.6 Classical software engineering — reviewers at ICSE, FSE or MSR will raise these

**Regression test selection — Rothermel & Harrold (safe RTS, TOSEM 1997); Ekstazi (Gligoric et al., ISSTA 2015); testmon**

| | |
|---|---|
| **What they do** | Checksum dependencies (files or classes), rerun only the affected tests; a formal notion of **safety** (no missed affected test). |
| **Overlap** | **C1 (strong)** |
| **Already done — cannot claim** | Proposition 1 is, in spirit, *safe RTS*: dependency checksums give sound change detection. |
| **Still novel for us** | Applying the safety and minimality framing to *memory claims*, including non-executable claims (glosses, structural facts) that RTS cannot cover. |
| **Reviewer attack** | "Your proposition is safe RTS re-derived." |
| **Required response** | Cite RTS safety explicitly; state Propositions 1–2 as the *memory analogue*. Use testmon as a baseline (as Anand does). |

**Incremental computation — Build Systems à la Carte (Mokhov et al., ICFP 2018); Adapton (PLDI 2014); Salsa (rust-analyzer)**

| | |
|---|---|
| **What they do** | Verifying traces and early cutoff: recompute only when the hashes of inputs change, and stop when an output hash is unchanged. |
| **Overlap** | **C1, C3 (strong)** |
| **Already done — cannot claim** | Query anchors with "early cutoff" are exactly Salsa/verifying-trace semantics. |
| **Still novel for us** | Memory records are *not recomputable* by definition (LLM-written). The contribution is deciding *when a non-recomputable artifact loses validity*. |
| **Reviewer attack** | "This is build-system invalidation." |
| **Required response** | Frame anchors *as* verifying traces for agent memory, citing Mokhov et al. The novelty is the non-recomputable claim classes and the empirical study. |

**Comment/code inconsistency — Panthaplackel et al. (AAAI 2021, JIT detection) (v); CUP (Liu et al., ASE 2020); Wen et al. (ICPC 2019)**

| | |
|---|---|
| **What they do** | Detect that a natural-language comment became inconsistent after a code change; update it. |
| **Overlap** | **C3/C4 for glosses (strong)** |
| **Already done — cannot claim** | Staleness of natural-language descriptions of code under change, with learned detectors. |
| **Still novel for us** | Agent memory rather than developer comments; deterministic anchors against learned detectors; downstream agent effect. |
| **Reviewer attack** | "Stale gloss = outdated comment, a solved-ish problem." |
| **Required response** | Add Panthaplackel's detector (or an LLM equivalent) as a gloss-staleness baseline in E1's gloss proxy. |

**Where-to-comment prediction (Louis et al., ICSE-NIER 2020) (v)**

| | |
|---|---|
| **What they do** | Predict which code locations deserve comments. |
| **Overlap** | **C5** |
| **Already done — cannot claim** | "Which code deserves an NL description" as a prediction task. |
| **Still novel for us** | Selection under an LLM cost budget, judged by agent demand rather than developer habit. |
| **Reviewer attack** | "Choosing what to describe is known." |
| **Required response** | Cite it; note that the objective differs (demand coverage per dollar). |

**Change-proneness and defect prediction — churn metrics (Nagappan & Ball, ICSE 2005, and the long line after it)**

| | |
|---|---|
| **What they do** | Predict which files or functions change or break next from history features. |
| **Overlap** | **C5 (strong for D_edit, D_patch)** |
| **Already done — cannot claim** | Our "learned ranker on churn features predicting edits/patches" *is* change/defect prediction. |
| **Still novel for us** | Using it to allocate an LLM-memory budget, plus the downstream localisation effect. |
| **Reviewer attack** | "The learned ranker is defect prediction with a new label." |
| **Required response** | Own that: present C5 as *transferring* defect-prediction features to memory allocation. Novelty is modest, so demote C5. |

---

## 2. Contribution-level verdict (the plan as currently written)

| Plan contribution | Status after this review | Evidence | Verdict |
|---|---|---|---|
| **C1** Formalism: sufficiency ⇒ soundness, minimality | **Partially done.** Safe RTS and verifying traces supply the principle; nobody has stated it for agent-memory claims or used it to explain Anand's and our results | RTS, Mokhov et al.; Anand (no theory) | **Keep**, reframed as the memory analogue of safe RTS. Its value is *explanatory and prescriptive* (routing), not the proposition itself |
| **C2** Replay benchmark | **Largely done** for behavioural claims (Anand, released) | Anand | **Narrow**: structural facts plus glosses, multi-language (TypeScript), larger repositories. A *companion*, not the headline. Evaluate on **Anand's benchmark too** |
| **C3** Anchor families (file, span, AST, query, hybrid) | File, span and AST: **done** (Anand, EA-Graph, ECK, Cursor, Codebase-Memory). Query anchor: **new but trivially exact**. Hybrid span + callee closure: **new** (Anand's symbol anchor has no closure; testmon is a dynamic closure) | as listed | **Keep only query, closure and routing** as ours; the others are named baselines |
| **C4** Downstream stale adoption in agents on real repositories, with cost | **Open.** Anand explicitly has no deployment; EA-Graph is synthetic with n≈42 sessions; STALE and Nakayashiki are non-code | as listed | **Promote to co-headline** |
| **C5** Budgeted gloss selection | **Mostly done in spirit** (Aider PageRank, Louis 2020, defect prediction, ECK's selective units) | as listed | **Demote** to a short section or appendix, or split into an MSR-style short paper |
| **C6** Experiential memory | **Done** (SWE-Exp and follow-ups), except for staleness | as listed | **Drop from the paper**; keep it in the system |
| **NEW C7** Anchor-gated cascade: sound anchor prefilter → claim-level LLM judge only on fired records | **Not evaluated by anyone.** Anand runs the judge on every claim at every change | Anand §(1) (v): "no cascade evaluated" | **New headline.** The judge's precision at a fraction of its calls, *provided the prefilter has high recall*, which is exactly what C1 predicts and what closure anchors buy |

---

## 3. What reviewers will attack, ranked, with the planned defence

| # | Attack | Severity | Defence (must be in the paper) |
|---|---|---|---|
| 1 | "Anand 2026 already did anchor vs. judge on git history, and the judge wins." | **Fatal if ignored** | Head-to-head on **their released benchmark**. The cascade must match or beat their claim judge's F1 with ≥ 3× fewer LLM calls; report the frontier. If it can't, the paper becomes an analysis paper (see §4, fallback) |
| 2 | "Span/AST anchoring is EA-Graph / ECK." | High | Name them as the A3/A3n baselines. Our delta: claim-class routing, closure anchors, theory, real-repository scale, downstream effect |
| 3 | "Proposition 1 is safe regression-test selection." | High (SE venues) | Cite it and state the analogy up front; the contribution is the extension to non-executable claims and the routing it implies |
| 4 | "Query anchors are exact by construction — trivial." | Medium | Agree. Their point is *routing*: structural claims never need an LLM judge; that fraction of memory is free to keep fresh. Measure what share of real agent memory is structural (from Codexa job logs and the E3 memory mix) |
| 5 | "Ground truth from your own static analyzer." | Medium | E1 structural = analyzer consistency (intended). Behavioural claims come from Anand's execution-verified set. Validate call edges with PyCG |
| 6 | "Low base rate (~2%) makes precision meaningless." | Medium | Report at the natural base rate *and* balanced, as Anand does; FIR and SSR; cost per detected flip |
| 7 | "Agents don't really use stale memory — they re-read the code." | Medium | E3 mode T measures exactly this. If stale adoption is small, the claim becomes cost (re-read tokens avoided), per gate G2 |
| 8 | "Python-heavy, small libraries." | Medium | Add TypeScript repositories and SWE-bench-scale Python repositories; per-repository results |
| 9 | "C5 is defect prediction / Aider." | Medium | Demote it; name the baselines; claim only the transfer and the downstream effect |
| 10 | "Where is Mem0/Zep as a baseline?" | Low–Medium | A Mem0-style diff update ≈ Anand's A5; include it on a subsample |

---

## 4. Required revisions to `paper_plan.md`

**New thesis (one sentence):** *Memory about code should be invalidated by the cheapest mechanism
that is sound for its claim class. Structural claims need only graph-query anchors; behavioural and
descriptive claims need an LLM claim judge, but only after a sound dependency-closure anchor fires. We
formalise this routing, and show on two benchmarks (Anand's behavioural claims and our structural and
gloss claims) that it matches claim-level judging at a fraction of the cost. We also show, in real
agents on real repositories, that it removes stale adoption.*

**Revised contributions:**
1. **Claim-class theory.** Soundness and minimality as the memory analogue of safe RTS and verifying
   traces. It explains the recall failures of span anchors (Anand's 0.54, our 0.60) and prescribes
   routing.
2. **Dependency-closure anchors plus the anchor-gated cascade (C7).** Evaluated on Anand's released
   benchmark (head-to-head against their A6) and on our structural/gloss replay set.
3. **Downstream study (C4).** Stale adoption and cost in real agents on real repositories, comparing
   never / wipe / TTL / span anchors / judge-only / cascade.
4. Resources: the structural and gloss replay set (a companion to Anand's), TypeScript included.

**Demoted:** C5 becomes an appendix or a separate short paper. C6 is dropped from the paper.

**New prerequisite tasks (insert before the P1 tasks):**

| # | Task | Size |
|---|---|---|
| P0.7 | Download and reproduce Anand's released benchmark and arms (their A3, A4, A6 numbers within noise) | 1–2 days |
| P0.8 | Implement closure anchors: span hash of X plus span hashes of the static callee closure to depth *d*, and optionally its import closure. Run them on Anand's claims (their claims reference test functions; anchor the test plus the closure of the code under test) | 1–2 days |
| P0.9 | Cascade harness: anchor → judge on fired claims only; sweep *d* and the judge model; plot a cost/F1 frontier | 1 day |

**New gate G1′ (week 2), which replaces G1.** The cascade must reach ≥ 95% of A6's F1 on Anand's
held-out split with ≤ 35% of A6's judge calls.
- **If it passes**, the headline is the cascade.
- **If closure anchors cannot reach recall ≥ 0.85**, the cascade is capped by its prefilter. The
  paper becomes *an analysis of why deterministic anchors cannot be sound for behavioural claims*
  (the theory plus a failure taxonomy plus the structural-claim routing that *does* work). That is
  still publishable, as a workshop or MSR paper.

**Must-cite list, added to the plan:** Anand 2026; EA-Graph; ECK; STALE; Nakayashiki 2026; Rothermel
& Harrold; Ekstazi; testmon; Mokhov et al.; Panthaplackel et al.; Louis et al.; Nagappan & Ball; the
Aider repo-map. Also everything already listed in the plan: CoALA, MemGPT, Mem0, A-MEM, Zep,
MIRIX, LongMemEval, MemoryAgentBench, Codebase-Memory, RepoGraph, CodexGraph, LocAgent, CodeNib,
RepoAtlas, SWE-Exp.

---

## 5. Sources consulted in this pass

- Anand, *Impact Is Not Invalidation* — https://arxiv.org/html/2609.25130
- Hsu, Chi, Everett, *EA-Graph* — https://arxiv.org/html/2608.04278
- Gao, *Executable Code Knowledge* — https://arxiv.org/abs/2608.16295
- Chao et al., *STALE* — https://arxiv.org/abs/2605.06527
- Nakayashiki, *When Stale Constraints Go Unchecked* — https://arxiv.org/abs/2608.25553
- Helwig, *Memory as Infrastructure* — https://arxiv.org/abs/2609.05510
- Panthaplackel et al., *Deep Just-In-Time Inconsistency Detection* — https://arxiv.org/abs/2010.01625
- Louis et al., *Where should I comment my code?* — https://homes.cs.washington.edu/~mernst/pubs/predict-comments-icse2020.pdf
- Also surfaced by the search but not yet read (triage before submission): *MemTX* (arXiv 2607.23929);
  *When Memory Updates but Behavior Does Not* (2608.01619); *Why Does CLAUDE.md Keep Growing?*
  (2608.11095); *Always-On Agents* survey (2606.30306); *The Memory Trust Gap* (2609.01852);
  *Temporal Validity in Retrieval Memory* and *PrecisionMemBench* (both cited by Anand).
- The remaining rows come from [`paper_gap_analysis.md`](paper_gap_analysis.md) §2 and §9, or from
  standard knowledge. Verify each before citing.
