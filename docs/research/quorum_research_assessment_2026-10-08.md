# Quorum research assessment: implementation, evidence, prior work, and paper roadmap

Assessment date: **8 October 2026, Asia/Calcutta**. Inspection and literature searches began 7 October. Checkout: `main`, HEAD `0ea016a`; pre-existing uncommitted work included memory anchoring, annotation policy, retrieval, jobs, and tools. Application code and existing reports/results were not edited. This report and accompanying probe are new research artifacts.

Evidence labels: **F** = directly observed implementation/artifact; **I** = interpretation; **H** = untested hypothesis; **P** = proposed work. A saved status or token ledger is not independently established answer correctness. No live LLM calls, training, or large experiments were initiated. User preference: free APIs for initial tests; human annotation permitted. Free-tier availability and quotas were not tested or assumed.

## 1. Executive verdict

**Current Quorum supports an implementation description and reproducible counterexamples, not a validated accuracy or anti-sycophancy paper.** No labeled Quorum experiment, matched-budget comparison, or saved debate transcript was found. Its default mechanism is heterogeneous candidate generation followed by lexicographic claim-score selection. It is neither majority voting nor a distributed consensus protocol.

**Strongest realistic direction:** a findings-first study of **partial verification in repository QA**: when claim-scored selection helps, when agreement is misleading, and when verification blocks or falsely certifies answer revisions. Working title: *When Verification Is Partial: Evidence, Agreement, and Answer Revision in Repository QA*. Start with a small controlled pilot; add natural repository questions and human annotation before claiming practical generality. Treat an externally enforced revision gate as an experimental arm, not the paper's presumed novelty.

**Largest gap:** no independent answer labels or coverage/precision measurements connect the verifier's side claims to actual question correctness. A model can win with irrelevant or duplicate true claims while its answer is wrong. Some unchecked claims are counted as verified. Eliminating those software defects would not itself establish a scientific contribution.

Close prior work already covers heterogeneous confidence-weighted debate, verifier-guided candidate selection, evidence-gated feedback, identity effects, and coding-agent susceptibility to misleading suggestions. A contribution must expose useful boundary conditions or demonstrate a carefully isolated advantage over simple alternatives. No “first,” “eliminates sycophancy,” “fault tolerant consensus,” or “state of the art” claim is defensible now.

Practical format: focused workshop or short paper after a credible pilot plus natural-code transfer; expand to a full paper only if results generalize and survive cost controls. Acceptance remains uncertain.

## 2. Repository and Quorum analysis

### 2.1 Product, architecture, and actual dependencies

Authoritative [spec](C:/Users/rohit/OneDrive/Documents/Codexa/docs/codexa_os_build_prompt_v5.md:1) defines an engineering knowledge graph platform, PostgreSQL source of truth, Neo4j/Qdrant projections, trust boundaries, simulation before execution, and limited frontend scope. Quorum is not named as a Section 5 subsystem or Section 8 sprint row. Existing implementation is assessed as found; future changes should stay one scoped research/Quorum task at a time. No Section 6 deferred work is needed.

Observed checkout has FastAPI, Pydantic, PostgreSQL/in-memory graph implementations, Tree-sitter repository analysis, agentic chat/jobs, graph-based retrieval, memory, planning, code proposals, and policy/simulation services. README distinguishes running components from modeled interfaces. Docker execution is described as modeled rather than a live sandbox. Infrastructure manifests alone do not establish running projections or queue workers.

Quorum directly uses `LLMClient`, `GraphService`, and shared claim verification. It does **not** invoke ordinary chat tools, retrieval/context assembly, memory maps, Planner/Architect/Coder role dispatch, execution, or the simulation engine. It answers a query and records a decision; it proposes no executed patch. Thus broader platform features cannot be counted as Quorum benefits without testing their integration.

Code reference key, used below:

| Key | Source and relevant responsibilities |
|---|---|
| Q | [quorum.py](C:/Users/rohit/OneDrive/Documents/Codexa/backend/agents/quorum.py:151): orchestration 156–191; panel/failover 193–274; listing 276–298; parse 329–357; verification 359–365; ranking 367–380; debate 382–415; persistence 417–436 |
| V | [verification.py](C:/Users/rohit/OneDrive/Documents/Codexa/backend/agents/verification.py:139): symbol identity/counts 139–173; resolver and fail-open branches 176–215; failed-claim interface 218 onward |
| L | [llm.py](C:/Users/rohit/OneDrive/Documents/Codexa/backend/agents/llm.py:555): tier routing; provider registry/order near 54–220; rate limiter 381 onward; usage 701–715; key retries 717–732; completion 734–741 |
| A | [agents/api.py](C:/Users/rohit/OneDrive/Documents/Codexa/backend/agents/api.py:83): HTTP route and 503 fallback |
| G | [graph/service.py](C:/Users/rohit/OneDrive/Documents/Codexa/backend/graph/service.py:24): graph mutation then event append; [graph/repository.py](C:/Users/rohit/OneDrive/Documents/Codexa/backend/graph/repository.py:96): PostgreSQL upsert; [main.py](C:/Users/rohit/OneDrive/Documents/Codexa/backend/main.py:122): storage selection and Quorum wiring |
| U | [chat/page.tsx](<C:/Users/rohit/OneDrive/Documents/Codexa/graph-viz/app/(workspace)/chat/page.tsx:798>): single query dispatch; result rendering 1482 onward; [lib/api.ts](C:/Users/rohit/OneDrive/Documents/Codexa/graph-viz/lib/api.ts:740): HTTP client |
| S | [repository/analyze.py](C:/Users/rohit/OneDrive/Documents/Codexa/backend/repository/analyze.py:242): Tree-sitter analysis; call resolution 350–394 |

### 2.2 End-to-end mechanism, observed facts

1. UI sends only repository name and current query to `POST /agents/quorum/run` (U:798; A:83). Quorum request contains no chat history. Query length is capped at 2,000 characters; repository name at 100. Explicit model list exists, with no size/uniqueness constraint in this request schema.
2. Default panel target is three. Iterate `balanced`, `heavy`, then `light`; prefer different model-ID provider prefixes; fill from available candidates if fewer prefixes exist (Q:236–263). Explicit override bypasses automatic selection and reserves. This is provider diversity, not measured model-family/error diversity; different hosting prefixes can host related or identical weights. All participants have the same answering role.
3. Compute one shared graph listing: alphabetically first 120 file paths and first 200 unique symbol names (Q:276–298). No source bodies, relationships, definition qualification, query-targeted retrieval, or usage-count data are included. Large repositories introduce a systematic alphabetical truncation effect. Empty indexing is explicitly represented.
4. Submit independent first-round calls through `ThreadPoolExecutor`. Participants share prompt/listing but see no peers initially (Q:204–234). Information isolation does not make statistical errors independent.
5. Ask for JSON: 2–6 sentence answer, self-reported confidence, up to five claims. Allowed types: file existence, symbol existence, symbol usage count. Test/action claims are dropped. This is self-selection of checkable claims, not independent extraction of every factual statement in the answer.
6. Strip complete `<think>...</think>` blocks; greedily locate JSON object. Non-JSON becomes up to 2,000 characters of raw answer, confidence 0.3, zero claims. Confidence clamps to [0,1], but numeric zero incorrectly defaults to 0.5 through `or 0.5` (Q:341). Malformed JSON shapes are not fully schema-validated before accessing fields; some errors can become participant failures.
7. Verify claims against live filesystem and graph (Q:359; V:176). Existence checks generally ignore the assertion text and only test target existence. Symbol qualification is reduced to a bare name. Usage count takes the first unsigned digit sequence from assertion, then counts incoming `calls/imports/depends_on/flows_into` graph edges. This is graph-edge cardinality, not necessarily runtime calls, source occurrences, or unique callers.
8. Compute score `s_i = (verified_i - failed_i, confidence_i * calibration_i)`. Sort lexicographically; retain exact-score maxima (Q:367–380). No majority count, answer clusters, learned judge, or answer synthesis. One minority card can win over two agreeing cards.
9. Calibration is pooled lifetime verified/(verified+failed) claim ratio for the same model string across all stored Quorum decisions; return neutral 1.0 below five claims (Q:310–327). It is not a calibrated probability of answer correctness. Domain, relevance, snapshot, question difficulty, self-selected claim count, and time drift are uncontrolled.
10. Debate only if multiple top cards tie **exactly on both components, including floating-point confidence product**, and answer strings differ (Q:172). One round; only tied models revise. Sequential calls see original tied cards, so later participants do not see earlier revisions from this round.
11. Debate prompt carries **model identity, full peer answer prose, verified/failed counts and failure reasons**. It omits peer claim records/verified atomic evidence, confidence, original query, and repository listing (Q:392–408). “Revise only on verified evidence” is a prompt instruction. Returned revisions are rechecked and accepted without an enforced relation between revised answer and evidence.
12. Re-rank all final cards. Resolved means one answer string among top-scoring cards, including a singleton; it does not mean panel unanimity or verified correctness (Q:178–183). Paraphrases can remain unresolved; a wrong unique winner can be resolved.
13. Persist `QuorumDecision` with query, repository, final cards, winner and flags (Q:417). API returns fresh `quorum_id`, but that ID is not persisted with the node. Original round-1 cards are lost for revised participants; prompts, raw outputs, attempt timing, snapshot hashes, rejection reasons and per-run token totals are absent. Unavailable models are returned but not stored in the decision node.

### 2.3 Failure handling, stopping, and economics

**F:** First-round participant exceptions trigger reserve candidates until available reserves are exhausted. Failed provider prefixes are avoided; explicit overrides have no reserves. One surviving card can produce a resolved decision. Zero survivors raises `QuorumUnavailableError` and HTTP 503. This is availability fallback, not minimum-quorum or Byzantine fault tolerance. Provider classification is coarse; failures caused by malformed output can also blacklist a provider.

**F:** Output-cap error can retry first-round call once at 1,000 tokens instead of 2,000 (Q:268–274). Other key retries occur in L:717–732 on rate limit/auth errors until configured key advancement ends. Debate completion errors keep original card (Q:410–413); parsing/verification after that completion lies outside this exception handler and can still abort a run. There is no iterative convergence loop beyond one debate round.

**F:** Quorum sets no per-call timeout or overall deadline; `LLMClient.complete` passes no explicit default timeout. Effective transport defaults are delegated to installed LiteLLM/provider behavior and were not established as a bounded Quorum SLA. Thread executor exits wait for all submitted futures. Rate-limiter waiting and retries add delay; no early cancellation of losing members.

**I:** For N successful participants, normal path has N logical completions; debate adds T calls for T tied participants, 2 <= T <= N. Actual network attempts also include key retries, output-cap retries, replacements and library retries. At default N=3, successful no-fallback run requests output caps totaling 6,000 tokens, or 12,000 with all three debating. These are requested caps, not bills; historical usage includes a 2,048-token completion, so provider accounting/cap behavior must be logged.

**I:** Initial latency is approximately slowest participant plus verification, limiter wait and reserve waves. Debate adds a sequential sum. Input tokens repeat the listing for each participant. Costs require attempt-level input/output/reasoning accounting and dated prices; free APIs still consume quota and wall time. No verified dollar cost or latency distribution exists for Quorum. Usage records lack run association and elapsed time.

### 2.4 Load-bearing limitations and locally reproduced counterexamples

New **scripted, model-free** probes establish software behavior, not prevalence in real LLMs. Reproducible [probe](C:/Users/rohit/OneDrive/Documents/Codexa/docs/research/quorum_probe_2026-10-08.py:1) and [output](C:/Users/rohit/OneDrive/Documents/Codexa/docs/research/quorum_probe_2026-10-08.json) accompany report.

| Limitation | Observed/local result | Research consequence |
|---|---|---|
| Claim padding, including duplicates | Wrong answer with five repeated true claims beats correct answer with one | Score rewards claim volume; no relevance/answer entailment guarantee (Q:345,376) |
| Majority ignored | Wrong 0.99-confidence card beats two correct 0.8/0.7 cards with equal verified counts; no debate | Cannot claim voting benefit or agreement certificate |
| Fail-open counted as verified | Missing repository file check and unparseable usage count each report `(1,0,[])` | “Not checked” becomes positive evidence (V:185,205; Q:363) |
| Prompt-only revision gate | Tied correct card may switch to wrong peer answer with unchanged supporting claim; accepted | Anti-sycophancy invariant absent |
| Zero confidence bug | Numeric `0.0` becomes `0.5` | Confidence-based comparisons confounded |
| Duplicate target accounting | Failure set keyed by target, not claim identity | One failed assertion suppresses other true assertions for same target |
| Exact prose equality | Semantically identical answers may disagree | Agreement/abstention metrics depend on wording |
| Partial verifier and claim omissions | Empty-claim card remains eligible; even all failing cards have a maximum | No minimum grounding/coverage threshold; unverified prose remains publishable output |
| Incomplete symbol identity and graph approximation | Same-name definitions collapse in V; S resolves calls heuristically, deduplicates edges and applies caps | Graph agreement is not ground truth for natural-code semantic call relations |
| File path check bypasses safe-path helper | V uses `(root / target).exists()` rather than file API `_safe` | Repository membership can be falsely certified by an out-of-root target; containment must be tested before “repo-grounded” claims |

Additional provenance concern: Q:435 labels the whole decision `trusted_user` although answers are generated. PostgreSQL node upsert inspected in G does not retain the schema's provenance field in its SQL insert. Do not assume trust labels establish correctness or survive all storage paths. Quorum listing/peer text does not itself call content-isolation services. No external content was fed into application tools in this investigation.

Distributed-systems analogy stops at the name: no quorum intersection, replicated state-machine agreement, linearizability, fault threshold, leader election, safety/liveness proof, or Byzantine adversary model. Literature on Paxos/Raft is not a useful novelty comparator here.

## 3. Existing evaluation audit

### 3.1 Quorum evidence, separated by status

| Artifact | Question, setup, sample/settings | What it establishes / limitations |
|---|---|---|
| [Quorum unit tests](C:/Users/rohit/OneDrive/Documents/Codexa/tests/test_quorum.py:1) | 22 scripted FakeLLM tests; toy in-memory symbol graph; author-chosen answers/confidences; panel/provider choices, ranking, tie/debate, failures, parsing, calibration, persistence | Software contracts; no dataset, real model version, empirical accuracy, measured persuasion or budget comparison |
| [Quorum claim audit](C:/Users/rohit/OneDrive/Documents/Codexa/tests/audit/codexa_claims/test_claim_quorum.py:16) | 3 tests; allowed enum membership, manually populated card scores, prompt substring assertions | Audit's “deterministic verification” test invokes `_rank` on supplied counts; does not test verifier soundness. Prompt text test does not test model compliance |
| [Saved audit status](C:/Users/rohit/OneDrive/Documents/Codexa/tests/audit/codexa_claims/evidence/test_claim_quorum_evidence.json) | Status PASSED, 2026-09-15T06:24:21Z, 0.26 sec | Verified saved file exists; historical run not independently reconstructible from this small metadata object |
| Usage ledgers `.codexa/usage*.jsonl` | Manual/provider smoke use on 5 and 11 September; no questions, answers, labels, run IDs, prompt settings, repetitions or baseline | **22 unique records**, not 31 experiments. Backup repeats nine current-ledger rows. Zero `quorum_debate` entries. This supports zero logged debate calls, not proof debate never occurred elsewhere |
| PostgreSQL `QuorumDecision` query | Direct read-only SELECT, 5 sec connect/statement limits | **0 nodes in configured database**. Does not rule out lost in-memory decisions, another database or external archives |
| Prior research notes and protocol | Earlier assessment, gap analysis, SYCOPHANCY_PROTOCOL; source and plan comparison | Proposals/reported probes, not new experimental results. Earlier assessment double-counts ledger backup; uses incomplete evidence-gate reading. Preserve originals, correct here |
| Newly run verification | Quorum + shared verifier + audit: **42 passed** | Newly verified software behavior; no live model evidence |
| New probe | Scripted counterexamples, in-memory persistence only | Establishes possible failures; not rates, quality effects or research novelty |

Unique usage by recorded model string (endpoint labels are not independently verified model snapshots):

| Recorded model | Calls |
|---|---:|
| `gemini/gemini-3.7-flash` | 5 |
| `groq/qwen/qwen3.6-27b` | 7 |
| `openrouter/minimax/minimax-m3:free` | 3 |
| `groq/openai/gpt-oss-120b` | 2 |
| `tokenrouter/z-ai/glm-5.3-free` | 3 |
| `nvidia_nim/nvidia/nemotron-3-super-120b-a12b` | 2 |

Totals: **5,845 input + 15,143 completion = 20,988 tokens**. Prompt range 7–467; completion range 16–2,048. Tiny prompts plausibly include availability probes, but no content establishes that classification. Run count cannot reliably be inferred by dividing calls by three. No cost-matched improvement can be computed.

### 3.2 Wider project experiments: reuse without misattribution

| Campaign | Verified artifacts/design | Findings and validity limits |
|---|---|---|
| Memory/graph agentic runner | [runner](C:/Users/rohit/OneDrive/Documents/Codexa/tests/benchmarks/memory_graph/runner.py:1), questions/configs, 12 GLM JSONs, 70 Solar JSONs. Four questions on Exam-Proctoring; raw / graph / graph+memory arms; provider-reported tokens, duration, output text, status, tool counts. GLM: one file per 3x4 cell; Solar incomplete repetition matrix | GLM status: 11 done, 1 error. Solar: 47 done, 23 error; raw 26/6 done/error, graph 18/14, full 3/3. Raw totals are valid saved observations, not verified answer quality. “done” can contain file dumps or notices. No gold scoring. Incomplete/failure-dependent matrix, mutable code, provider fallback and settings create confounds. **No Quorum arm** |
| Token result narrative | [token_bench_results.md](C:/Users/rohit/OneDrive/Documents/Codexa/docs/token_bench_results.md:1) reports another full/raw harness, n=5 full cells, 8–16x reductions | Reported evidence only for exact claims: its cited `scratchpad/bench_matrix.py` absent in inspected checkout. Different harness from saved runner; cannot equate two campaigns or reconcile headline completion claim with 70-file campaign without manifests |
| Retrieval payload | [retrieval_payload.py](C:/Users/rohit/OneDrive/Documents/Codexa/tests/benchmarks/memory_graph/retrieval_payload.py:1), 5 JSONs, 174 sampled symbols; cl100k_base, no models | Saved aggregate 1,860,803 raw vs 21,684 graph tokens = 85.82x under whole-file baseline. Both selection/required file sets derive from graph. Compact graph vs full files partly builds gain into representation; targeted search/snippets are missing baseline. Graph completeness, preprocessing cost and semantic answer equivalence unestablished. Useful token-payload fact, no LLM accuracy or Quorum gain |
| Anchored-memory replay | [replay.py](C:/Users/rohit/OneDrive/Documents/Codexa/tests/benchmarks/memory_anchoring/replay.py:1), 5 JSONs, 144 commit pairs across repositories; k=1/5/20, max 300 facts, seed 0; multiple invalidation policies and TTLs | Saved summary reports 106,248 fact comparisons, 1.9% stale. Same extractor defines operational facts and some query anchors; natural-code semantic truth not independently established. Shared commits/facts are dependent. Reusable snapshots/stale-evidence stress cases; **not 106,248 independent QA trials** |
| Annotation budget | [run.py](C:/Users/rohit/OneDrive/Documents/Codexa/tests/benchmarks/annotation_budget/run.py:1), 4 JSONs, horizon 20, 10 bases, several K values, random seeds 0–4 | Future edit demand coverage and annotation cost proxies; real QA gold-symbol option exists but saved campaign's exact relevance to real QA not established. No Quorum or answer labels. Reuse data handling, not quality claims |

Unit tests are abundant; Quorum scientific evidence is absent. Existing negative/failure data should remain in any future analysis. No saved experiment was rerun with paid APIs or substantial compute.

### 3.3 Newly executed suite and state-preservation caveat

Initial command: `python -m pytest -q -p no:cacheprovider`: **1,131 passed, 25 failed, 1 xfailed**, 124.94 sec. The suite's fixtures isolate files, but do not disable configured database URLs. It selected PostgreSQL; several API tests wrote fixture records, and in-memory `.nodes`/`.events` expectations failed. This was an avoidable verification side effect. Existing database records were not deleted or “restored” by guessing; upserts can also modify existing stable IDs, so unchanged persistent state cannot be claimed. No pre-run database snapshot exists.

Rerun with process-local `CODEXA_DATABASE_URL=''` and `DATABASE_URL=''`: **1,147 passed, 9 failed, 1 xfailed**, 94.45 sec. Remaining failures: five stale/changed GLM routing/pool expectations; advisory intent-fidelity expectation; provider usage default; content-tier environment availability; orphaned `semantic_search` tool group. No tests were edited. Other provider environment remains a limitation; do not classify all nine as product defects without isolation.

Targeted command with database URLs disabled: `python -m pytest tests/test_quorum.py tests/test_verification.py tests/audit/codexa_claims/test_claim_quorum.py -q -p no:cacheprovider`: **42 passed**, 3.41 sec. Full suite is **not clean**. Investigation/report completion does not imply implementation Definition of Done.

## 4. Related-work matrix

Depth: **M** selected method/evaluation sections read beyond abstract; **A** bibliographic record and abstract inspected. Titles/authors/status verified from linked primary sources. “Et al.” abbreviates verified longer author lists. No result below is a Codexa result. Preprints receive no unverified acceptance claim. Table prioritizes closest mechanisms rather than volume.

| ID: verified work | Mechanism, assumptions, evaluation | Precise overlap and difference; claim implication |
|---|---|---|
| R1. Xuezhi Wang, Jason Wei, Dale Schuurmans, Quoc Le, Ed Chi, Sharan Narang, Aakanksha Chowdhery, Denny Zhou. **Self-Consistency Improves Chain of Thought Reasoning in Language Models**. ICLR 2023; [paper](https://arxiv.org/abs/2203.11171). A | Diverse sampled reasoning paths, aggregate final answers; arithmetic/commonsense benchmarks | Repeated inference/aggregation precedent. Same-model N samples mandatory; extra calls alone are not Quorum novelty |
| R2. Yilun Du, Shuang Li, Antonio Torralba, Joshua B. Tenenbaum, Igor Mordatch. **Improving Factuality and Reasoning in Language Models through Multiagent Debate**. ICML 2024; [proceedings](https://proceedings.mlr.press/v235/du24e.html). A | Independent agents exchange answers/rationales over rounds; factuality and reasoning evaluation | Canonical free-text debate comparator. Quorum restricts trigger/claim scoring but still passes prose; restriction efficacy unmeasured |
| R3. Justin Chih-Yao Chen, Swarnadeep Saha, Mohit Bansal. **ReConcile: Round-Table Conference Improves Reasoning via Consensus among Diverse LLMs**. ACL 2024; [paper/DOI](https://aclanthology.org/2024.acl-long.381/). A; PDF retrieval partly failed | Heterogeneous models, confidence-weighted aggregation and discussion; reasoning tasks | Strong precedent for diverse panels/confidence. Quorum's partial deterministic verifier differs, but no fair comparison exists |
| R4. Hyeong Kyu Choi, Xiaojin Zhu, Sharon Li. **Debate or Vote: Which Yields Better Decisions in Multi-Agent Large Language Models?** NeurIPS 2025; [proceedings](https://proceedings.nips.cc/paper_files/paper/2025/hash/934252acd87f254d5d4672fbde283bd2-Abstract-Conference.html), [methods](https://arxiv.org/html/2508.17536v1). M | Separates vote from debate over seven benchmarks; five agents and multiple rounds; DCM/Bayesian belief model yields martingale under stated assumptions; correction-biased interventions | Closest critique of gains attributed to communication. Supports vote baseline, **not universal theorem that all LLM debate cannot help**. Quorum is not voting and its partial oracle is not their ground-truth oracle |
| R5. Hyeong Kyu Choi, Jerry Zhu, Sharon Li. **When Identity Skews Debate: Anonymization for Bias-Reduced Multi-Agent Reasoning**. ACL 2026 long; [DOI/paper](https://aclanthology.org/2026.acl-long.650/). M | Identity-weighted belief update, response anonymization, identity-bias metric, multi-model benchmarks | Quorum exposes model names. Identity removal already established; evaluate content-preserving anonymization separately from removal of answer prose |
| R6. Priya Pitre, Naren Ramakrishnan, Xuan Wang. **CONSENSAGENT: Towards Efficient and Effective Consensus in Multi-Agent LLM Interactions Through Sycophancy Mitigation**. Findings ACL 2025; [DOI/paper](https://aclanthology.org/2025.findings-acl.1141/). A | Dynamic prompt refinement, six reasoning datasets, three models; accuracy/round efficiency | Anti-sycophancy prompting is prior art. Current Quorum rule remains prompt-level; compare mitigation rather than assuming compliance |
| R7. Ansong Ni, Srini Iyer, Dragomir Radev, Veselin Stoyanov, Wen-Tau Yih, Sida Wang, Xi Victoria Lin. **LEVER: Learning to Verify Language-to-Code Generation with Execution**. ICML 2023; [proceedings](https://proceedings.mlr.press/v202/ni23b.html). A | Learned verifier sees programs and execution; reranks samples with generation probabilities; four language-to-code datasets | Selection via external verification established. Quorum uses partial structural claims about NL answers, not execution-grounded whole-program scoring |
| R8. Bei Chen, Fengji Zhang, Anh Nguyen, Daoguang Zan, Zeqi Lin, Jian-Guang Lou, Weizhu Chen. **CodeT: Code Generation with Generated Tests**. 2022 preprint; ICLR 2023 status not independently confirmed through accessible decision page this pass; [paper](https://arxiv.org/abs/2207.10397). A | Generated tests, dual execution agreement, candidate-code selection, HumanEval-type evaluations | Test-guided consensus/selection precedent; generated tests are themselves imperfect. Novelty cannot be “check candidates then choose” |
| R9. Chirag Parmar, Akshat Mehta, Henglin Wu, Jagadish Ramamurthy, Shweta Medhekar. **When Helping Hurts and How to Fix It: Multi-Agent Debate for Data Cleaning**. June 2026 preprint; [methods](https://arxiv.org/html/2606.02866v1). M | Generator/critic; three cleaning benchmarks, four model families; text/execution grounding and evidence-gated G2 prompt strategies; distinguishes damage to correct generation from useful correction | Very close evidence-grounded feedback precedent. Section 7 describes **Generator strategies** and measured compliance, supporting prompt-level interpretation; associated implementation not inspected, so absence of any external gate is not proved. Static repository oracle, answer binding, coverage/error intervention could differ; currently untested |
| R10. Huanhuan Ma, Henry Peng Zou, Chengze Li, Enze Ma, Yunyue Su, Philip S. Yu. **Sycophancy Suppression Can Impair Rational Updating: Anti-Sycophancy Should Preserve the Ability to Update**. August 2026 preprint; [methods](https://arxiv.org/html/2608.26511v1). M | Two-turn unsupported pressure vs valid evidence; four factual/reasoning datasets; inference/training interventions; measures both flip directions | Harm suppression without beneficial correction is insufficient. Quorum study can test system-level selective revision, not claim new definition of sycophancy |
| R11. Yibo Hu, Jiaming Qu. **Most LLM Conformity Needs No Speaker: Measuring the Speaker-Free Floor in Peer-Pressure Benchmarks**. July 2026 preprint; [methods](https://arxiv.org/html/2607.05545v1). M | Same asserted answer with/without source; six open-weight models, seven datasets; re-ask/repetition controls | Peer answer prose alone can cause shifts. Distinguish assertion effect from identity increment; do not label every wrong flip “social pressure” |
| R12. Elliot Myunghoon Kim, Avi Garg, Kenny Peng, Nikhil Garg. **Correlated Errors in Large Language Models**. ICML 2025; [proceedings](https://proceedings.mlr.press/v267/kim25e.html). A | 350+ models, leaderboards and screening; correlated mistakes persist across providers/architectures | Provider-prefix diversity cannot certify independent evidence. Pairwise co-errors/conditional wrong-answer agreement required |
| R13. Yiwei Li, Peiwen Yuan, Shaoxiong Feng, Boyuan Pan, Xinglin Wang, Bin Sun, Heda Wang, Kan Li. **Escape Sky-high Cost: Early-stopping Self-Consistency for Multi-step Reasoning**. ICLR 2024 per primary record; [paper](https://arxiv.org/abs/2401.10480). A | Sequential sampling with stopping/control scheme; arithmetic, commonsense, symbolic reasoning | Adaptive inference is established. Current Quorum is fixed panel with conditional extra round; future adaptive claim needs quality–cost comparison |
| R14. Saurav Kadavath et al. **Language Models (Mostly) Know What They Know**. 2022 preprint; [paper](https://arxiv.org/abs/2207.05221). A | Answer truth/knowledge probability estimation, format and task-transfer dependence | Calibration research precedent. Quorum multiplies self-confidence by claim hit-rate, with no answer labels; cannot call product calibrated without held-out assessment |
| R15. Sebastian Farquhar, Jannik Kossen, Lorenz Kuhn, Yarin Gal. **Detecting hallucinations in large language models using semantic entropy**. Nature 630, 625–630, 2024; [DOI](https://doi.org/10.1038/s41586-024-07421-0), [author PDF](https://sebastianfarquhar.com/assets/papers/farquharDetecting2024.pdf). M introduction/method motivation | Meaning-level uncertainty over samples; targets inconsistent confabulations, not all systematic error | Exact string agreement is weak uncertainty signal. Semantic clustering already exists; deterministic task atoms cheaper/clearer for initial study; unanimity still can be wrong |
| R16. Weihan Peng, Yuling Shi, Yuhang Wang, Xinyun Zhang, Beijun Shen, Xiaodong Gu. **SWE-QA: Can Language Models Answer Repository-level Code Questions?** Findings ACL 2026; [published paper](https://aclanthology.org/2026.findings-acl.402/). M published first page and benchmark record | Natural repository QA, cross-file/multi-hop questions; agent/context strategies | Appropriate transfer dataset beyond trivial existence. **Version mismatch:** arXiv v2 says 576 items/11 repos; published abstract says 720 items. Pin actual released revision and snapshot rather than mixing counts |
| R17. Sen Fang, Weiyuan Ding, Zhezhen Cao, Zhou Yang, Bowen Xu. **AEGIS: From Clues to Verdicts — Graph-Guided Deep Vulnerability Reasoning via Dialectics and Meta-Auditing**. March 2026 preprint; [methods](https://arxiv.org/html/2603.20637v1). M | Repository code-property graph, clue-specific evidence traces, dialectical LLM verifier, audit veto, PrimeVul evaluation and ablations | Directly invalidates broad “first graph-grounded multi-agent code reasoning” claim. Audit is LLM reasoning, not Quorum's deterministic side-claim check. Domain transfer alone is weak; isolate partial-oracle reliability |
| R18. Renwei Meng, Haoyi Wu, Jingming Wang. **VulnAgent-R2: Evidence-Calibrated Multi-Agent Auditing for Repository-Level Vulnerability Detection**. 2026 preprint v3; [paper](https://arxiv.org/abs/2603.13384). A | Graph triage, roles/counter-evidence, selective dynamic verification, calibrated fusion, cost-risk scheduler; multiple vulnerability datasets | Overlaps graph+multi-agent+calibration+budget system framing. Broad Codexa integration novelty weak; mechanistic findings and independent evidence necessary |
| R19. Zhengxuan Wu, Yuxuan Li, Oyvind Tafjord, Been Kim. **XYEval: Agents say yes to bad advice**. September 2026 preprint; [methods](https://arxiv.org/html/2609.23939v1). M | Misleading suggestions in agent tasks including SWE-bench Verified/Pro; decomposed prompt controls and system-instruction defenses | “First coding-agent sycophancy benchmark” rejected. Proposed work narrower: factual revision, typed verification, raw versus accepted outputs, incomplete/wrong verifier records |

Search limitations: focused scholarly web search, primary proceedings/arXiv/author copies, selected methods; not a systematic exhaustive review. OpenReview decision page for R4 blocked by browser challenge; NeurIPS proceedings independently confirms venue. ReConcile PDF later returned internal error; no detailed replication claimed. Nature landing page failed; author PDF accessible. Supplementary code for R9/R18 was not inspected. Recent preprint findings not independently replicated. Prior notes' remaining citations are not automatically endorsed. Failure to find an identical protocol is not novelty evidence.

Backward/forward tracing: R4 and R9 methods/references led back to voting/debate and self-consistency; recent R5/R10/R11/R19 test whether identity, selective updating and code-agent claims are already covered. Targeted invalidation searches for deterministic evidence-gated debate and graph-grounded repository agents found R17/R18. No substantive distributed-consensus connection was found in implementation, so no gratuitous Paxos/Raft survey.

## 5. Contribution assessment

| Candidate precise claim | Code/results; closest work | Difference, significance, missing evidence, confidence/objection |
|---|---|---|
| C0: Existing Quorum isolates initial answers and ranks on selected structural claims | Q; scripted tests; R3/R7/R8 | **Established implementation fact**, useful integration/standard engineering. No new algorithm established. Reviewer: familiar best-of-N/partial verification |
| C1: Partial verification can mis-rank repository answers through irrelevant/duplicate facts, unchecked checks and identity ambiguity | Q/V/S; new probes; R7/R9/R17 | **Established possibility in this implementation**; useful failure taxonomy, not measured population finding. Publishable potential only if prevalence/impact across repositories/models or multiple scoring implementations is shown. Confidence high in counterexamples, low in generality |
| C2: Question-bound verification improves quality–cost tradeoff relative to claim-count Quorum and simple ensembles | No live result; R1/R3/R7/R9 | **H**, modest extension plus empirical contribution. Need natural QA, matched sample reuse, independent labels, preprocessing costs, direct verifier. Reviewer: stronger checker/source access alone explains gain |
| C3: Agreement/self-confidence/claim hit-rate predict correctness only under measurable coverage and diversity conditions | No labeled result; R12/R14/R15 | **H**, findings contribution even without new algorithm. Need held-out calibration, co-errors, support/coverage labels. Reviewer: another dataset/model application; answer with prespecified causal ablations and falsifiable boundary conditions |
| C4: Externally enforced evidence-bound revision reduces accepted wrong changes while retaining useful correction under incomplete verification | Existing protocol is P; R9/R10/R11/R19 | **H**. Sound full-coverage typed gate gives conditional software invariant, not behavioral discovery. Scientific value: unknown/stale/wrong checks, raw model proposals, useful correction, human transfer and direct-verifier comparison. Confidence medium in study relevance, low in eventual advantage |
| “Eliminates sycophancy/hallucinations”; “formal consensus”; “diversity guarantees independence” | No supporting controlled data; Q contradicts guarantees | **Reject** |
| “Belief cards,” “verification before debate,” confidence weighting, or integration alone are novel | R3/R7/R8/R9/R14/R17/R18 | **Reject broad claims**; any narrow distinction still needs evaluated value |
| “85.8x token reduction proves Quorum efficiency” | Payload campaign has no Quorum/model arm | **Reject attribution** |

Novelty is not required for every paper: a robust negative result showing misleading verification status, a measured failure boundary, or a useful evaluation taxonomy can matter. One implementation's contrived bugs are insufficient for a full findings paper.

## 6. Ranked paper directions

Ranks weigh significance, defensibility, evaluation feasibility and effort. Estimates are planning ranges for one engineer/researcher, not commitments. No direction has completed behavioral evidence today.

### 1. Recommended: *When Verification Is Partial: Evidence, Agreement, and Answer Revision in Repository QA*

**RQ:** Does query-relevant structural verification improve heterogeneous answer selection, and under what coverage/identity/error conditions does it hurt? Secondary RQ: does evidence-only feedback improve revision beyond prompt rules and output filtering?

**Contribution/H:** H1, irrelevant/duplicate/unknown verification disproportionately changes winners compared with task-bound support; H2, task-bound scoring outperforms current Quorum at equal initial samples but may not beat best constituent/self-consistency; H3, agreement loses predictive value under correlated errors and unsupported prose. Any null/negative result is publishable only if practically substantial and well characterized.

**Reuse:** Q/V panel/cards; tests and new probe; payload repositories and replay snapshots; existing SYCOPHANCY_PROTOCOL designs. No prior token result counts as answer-quality evidence.

**Modifications:** isolated evaluation harness, independent labels, attempt ledger, canonical answer atoms, tri-state checks, relevance/duplicate control, frozen calibration and scoring arms. Keep production Quorum unchanged during pilot. Pressure/revision sub-study only after selection labels work.

**Baselines:** every constituent, strongest selected on development set, homogeneous N-sample self-consistency, heterogeneous majority, random/uniform sample, current score, task-bound evidence score, direct structural checker plus same-model fallback for unknowns; capped LLM judge if budget permits. No-communication selector uses identical sampled cards.

**Data/metrics:** controlled file/declaration/signature items; 6–10 pinned natural repositories; stratified SWE-QA transfer if release matches snapshots. Answer accuracy, claim validity/relevance/coverage, winner regret vs best constituent, oracle-best-of-N ceiling, calibration, error overlap, selective risk–coverage, cost/latency including index amortization. Human audit required before general repository claims.

**Effort/cost:** 3–5 weeks for useful pilot and modest transfer; free API quota dominates elapsed time. Cache/reuse initial outputs for deterministic selectors. No paid-model dependence in primary pilot; record free-provider refusal/fallback separately.

**Threats/objections:** easy graph-addressable questions, verifier/gold circularity, padding contrived, missing task semantics, unequal evidence, API drift. Include naturally emitted cards and deliberately stressed cards separately; frozen atoms and independently graded transfer; publish nulls. **Format:** workshop/short paper first; full paper only with multi-repository/multi-family robust findings.

### 2. *Evidence or Pressure? Selective Revision under Partial Repository Verification*

**RQ:** At identical evidence access, how do communication restriction and external acceptance filtering separately affect harmful versus beneficial revision? **H:** pressure removal lowers raw unsupported revisions; filtering lowers accepted harm but may freeze useful corrections; stale/wrong authenticated checks can erase benefit.

**Reuse:** existing [SYCOPHANCY_PROTOCOL](C:/Users/rohit/OneDrive/Documents/Codexa/docs/research/SYCOPHANCY_PROTOCOL.md:1), Q cards, snapshot/replay machinery. All claimed outcomes remain proposed.

**Changes:** authenticated query/snapshot-bound check records, separate proposal and accepted answer, one-atom gate, positive/negative facts, content-matched feedback, raw/accepted logging. **Comparators:** free-text/prompt-only rule, anonymous peer text, evidence-only ungated, same output plus gate, freeze, plain re-ask, no-source wrong assertion, direct verifier. Hold identical initial samples/evidence and generation budget.

**Data/metrics:** controlled Python/TypeScript plus human-labeled natural transfer; conditional harmful/beneficial flips, source increment over no-source assertion, final accuracy, blocked useful changes, unknown behavior, schema failures and costs. Do not use model judge for automatically decidable atoms.

**Effort:** 4–7 weeks; revision arms create more calls than cached selection. Start scripted confederates, later real heterogeneous disagreement. **Threat:** zero accepted harm follows sound checker by construction; raw model behavior, lost correction and imperfect evidence supply actual findings. Simple direct checker may dominate. **Format:** short/workshop if bounded; full only if practical transfer and coverage/error results are strong. Higher scientific upside than D1, higher effort and overlap risk.

### 3. *Agreement Is Not Grounding: Calibrating Heterogeneous Code-QA Panels*

**RQ:** Which uncertainty signals predict wrong unanimous answers and identify cases Quorum loses to its constituents? **H:** provider diversity alone poorly predicts co-error; held-out claim relevance/coverage gives better risk ranking than lifetime hit-rate or exact text agreement.

**Reuse/changes:** same D1 sample bank, Q calibration; add time/repository split, semantic/atom agreement, held-out calibration and abstention; remove product score's online leakage. **Baselines:** raw confidence, claim hit-rate, vote margin, sample entropy, calibrated strongest model, semantic uncertainty when feasible. **Metrics:** Brier/ECE, AUROC/AUPRC for error, selective risk, coverage, co-error and regret.

**Data:** cross-repository question strata including ambiguous names and unanswerable items. **Effort/cost:** 2–4 additional weeks after D1; selector analysis cheap, cross-model sampling expensive. **Threats:** small model panels, calibration overfit, independent trials falsely assumed, checker score rewards verbosity. **Format:** findings short paper if signal generalizes; otherwise analysis section of D1. Scientific significance moderate; no currently reusable labeled result.

### 4. *Spend Inference Only When Evidence Disagrees: Adaptive Repository-QA Panels*

**RQ:** Can cheap first answer plus verification choose whether to add a model/debate without sacrificing quality? **H:** learned/prespecified trigger reduces calls at fixed risk; benefit disappears against early-stopping self-consistency or direct checker on simple atoms.

**Reuse/changes:** Q routing/verification and D1 bank; replace exact-score tie trigger with development-selected uncertainty/coverage rule; cost-aware scheduling, timeout/cancellation, unknown fallback, model-family diversity. Keep efficacy evaluation panel fixed; separately evaluate availability recovery.

**Baselines:** fixed N=1/3/5, ESC R13, confidence trigger, random escalation, task-bound checker fallback, budget-capped judge. **Metrics:** full accuracy–cost–p95 latency Pareto curves, error/coverage and worst-class degradation; account sequential overhead/indexing and failed attempts.

**Effort/cost:** 6–10 weeks with additional scheduler evidence; larger panel bank; not justified before D1 establishes a useful verification signal. **Threat:** very crowded adaptive inference literature, development overfit, sequential latency and provider quotas. **Format:** system/full paper only after compelling benefit; otherwise defer.

### Publication routes, officially checked

ARR is a review service, not a conference. ACL-family long/short review offers a plausible route for evidence-backed NLP findings: currently 8/4-page main limits; demo tracks use separate review. October 2026 reviewing-capacity/profile rules require checking current CFP/service qualifications. See [official author guidance](https://aclrollingreview.org/authors). No specific ACL conference deadline is asserted here.

ICSE 2027 NIER is suitable only for a **new SE idea with emerging evidence and future research agenda**, not a compressed completed full paper. Official call requires four main pages plus one references-only page, double-anonymous review and a “Future Plans” section. [Official NIER call](https://conf.researchr.org/track/icse-2027/icse-2027-new-ideas-and-emerging-results--nier-). This is format fit, not a claim its submission window is open. No deadline or acceptance guarantee is given. Workshop names should be chosen after current calls and scope are checked; none is invented here.

## 7. Recommended roadmap and evaluation design

### 7.1 Stage research before changing product

**Stage 0, essential, approximately 3–5 days:** archive manifests/hashes of existing outputs; isolate database/environment; create a research harness under a new benchmark directory; reproduce software counterexamples. Store generator, grader and checker independently. Passing fixtures validates measurement only. No live API calls required.

**Stage 1, free-first diagnostic pilot, approximately 1 week plus quota waiting:** 60 questions, two distinct model families/providers, two initial samples per model = **240 initial calls**. Use approximately 30 controlled and 30 natural items, balanced fact types and positive/negative cases. All deterministic selectors reuse these calls. For a pressure feasibility subset of 20 items/model with one frozen initial sample, four feedback conditions and three generation arms gives **480 revision calls**; total **720 calls**, excluding attempted failures and optional judge. At illustrative 2,000 total tokens/call, envelope is 1.44M tokens, not measured cost. Free quota may take days; do not silently substitute paid providers or stronger fallback models. Inspect first 10 items for parser/label defects, then freeze pilot configuration.

Purpose: establish sufficient initial errors/disagreements, checker's real coverage, logging/labels, and whether any nontrivial gain exists. A 60-item pilot cannot settle a small accuracy improvement. Do not select only initially disagreeing items and then call results population accuracy; report enriched analysis separately.

**Stage 2, confirmatory, contingent:** plan roughly 600 natural/control questions across 6–10 repositories, three model families, three initial samples/model = **5,400 initial calls**. Primary heterogeneous 3-agent panel uses one sample per model for each repetition; homogeneous N=3 compares equal calls. Separate development/pilot and held-out repository/template splits. Secondary revision study adds only prespecified arms/subsets that pilot shows informative; compute cost explicitly before running. Select final sample size using paired discordances, repository clustering and desired interval width/minimum effect from pilot—not a universal fixed N. Free endpoints are acceptable when sufficiently stable; immutable open weights are valuable replication if local capacity permits.

### 7.2 Independent data and labels

Controlled programs: declared grammar creates file inventory, declaration identity/location, signature facts; generator produces expected facts independently of production Tree-sitter graph. Grader uses generator manifest; experimental checker reads source bytes/inventory with a separate route. Include absent targets, duplicates/aliases, malformed output, distractors, large listings and renamed snapshots. Never use the same graph output as both verification and gold label.

Natural repositories: choose language/size/repository strata before model outcomes. Pin commits, dependency/config hashes and data licenses. Query targets sampled independently of graph so missing graph nodes can be detected. Include ordinary existence/declaration questions **and** broader explanation, cross-file and unsupported/ambiguous questions. Only claim soundness for precisely defined syntax/file predicates; natural dynamic dispatch/use counts require manual analysis or explicitly bounded semantics.

Human work now permitted: two annotators independently label a stratified 150–200-item set covering answer correctness, question relevance of claims, unsupported answer clauses and ambiguous identity; adjudicate disagreements. Blind method/provider identity. Publish rubric and agreement (e.g. Cohen's kappa for categorical labels plus raw agreement), denominators and adjudication counts. Pilot labels need not be 200 if budget/time lower; confirmatory natural-transfer labels should be expanded to all evaluated free-form items or a justified sampling design. Annotator hours scale with item complexity; 3–8 minutes per item per rater gives roughly 15–53 total hours for 150–200 items, before adjudication.

If using SWE-QA, pin release and question–commit mappings, inspect leakage/issue-derived answers, distinguish directly reused questions from new templates, and reconcile published/arXiv count mismatch. For free-form scoring, use reference answers plus repository evidence; incomplete reference text is not automatically exhaustive gold.

LLM judges optional, not default labels: blind/randomize answer order, separate judge family from candidate models, repeat swap tests, compare judgments against human audit, report disagreement/position/style/self-family bias. Judge costs and failures count. Do not let judge-vs-generator correlated errors masquerade as independent truth.

### 7.3 Matched comparisons and decisive ablations

Use identical repository snapshot, source context, question, initial sampled candidate bank and output caps across deterministic selectors. Best constituent chosen on development data only. Report each constituent separately. Include simple majority over canonical task answer values; unknown/ambiguous outputs explicitly represented. Use same-model self-consistency at N=3 with stated sampling settings; choose higher N only for separate budget curves.

Direct verifier is essential: on decidable atoms, output checker's value; outside coverage, fall back to same single model. Give checker access/evidence identically across appropriate arms and charge its preprocessing. If direct verification dominates, report that result and abandon superiority claim for multi-agent processing on these tasks.

Selection ablations: N=1/3/5; homogeneous vs heterogeneous with capability controls; raw confidence vs frozen claim hit-rate vs no confidence; count vs deduplicated/relevant support; unknown treated positive vs tri-state; exact text vs task atoms; query-relevant listing vs alphabetical truncation; model identities shown/hidden. Freeze real history or development-estimated calibration before test; do not update it across test arms or use labels from held-out items.

Revision arms: unrestricted peer answer; current prompt rule; anonymized text; evidence-only ungated; identical proposal plus deterministic gate; freeze; direct verifier. Use same frozen initial answer and checker record. Feedback controls: plain re-ask, no-source incorrect assertion, identical assertion attributed to peer/maintainer, genuine relevant correction. Add natural disagreements after scripted confederates; separate confederate realism from field prevalence.

Verifier ablations: known coverage 0/25/50/75/100%, random missingness **and** missing difficult/negative cases; stale snapshot records; authentic but incorrect known records at 1/5/10% rates; wrong target identity; duplicate/irrelevant evidence; cap/parse failures. Stale checks should be rejected by binding; deliberate wrong-but-current values test unsoundness, not authentication. Independent grading remains fixed throughout. Artificial corruption stress curves are not estimates of production corruption rates.

### 7.4 Metrics, repetitions, uncertainty, negative outcomes

Primary selector endpoint: paired held-out answer accuracy difference at equal N; also macro-average by repository/task class. Report all attempts, participant failure rate, resolved/abstained fraction and accuracy conditional on output. Count abstention as non-correct for unconditional accuracy; show risk–coverage separately. “Resolved” is not correctness.

Agreement endpoints: P(correct | unanimity/vote margin/verified score) with bin counts and intervals; pairwise joint errors and conditional same-wrong-answer agreement. Quantify selection regret relative to strongest constituent, and oracle-best-of-N availability without treating oracle selection as deployable.

Revision: HFR = wrong final changes / initially correct eligible items; BFR = corrected final answers / initially wrong eligible items. Report **raw proposal and accepted-output** versions separately; show denominators, invalid outputs, unknown checks and unchanged answers. Social/source increment compares same assertion with vs without attribution; total assertion effect compares no-source assertion with re-ask. Do not infer mental motives from these operational measures.

Repeat stochastic generation at least three independent samples in confirmatory bank, with fixed recorded seed when supported; explicit temperature/top-p, caps and model/provider revisions. Deterministic repeated selectors are not new observations. Pair comparisons at question/snapshot/initial-sample level. Bootstrap repositories then questions (and carry repeat samples together), report 95% intervals; use paired tests/McNemar where independence assumptions appropriate. With few repositories, show per-repo effects and sensitivity/leave-one-repo-out, not precise population intervals. Correct multiple exploratory comparisons (e.g. Holm) and preregister primary endpoint. Small/zero flip cells need binomial interval bounds, not “zero risk” claims.

Practical success: a robust gain or better quality–cost operating point relative to strongest/simple baselines, without unacceptable useful-correction loss or a single easy fact class carrying effect. Before held-out evaluation, set a meaningful accuracy gain and correction-loss margin from pilot (illustrative 3 percentage points each, **not predeclared universal targets**). Also define a minimum relevant coverage; use all sampled questions denominator. Negative outcomes: direct checker dominates; padding rarely occurs naturally; quorum loses to strongest model; gate only filters output and changes no raw behavior; oracle noise erases gain. Each falsifies a corresponding method claim and can still support bounded findings.

### 7.5 Prioritized repository changes, experiments and falsifiers

All changes below **proposed, not applied**. Prefer isolated harness until evidence justifies production integration; retain current Quorum as an explicitly versioned as-is baseline.

| Priority/change and affected component | Limitation/RQ | Isolating experiment; success/negative meaning |
|---|---|---|
| Essential: new benchmark manifest, grader, attempt ledger; research directory only | Missing research evidence/reproducibility | Scripted outputs plus live pilot; every attempt traceable to item/config/snapshot. If accounting incomplete, do not run confirmatory study |
| Essential: process-level DB/provider isolation before testing; later conftest improvement separately | Test state contamination | Temp DB or explicit in-memory mode; no persistent writes. Failure blocks trusted validation, not novelty proof |
| Essential: tri-state `verified/refuted/unknown`, per-claim identity; experimental checker first, eventual V/Q changes | Fail-open miscertification | Same cards, change unknown accounting only; human/source audit. No natural effect means bug matters operationally but may not explain model quality |
| Essential: exact path/symbol/query/snapshot binding and containment | Wrong target/stale evidence | Same-name, out-of-root, renamed-file cases; reject mismatches. Grounded answer accuracy remains separately measured |
| Essential: capture first/final cards, raw output, prompts/settings and run IDs; eventual Q/L/usage | Cannot measure flips/cost | Round replay reproduces winner and metrics; missing first card makes revision claim untestable |
| Essential: canonical graded atom and claim-to-question relevance; benchmark scoring only | Padding/prose not checked | Reuse same bank, count vs relevance/dedup. If strongest model/direct checker still wins, abandon ensemble advantage claim |
| Valuable: externally enforced revision acceptance; separate experimental module, not broad product gate | Prompt compliance vs filtering | Same raw proposal, gate on/off; raw/accepted metrics. Zero accepted harm with sound checker validates contract, not reduced raw sycophancy |
| Valuable: held-out calibration and abstention policy; eventual Q:310/367 | Claim ratio is not correctness probability | Freeze development estimate; calibration/risk curves on held-out repos. No improvement supports simpler score |
| Valuable: query-targeted listing/source snippets; eventual Q:276 | Truncation/insufficient context | Same model/selector, equal input budget; measure before attribution to aggregation. A context-only gain rejects “Quorum mechanism” explanation |
| Optional: learned judge, extra rounds, adaptive panel/deadlines | Utility outside oracle coverage | Budget-frontier comparison to simple fallback/ESC. No meaningful frontier gain means do not add complexity |

No unrelated frontend, cloud, Figma, training or infrastructure expansion is needed. Product integration must preserve trust-boundary/provenance and graph source-of-truth rules; any future executed code proposal still requires simulation. Research output alone is not authorization to implement deferred subsystems.

## 8. Paper outline tied to evidence

1. **Introduction:** developer QA setting, cost of misleading partial certificates; cite R4/R9/R17/R19. State questions, not unmeasured gains.
2. **Related work:** selection vs debate vs verification vs pressure; R1–R19 matrix distilled around closest methods.
3. **System and threat model:** independent generation, partial structural checks, answer binding, unknown state; Figure 1 contrasts existing Q flow and experimental arms. Code and probes support implementation, not quality.
4. **Measurement/data:** frozen repositories, control grammar, independent labels, human rubric, manifests, budget/attempt handling. Table 1 dataset/coverage strata; Table 2 arm/settings/cost design. Requires new artifacts.
5. **Selection findings:** Table 3 matched-budget quality/regret/cost; Figure 2 quality–cost and risk–coverage; Figure 3 agreement versus correctness by coverage/co-error. Requires live labeled bank.
6. **Revision and verifier failures:** Figure 4 raw vs accepted HFR/BFR; Figure 5 missing/stale/wrong-verifier curves; Table 4 naturally occurring failure taxonomy with code/evidence examples. Requires revision subset, audited labels; probe examples clearly labeled synthetic.
7. **Discussion/limitations:** direct-checker comparison, checker/gold soundness, natural vs controlled generality, model drift, index amortization, useful corrections lost; retain negative results.
8. **Reproducibility/ethics/conclusion:** artifact release, licensing, human annotation consent/payment policy where applicable, secrets removed, claim scope. No automatic tool execution from untrusted prompts.

For short paper, retain one primary selection finding plus partial-verifier ablations; move revision to follow-up rather than compressing two incomplete studies. Demo can show traceability, but passing tests alone does not demonstrate research gain.

## 9. Claim–evidence matrix

| Claim | Code | Results now | Prior work | Unresolved gap / permitted wording |
|---|---|---|---|---|
| Independent initial answers, shared context, score-based selection | Q:156–380 | Scripted tests/probe | R1/R3/R7/R8 | Describe implementation; no statistical independence |
| Evidence outranks confidence in score | Q:376 | Hand-built ranking tests | R7/R9 | Conditional on count validity/relevance; not “ground truth answer ranking” |
| Quorum majority or formal consensus | None | Counterexample contradicts | R4 | Reject |
| Quorum reduces peer sycophancy | Q prompt only | No real-model flip data; unsupported revision accepted locally | R5/R6/R9/R11 | Reject current claim; test raw and accepted flips |
| Fail-open/padding can change winner | Q/V | Newly reproduced scripted cases | R7/R9/R17 | “Can occur”; prevalence and impact absent |
| Query-bound verification improves selection | Proposed harness | None | R7/R8/R9 | H; matched bank/direct checker needed |
| Agreement/calibration reliably predicts correctness | Q:310/376 | No independent labels | R12/R14/R15 | H; held-out calibration and co-errors required |
| Sound typed acceptance gate prevents accepted wrong changes from correct atom | Proposed gate | Conditional argument only | R9/R10 | Requires binding + sound known checker; says nothing about raw model, initial errors or prose |
| Partial verification preserves useful correction with lower harm | Proposed arms | None | R9/R10/R11/R19 | H; coverage/error controls and natural transfer |
| Multi-agent method has useful cost advantage | Q/L | Unique token ledger without per-run answers/timing | R1/R13 | H; all attempts plus indexing/latency, simple fallback baseline |
| Large retrieval/memory gains support Quorum quality | Unrelated paths | Existing payload/replay JSONs only | Different mechanisms | Reject attribution; reuse infrastructure/snapshots only |

## 10. Essential user questions and remaining access limits

Already answered: prefer free APIs initially; human annotation acceptable. Plan assumes no hard deadline and no paid-model requirement. Remaining inputs materially changing feasibility:

1. Are additional Quorum outputs/labels/manual notes stored outside this checkout, or in another database? Configured PostgreSQL had no decisions; ledgers alone cannot recover answers.
2. What actual developer question population matters most: structural navigation, architecture/explanations, or decision support? This sets natural sampling and meaningful verifier coverage; do not estimate usage coverage from graph-friendly synthetic questions.
3. Is a fixed venue/deadline or publication-cost ceiling required? Default recommendation is pilot-first short/workshop path, with format chosen from results rather than forced full-paper goal.

No external archives, provider dashboards, historical endpoint snapshots or supplementary research implementations were accessed. No user secrets were printed. Historical outputs cannot be reconstructed from usage counters. Database fixture side effects from initial suite remain disclosed, without speculative cleanup.

### Inspection/search record

- Read repository AGENTS, full v5 spec/sprint/deferred boundaries; README, dependency config, graph storage/service/event paths, app wiring, Quorum code/prompts/API/UI, shared verifier, file-root checks, Tree-sitter call-resolution path, alternatives (retrieval/planner/coder/jobs interfaces), usage/client routing/retry paths.
- Inspected Quorum unit/audit tests and saved status; conftest persistent-state isolation; relevant E2E imports; git status/HEAD and two Quorum history commits `7a69b51` and `0a68b6e` (14 September addition of resilience/related changes). September 5/11 usage predates latest Quorum changes; not direct validation of current implementation.
- Inspected prior research notes/protocol, memory/graph harness/config/questions, all saved campaign JSON metadata, five payload aggregates, five replay/four annotation result configs and corresponding methods. No notebooks found under tests; dependency/vendor/generated repo trees were excluded from first-party searches. Wider unrelated source was sampled by dependency/interface, not every line audited.
- Parsed both usage ledgers, deduplicated exact JSON records; read-only configured PostgreSQL query for QuorumDecision; newly ran two full suite variants and targeted 42-test subset; scripted probe no network.
- Search clusters: heterogeneous panel confidence/voting; self-consistency/best-of-N and execution verifiers; evidence-gated generation/deterministic revision; graph-grounded repository agents; selective updating/identity/speaker-free effects; correlated errors/calibration/semantic entropy; adaptive stopping; natural QA and coding-agent misleading suggestions; official ARR and ICSE NIER formats.
- Sources read/linked in R1–R19; deeper selected sections R4/R5/R9/R10/R11/R17/R19, author PDF introduction R15, published benchmark record R16. No source-count novelty argument; failed/unverified bibliographic guesses omitted. Plan/results/app code remain distinct.
