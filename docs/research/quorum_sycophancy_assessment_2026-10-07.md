# Quorum mode and sycophancy: a research assessment

Date: 7 October 2026. Repository: `main` at `0ea016a`, plus the uncommitted work that was already there.
Stated aim (from the user): *use a new communication protocol to eliminate LLM sycophancy.*

What this investigation did and did not do. It read the code, ran the existing Quorum tests, ran a
local probe with a scripted fake LLM (no network calls, saved only in the session scratchpad), and
searched the literature on the web. It changed no application code, made no paid or live model
calls, and started no training or benchmark runs. This file is the only addition to the repository.

Labels used throughout:
**[F]** observed fact, with a code reference · **[I]** interpretation · **[H]** hypothesis, not yet
tested · **[P]** proposed work.

---

## 1. Executive verdict

**Current paper potential: low as Quorum stands; moderate to good for a focused redesign.**
There is no research evidence for Quorum today. The repository holds plumbing tests and about eight
manual live runs. Those runs saved no outputs or labels, and none of them reached the debate round.
The documents that say Quorum "genuinely avoids sycophancy" (`CODEXA_CLAIMS_AND_PROOF_AUDIT.md:22,195,371`,
`README.md:32`) rest only on unit tests of a sorting function.

**What the mechanism actually is [F/I].** On the default path, Quorum does not run a protocol
between agents. Three models from different providers answer on their own. The system checks each
answer's self-declared existence and count claims against the code graph. The winner is the
argmax of `(verified − failed claims, confidence × historical claim hit-rate)`
(`backend/agents/quorum.py:367-380`). Agents talk to each other only when two top cards tie
*exactly* on that tuple, including the floating-point product, and their answer strings differ
(`quorum.py:172`). The live logs never show this happening. So Quorum avoids peer sycophancy on
its main path by *isolation*, not by protocol. In ML terms it is **verifier-weighted best-of-N
across heterogeneous models with a partial deterministic verifier**.

**Strongest defensible contribution [H].** Repositories offer a cheap, deterministic, *partial*
oracle: the program-structure graph. That oracle makes possible a *code-enforced* communication
rule: "a peer message (or a user challenge) can change an agent's answer only through an atomic
claim that the oracle verified." No answer text, confidence, identity, or rationale prose crosses
the channel. This turns the "selectivity" goal from Ma et al. (2026) (refuse unsupported yielding,
keep rational updating) into a mechanism rather than a training objective. On the fragment of
questions the oracle can decide, harmful flips become impossible *by construction*. The paper's
real empirical content would be three things:
(a) how large that fragment is in real repository QA;
(b) how many *beneficial* updates the gate keeps compared with prompt-only gates, anonymization,
and free-text debate;
(c) what happens outside the fragment.

**Largest evidence gap.** No benchmark, no baselines, no flip logging, and no measured oracle
coverage or precision. Several mechanism defects also undermine the anti-sycophancy property today
(§2.6). The most serious: an unresolvable `file_exists` claim counts as *verified*, and agents can
pad their answers with irrelevant true claims to win.

**Do not use "eliminate".** It holds only on the oracle-decidable fragment, and only when
verification fails closed. Close prior work already exists: evidence-gated revision with
code-execution grounding (Parmar et al., 2606.02866), anonymization (Choi et al., ACL 2026),
sycophancy priors (2604.02668), Free-MAD, and Minority Sentinel. "First" claims are not safe.

---

## 2. Repository and Quorum analysis

### 2.1 Where it lives
| Piece | Location |
|---|---|
| Service, prompts, ranking, debate | `backend/agents/quorum.py` (436 lines) |
| Claim resolution (shared with chat answer verification) | `backend/agents/verification.py:155-252` |
| HTTP endpoint `POST /agents/quorum/run` (503 if no model answers) | `backend/agents/api.py:83-92` |
| Wiring | `backend/main.py:145,195` |
| Graph node type `QuorumDecision` | `backend/graph/schemas.py:28` |
| UI toggle and result card (single-shot; no chat history is sent) | `graph-viz/app/(workspace)/chat/page.tsx:798-813,1482-1530`; `graph-viz/lib/api.ts:740` |
| Tests | `tests/test_quorum.py` (22 tests), `tests/audit/codexa_claims/test_claim_quorum.py` (3 tests) |

### 2.2 End-to-end trace [F]
1. **Panel selection** (`_panel_models`, `quorum.py:236-263`). The system walks the tiers in order
   (`balanced`, `heavy`, `light`) and takes the first model from each distinct provider until it
   has `_PANEL_SIZE = 3`. If too few providers exist, it repeats a provider. The request can
   override the panel. All agents have the same role and get the same prompt. No temperature is
   set anywhere in `backend/agents/llm.py`, so provider defaults apply.
2. **Grounding** (`_repo_listing`, `quorum.py:276-298`). One listing is built and shared by every
   agent: up to 120 file paths and 200 symbol names, sorted alphabetically and cut off at those
   limits. Large repositories therefore show agents only the alphabetical prefix.
3. **Independent answers** (`_gather_cards`, `quorum.py:204-234`). Calls run in parallel threads.
   The prompt says agents cannot see each other. Each agent returns JSON with `answer`,
   `confidence`, and up to 5 `claims`. Claims are limited to `file_exists`, `symbol_exists`, and
   `symbol_used_n_times` (`quorum.py:56`).
4. **Parsing** (`_parse`, `quorum.py:329-357`). `<think>` blocks are stripped. If the output is not
   JSON, the raw text becomes the answer with confidence 0.3 and no claims.
5. **Verification** (`_verify`, `quorum.py:359-365` → `verify_claims`). `file_exists` is checked
   on disk. Symbol claims are checked against the graph. Usage counts are counted over
   `calls`/`imports`/`depends_on`/`flows_into` edges (`verification.py:144-152`).
6. **Ranking** (`_rank`, `quorum.py:367-380`). Each card scores the tuple
   `(verified − failed, confidence × calibration)`. Calibration is the model's lifetime ratio of
   verified to (verified + failed) claims across every stored `QuorumDecision` node, set to 1.0
   below 5 samples (`quorum.py:310-327`).
7. **Debate trigger** (`quorum.py:172`). Debate runs only if two or more cards share the exact top
   tuple *and* their answer strings differ. It lasts one round, and only the tied agents speak
   (`_debate_round`, `quorum.py:382-415`). Each tied agent sees its peers' **model names, full
   answer text, and verified/failed counts plus failure reasons**. It does **not** see the peers'
   verified claim text or their confidence. Any revised card is accepted.
8. **Resolution** (`quorum.py:180-181`). The run is resolved if the top-scoring cards share one
   answer *string*. Otherwise it is unresolved: no winner, and every card is shown.
9. **Persistence** (`_record`, `quorum.py:417-436`). A `QuorumDecision` graph node is written with
   every card and provenance `trusted_user`.

### 2.3 What the mechanism provides, and what it does not
| Property the name might suggest | Present? | Evidence |
|---|---|---|
| Independent first answers | Yes, as far as information flow goes (shared prompt and listing; no peer text) | `quorum.py:204-234` |
| Diverse models | Best-effort: one model per provider | `quorum.py:236-263` |
| Voting or majority | **No.** A 2–1 majority loses to a single higher-confidence dissent | probe #2, §2.6 |
| Formal quorum or consensus guarantee | **No.** The name is unrelated to distributed-systems quorums (no intersection property, no fault model) | — |
| Grounded correctness of the *answer* | **No.** Only the side claims an agent chooses to make are checked, and nothing ties them to the answer | probe #1 |
| Anti-sycophancy revision rule | **Prompt only** (`quorum.py:74-87`). `_debate_round` accepts any revision | probe #5 |
| Peers see verified evidence | **No.** They see answers and counts, not the claims | `quorum.py:392-397` |
| Correlated-error handling | Indirect only (provider diversity). Not measured | — |
| Calibration | Claim hit-rate, not answer accuracy. Pooled across repositories and questions. Applied only inside score ties | `quorum.py:310-327,376` |
| Fault tolerance | Failed members are replaced by reserves from providers that haven't failed. A smaller panel is reported. A failed debate call keeps the round-1 card | `quorum.py:204-234,408-414` |

### 2.4 Retries, timeouts, fallbacks [F]
- A provider error drops that member, adds the provider to a failed set, and pulls the next reserve
  model from a different provider. This repeats until the reserves run out (`quorum.py:218-233`).
- If a provider caps output tokens, the call is retried once with `max_tokens=1000`
  (`quorum.py:268-273`).
- Quorum sets no timeout of its own and relies on the LLM client's.
- If no model answers, the run raises `QuorumUnavailableError` and the endpoint returns HTTP 503.

### 2.5 Calls, tokens, latency, cost
- **[F]** Calls: N first-round calls, in parallel (default N = 3, plus any replacements). Debate
  adds at most one sequential call per tied agent. The debate loop is sequential
  (`quorum.py:388-414`).
- **[F]** Live usage logs (`.codexa/usage.jsonl`, `.codexa/usage.backup-2026-09-11.jsonl`) hold 31
  `quorum` calls from 2026-09-05 and 2026-09-11, about 8 runs. There are **zero** `quorum_debate`
  calls. Prompt sizes were 214–467 tokens; completions were 57–2,048. Qwen3.6-27B hit about
  2,000 completion tokens three times, which matches the 2,000 output cap.
- **[I]** A 214-token prompt is about the size of the template alone. That suggests the
  2026-09-05 runs had an empty or near-empty repository listing (the "no files or symbols are
  indexed" branch). Two log entries with 7–16 prompt tokens look like availability probes, not
  real Quorum prompts. The backend log also shows several HTTP 500s raised from `_ask` before the
  reserve logic existed.
- **[I]** Cost is about N× a single answer, and latency is about the slowest panel member. That
  makes Quorum compute-comparable to self-consistency with N samples, not to a single call.

### 2.6 Mechanism defects that matter for an anti-sycophancy claim
All of these reproduce with a scripted fake LLM and no network
(`scratchpad/probe_quorum.py`, not committed).

| # | Defect | Observed result | Code |
|---|---|---|---|
| 1 | **Claim padding.** The score counts claims, and nothing checks that a claim is relevant to the answer | A wrong answer padded with 3 irrelevant true symbol claims (score 3) beats a correct answer with 1 claim (score 1) | `quorum.py:376` |
| 2 | **Majority ignored** | 2 agents give the correct answer at confidence 0.7 and 0.8; 1 gives a wrong answer at 0.95. The wrong answer wins and no debate runs | `quorum.py:367-380` |
| 3 | **Agreement means identical strings** | Two answers that mean the same thing but are worded differently count as disagreement, which forces a debate and can leave the run unresolved | `quorum.py:172,180` |
| 4 | **Fail-open verification counted as verified** | `file_exists` on an unresolvable repository, and a usage count that can't be parsed, both return holds=True. `_verify` then counts them as **verified** | `verification.py:183,187,203`; `quorum.py:363` |
| 5 | **Revision gate is prompt-only** | An agent that gives in to a peer's answer without any new evidence is accepted, and the peer's answer wins | `quorum.py:405-415` |
| 6 | Confidence `0.0` is parsed as `0.5` (because `or` treats 0.0 as false) | — | `quorum.py:341` |
| 7 | Verified count is computed per target, so one failed claim marks every claim with the same target as failed | — | `quorum.py:363-364` |
| 8 | Agents can't express negative facts ("X does not call Y") as claims. Absence is only implied | — | `quorum.py:56` |
| 9 | Debate triggers on an exact floating-point tie of self-reported confidence, which is effectively a coincidence and not a principled uncertainty signal | 0 debates in the live logs | `quorum.py:172,376` |

Implication [I]: as built, a confident agent that pads its answer can beat a correct majority.
That is a structural form of "persuasion wins" that the module says it prevents.

---

## 3. Audit of existing tests and experiments

| Artifact | Kind | Establishes | Does not establish |
|---|---|---|---|
| `tests/test_quorum.py` (22 tests, **re-run today: all pass**) | Software correctness, scripted LLM | Panel dedupes providers; ranking orders correctly on hand-built cards; debate path, reserve replacement, token-cap retry, `<think>` stripping, persistence | Anything about real model behaviour, accuracy, or sycophancy. The scripted debate revisions are written by the test author |
| `tests/audit/codexa_claims/test_claim_quorum.py` (3 tests, pass) + `evidence/test_claim_quorum_evidence.json` | Claim audit | The allowed claim types are as stated; `_rank` puts a card with a verified claim above a card with a failed claim; the prompt string contains the anti-persuasion sentence | That the prompt is obeyed, or that sycophancy drops. The audit doc's "HIGH confidence" rating overstates this |
| Usage logs (31 calls, about 8 runs) | Manual smoke use | The endpoint ran against real providers | No questions or answers were saved, no ground truth, no baselines, no repetitions. The debate path was never exercised |
| `QuorumDecision` nodes in Postgres | Unknown | Not inspected (no database access in this pass) | — |
| `docs/research/paper_gap_analysis.md` §2.4, §4.2 (2026-09-25) | Earlier internal analysis | Correctly flagged defects 5 and the missing evidence channel, and proposed a hard gate | It is a plan. It did not catch defects 1–4. Its "nobody has tested this in code" is now contradicted by 2606.02866 (§4) |
| `paper_plan.md`, `conference_assessment_2026-10-07.md` | Earlier plans | Both explicitly *excluded* Quorum | — |

Bottom line: **no verified research result exists for Quorum.** Any claim about gains, fewer flips,
or cost-effectiveness is unsupported right now. That includes whether gains would come from the
mechanism, from stronger constituent models, or from N× more inference.

---

## 4. Related-work matrix

Depth key: **(R)** methods read beyond the abstract · **(A)** abstract or summary level only ·
**(K)** well-known paper, not re-opened this session.

| # | Work (verified bibliographic data) | Problem / mechanism | Overlap with Quorum or the proposed protocol | Real difference | Implication |
|---|---|---|---|---|---|
| 1 | Choi, Zhu, Li. *Debate or Vote: Which Yields Better Decisions in Multi-Agent LLMs?* NeurIPS 2025. [arXiv 2508.17536](https://arxiv.org/abs/2508.17536) **(R)** | Splits MAD into voting plus debate. Models debate as a Dirichlet-compound-multinomial belief process and proves it is a **martingale**: debate alone does not improve expected correctness. Interventions: *MAD-oracle* (lock agents that hold the ground-truth answer), MAD-Conformist, MAD-Follower. Uses 7B–32B homogeneous models, 5 agents, temperature 1.0 | The theoretical reason why debate needs a correction-biasing signal | Their oracle is **hypothetical** (it uses ground truth). They use no verifiers or tools. A static-analysis oracle is a *real, partial* version of their intervention | Strongest framing hook. The proposed paper can test the "partial oracle" case they leave open. It cannot claim the theory |
| 2 | Choi, Zhu, Li. *When Identity Skews Debate: Anonymization for Bias-Reduced Multi-Agent Reasoning.* ACL 2026 (long). [arXiv 2510.07517](https://arxiv.org/abs/2510.07517) **(A)** | Identity-weighted Bayesian update; strips identity markers; Identity Bias Coefficient | Quorum's debate prompt *shows* peer model names. An evidence-only channel removes identity | Anonymization equalizes weights but still passes answer text and rationale | Required baseline. Identity removal is not novel |
| 3 | Yao et al. *Peacemaker or Troublemaker: How Sycophancy Shapes Multi-Agent Debate.* [arXiv 2509.23055](https://arxiv.org/abs/2509.23055) (preprint) **(A)** | Sycophancy speeds up disagreement collapse; separates debater-driven from judge-driven failures | Motivation | No verifier | Cite for motivation |
| 4 | Pitre, Ramakrishnan, Wang. *CONSENSAGENT.* Findings of ACL 2025. [doi:10.18653/v1/2025.findings-acl.1141](https://aclanthology.org/2025.findings-acl.1141) **(A)** | Rewrites prompts dynamically to reduce agreement bias | Same goal | Prompt-level | Prompt-level baseline |
| 5 | *Too Polite to Disagree: Understanding Sycophancy Propagation in Multi-Agent Systems.* SIGDIAL 2026. [arXiv 2604.02668](https://arxiv.org/abs/2604.02668) **(A)** | Gives agents peer sycophancy rankings (static or online); +10.5 points absolute accuracy | **Close to Quorum's per-model calibration** (a reliability prior used to discount peers) | Their prior is a sycophancy score; Quorum's is a claim hit-rate, used only to break ties | Kills any novelty claim for "self-calibrating peer weighting" |
| 6 | Bertalanič, Fortuna. *The Cost of Consensus.* ACM CAIS 2026. [arXiv 2605.00914](https://arxiv.org/abs/2605.00914) **(A)** | Splits failure into sycophantic conformity (up to 85.5%), contextual fragility (up to 70%), and consensus collapse (oracle gap up to 32.3 points); debate costs 2.1–3.4× the tokens of self-correction | Taxonomy and cost baseline | 7–8B homogeneous models, math and MMLU | Use their decomposition. Include isolated self-correction as a baseline |
| 7 | Wynn, Satija, Hadfield. *Talk Isn't Always Cheap.* ICML 2025 MAS workshop. [arXiv 2509.05396](https://arxiv.org/abs/2509.05396) **(A)** | Heterogeneous debate lowers accuracy; correct-to-wrong shifts happen even when strong models are the majority | Heterogeneous panel, like Quorum | No verifier | Motivation for heterogeneous panels |
| 8 | Qu, Fu, Hu. *Easier to Mislead Than to Correct.* [arXiv 2606.01637](https://arxiv.org/abs/2606.01637) (preprint) **(A)** | Harmful revision 62.9% under an all-wrong peer condition vs. beneficial revision 51.5% under all-correct; CoT and reflection don't fix it | Defines the harmful/beneficial flip metrics to use | Diagnostic only | Adopt their metric definitions and conditions |
| 9 | Hu, Qu. *Most LLM Conformity Needs No Speaker.* [arXiv 2607.05545](https://arxiv.org/abs/2607.05545) (preprint) **(A)** | Restating a wrong answer with no speaker still causes 66.5% harmful revision vs. 10.3% for a plain re-ask | **Key design insight:** the *answer text itself* is a pressure channel. Quorum's debate passes peer answer text | — | Supports removing answer text from the channel. The experiment must include a speaker-free control |
| 10 | Ma et al. *Sycophancy Suppression Can Impair Rational Updating.* EMNLP 2026 Findings (per arXiv). [arXiv 2608.26511](https://arxiv.org/abs/2608.26511) **(A)** | Most anti-sycophancy methods cut valid updating too. The two behaviours share internal circuitry. Calls for *selectivity* | **The central framing:** a verification-gated channel is a selectivity mechanism outside the model | Their interventions are training and inference on a single model facing users | Strongest positioning: measure both unsupported yielding and rational updating |
| 11 | Parmar et al. *When Helping Hurts and How to Fix It: Multi-Agent Debate for Data Cleaning.* [arXiv 2606.02866](https://arxiv.org/abs/2606.02866) (preprint) **(R, partial; summarized by a tool)** | Finds "critique-induced confusion". **Evidence-gated generation:** the generator acts only on critic feedback that cites specific data evidence. A separate critic grounded in code execution gives +5.3 points (p<0.05); compliance drops from 95.3% to 60.3% | **Closest prior work** to "revise only on verified evidence" | Their gate appears to be an instruction to the generator (compliance is measured, so the LLM still decides); this was not confirmed from the full text. Domain is data cleaning. Evidence comes from execution, not a structural oracle. Not framed as sycophancy | "Evidence-gated revision" alone is **not novel**. Novelty must rest on a *deterministic* gate, the evidence-only channel, the selectivity measurement, and code-repository QA |
| 12 | *Free-MAD: Consensus-Free Multi-Agent Debate.* [arXiv 2509.11035](https://arxiv.org/abs/2509.11035); appears as Findings ACL 2026 (2026.findings-acl.1600) in search results, not opened **(A)** | Anti-conformity mode plus trajectory scoring; one round | Same goal, single round | No external oracle | Baseline candidate |
| 13 | *Minority Sentinel.* [arXiv 2606.29270](https://arxiv.org/abs/2606.29270) (preprint) **(A)** | Correlated errors bury correct minorities. A learned meta-classifier decides when to overturn the majority (+1.71 points) | Quorum *does* overturn majorities, but without principle (defect 2) | Learned vs. oracle-driven | Use their "minority truth" measure |
| 14 | Kim, Garg, Peng, Garg. *Correlated Errors in Large Language Models.* ICML 2025, PMLR 267. [arXiv 2506.07962](https://arxiv.org/abs/2506.07962) **(A)** | Across 350+ models, models agree 60% of the time when both are wrong; larger models are more correlated even across providers | Undercuts Quorum's provider-diversity assumption | — | The experiments must measure error correlation inside the panel |
| 15 | *Tool-MAD.* [arXiv 2601.04742](https://arxiv.org/abs/2601.04742) (preprint) **(A)** | Each agent gets a different retrieval tool; an LLM judge scores faithfulness and relevance | Tool-grounded debate | Evidence is judged by an LLM; revision is unconstrained | Related-work contrast |
| 16 | Yang et al. *Belief Engine.* [arXiv 2605.15343](https://arxiv.org/abs/2605.15343) **(A)** | Splits belief state from generation; LLM argument extraction plus a deterministic log-odds update | Structured belief state passed between agents, like belief cards | Evidence uptake is a parameter, not verified against an oracle | Prior work on structured belief exchange. "Belief cards" are not novel by themselves |
| 17 | Hu. *Silence Is Endorsement: Verification-Status Laundering.* [arXiv 2609.20211](https://arxiv.org/abs/2609.20211) **(A)** | Verification status is lost in handoffs, so approval rates jump (5%→60%, 9%→98%). Recommends carrying verification as structured state attached to each claim | Supports passing verification status *per claim* (Quorum passes only counts) | Diagnostic | Design support |
| 18 | Itkin. *Delayed Verification Destabilizes Multi-Agent LLM Belief.* [arXiv 2606.27409](https://arxiv.org/abs/2606.27409) **(A)** | Corrector agents with delay; instability thresholds | Verification inside multi-agent belief dynamics | Continuous correction, not a gate | Cite. Gating *before* exposure avoids the delay regime [I] |
| 19 | Du et al. *Improving Factuality and Reasoning through Multiagent Debate.* ICML 2024. [arXiv 2305.14325](https://arxiv.org/abs/2305.14325) **(A)** | Canonical free-text MAD | Baseline | — | Baseline |
| 20 | Chen, Saha, Bansal. *ReConcile.* ACL 2024. [aclanthology 2024.acl-long.381](https://aclanthology.org/2024.acl-long.381) **(A)** | Diverse LLMs; confidence-weighted voting; convincing explanations | Heterogeneous panel and confidence weighting, like Quorum | No oracle | Baseline |
| 21 | Sharma et al. *Towards Understanding Sycophancy in Language Models.* ICLR 2024. [arXiv 2310.13548](https://arxiv.org/abs/2310.13548) **(A)** | Sycophancy toward users and its origin in preference data | Defines user-directed sycophancy | — | Background |
| 22 | Laban et al. *Are You Sure? Challenging LLMs… FlipFlop Experiment.* [arXiv 2311.08596](https://arxiv.org/abs/2311.08596) (venue not verified) **(A)** | On average models flip 46% of answers when challenged; accuracy drops 17% | Protocol for user pushback | — | Reuse their challenger templates |
| 23 | Fanous et al. *SycEval.* [arXiv 2502.08177](https://arxiv.org/abs/2502.08177) (venue not verified) **(A)** | Progressive (43.5%) vs. regressive (14.7%) sycophancy | Selectivity metric for user pushback | — | Metric |
| 24 | *SycoBench-600.* Findings ACL 2026. [aclanthology 2026.findings-acl.1759](https://aclanthology.org/2026.findings-acl.1759/) **(A)** | Doubt, authority, and wrong-suggestion perturbations; correction selectivity | Metric design | Multiple-choice, not code | Metric design |
| 25 | Weng et al. *Do As We Do, Not As You Think* (BenchForm). ICLR 2025. [arXiv 2501.13381](https://arxiv.org/abs/2501.13381) **(A)** | Conformity benchmark | Background | — | Background |
| 26 | Ni et al. *LEVER.* ICML 2023 ([PMLR v202](https://proceedings.mlr.press/v202/ni23b)); Chen et al. *CodeT.* ICLR 2023 ([arXiv 2207.10397](https://arxiv.org/abs/2207.10397)) **(A)** | Choose among sampled programs with execution or tests | **Prior work for Quorum's actual default mechanism** (verifier-guided best-of-N in code) | Programs and execution vs. NL answers and structural claims | Rules out claiming verifier-weighted selection itself as new |
| 27 | Spracklen et al. *We Have a Package for You!* USENIX Security 2025. [link](https://www.usenix.org/conference/usenixsecurity25/presentation/spracklen) **(A)** | Existence hallucinations in code (5.2–21.7% of packages) | Quorum's oracle mainly catches existence hallucinations | — | Evidence that existence claims matter in practice |
| 28 | *SWE-QA.* [arXiv 2509.14635](https://arxiv.org/abs/2509.14635) (720 questions, 15 Python repositories) **(A)** | Repository-level QA benchmark | Candidate source of repositories and questions outside the decidable fragment | Free-form answers need a judge | Use for the "outside the fragment" condition |
| 29 | *A Scalable Communication Protocol for Networks of LLMs* (Agora). [arXiv 2410.11905](https://arxiv.org/abs/2410.11905) **(A)** | Mixes structured routines with natural language for efficiency | "Communication protocol" terminology | About efficiency and interoperability, not epistemics | Avoid a protocol framing that invites comparison to Agora/A2A/MCP. Frame as an *epistemic channel constraint* |
| 30 | Wang et al. self-consistency (ICLR 2023); Li et al. *More Agents Is All You Need* (TMLR 2024) **(K)** | Sampling plus voting | Matched-budget baselines | — | Required baselines |

**Search limits.** Most entries are read at abstract level. Only #1, and partly #11, were read in
the methods. The exact gate in #11 needs a full-text read before the paper cites it as "prompt-level".
The field moves fast: many relevant preprints appeared between June and September 2026, so a
re-search right before submission is needed. Not finding an identical system is **not** proof of
novelty.

---

## 5. Contribution assessment

| Candidate claim | Verdict | Why |
|---|---|---|
| "Quorum eliminates LLM sycophancy" | **Reject** | No evidence. Default path has no communication. The revision rule is prompt-only. Defects 1–5. "Eliminate" can only be true by construction on a decidable fragment |
| "Structured belief cards instead of free text are novel" | **Reject as stated** | Belief Engine (#16), ReConcile's structured inputs, Free-MAD scoring. Structure alone is prior art |
| "Self-calibrating confidence from verification history is novel" | **Reject / minor** | Close to sycophancy priors (#5) and reliability weighting. Used only in ties. Never evaluated |
| "Verifier-weighted cross-model selection improves repository QA" | **Plausible, incremental** | Prior: LEVER and CodeT (selection), MAD baselines. Needs matched-budget comparison with self-consistency on the strongest model. This could easily be a negative result |
| "Graph-verified claims rank above confident wrong ones" | **True but trivial** | That is what the sort does. Not a research finding |
| **C1. A deterministic, evidence-only channel** (peers and users can change an answer only through oracle-verified atomic claims; no answer text, confidence, identity, or rationale crosses) **removes harmful flips on the oracle-decidable fragment and keeps a measurable share of beneficial flips, beating prompt-only gates and anonymization on selectivity** | **Potentially publishable** (findings plus method) | Close prior: #11 (prompt-level evidence gate, data cleaning), #2 (anonymization), #10 (selectivity framing). The new part: a code-enforced gate with a real deterministic oracle; separating *which channel components* carry pressure (answer text, per #9; confidence; identity; rationale); measuring both flip directions under peer *and* user pressure in code QA. Confidence: medium. Expected reviewer objection: "by construction". Answer: the content is the coverage and beneficial-flip measurement, plus behaviour outside the fragment |
| **C2. Oracle coverage:** what fraction of answers to real repository questions can be decided by static structure, and how precise the oracle is (Python dynamic dispatch makes the call graph unsound) | **Publishable as part of C1**; weak alone | Needed to make C1 meaningful. New empirical knowledge if done on real question distributions (SWE-QA, usage logs) |
| **C3. Partial-oracle extension of the debate martingale result:** expected correction scales with coverage × precision × the chance that some peer emits the relevant verified atom | **Hypothesis**; small proposition at most | Builds on #1. Must be a modest formal statement plus an empirical check, not a headline |
| **C4. Failure taxonomy of verifier-weighted aggregation** (padding, fail-open, string-equality agreement, majority override) | **Useful workshop or short-paper content** | Concrete and reproducible, but specific to one implementation unless shown on other verifier-aggregation systems |

Classification: Quorum today is **useful integration and standard engineering** (provider
failover, parsing robustness, audit trail). C1 with C2 is the only **potentially publishable**
contribution. C4 is **incremental**.

---

## 6. Ranked paper directions

### D1 (recommended). *What may agents tell each other? An oracle-gated, evidence-only channel against peer and user sycophancy in repository QA*
- **Research question.** Which parts of an inter-agent or user message cause harmful revisions?
  Does a channel that carries only deterministically verified atomic claims remove harmful flips
  while keeping beneficial ones?
- **Hypotheses (falsifiable).**
  - H1: the hard gate gives a lower harmful-flip rate (HFR) than the prompt-only gate (today's
    Quorum prompt), anonymized MAD, and free-text MAD, under confederate peer pressure.
  - H2: the hard gate keeps at least 70% of free-text MAD's beneficial-flip rate (BFR) on
    decidable items. *Falsified* if the gate reproduces Ma et al.'s trade-off.
  - H3: removing answer text alone (no gate) closes most of the gap. This would make the
    deterministic gate unnecessary, an important negative outcome.
  - H4: under user pushback, the gate cuts regressive sycophancy and keeps progressive updating.
  - H5: outside the decidable fragment, the gated system performs like the no-communication
    baseline (no harm, no help).
- **Reuse.** Panel construction, failover, parsing, `verify_claims`, the graph, `QuorumDecision`
  persistence, and the `FakeLLM` test pattern for confederates.
- **Required changes.** See §7.2 (E1–E7).
- **Baselines.** Single strongest model; self-consistency on the strongest model at matched calls;
  majority vote over the panel; Du et al. MAD; MAD with anonymization (#2); MAD with the current
  Quorum prompt gate; Free-MAD or isolated self-correction (#6) if budget allows; current Quorum
  ranking.
- **Datasets.** (a) A *decidable* set generated from tree-sitter graphs of about 10 pinned Python
  repositories (prefer SWE-QA's repositories for comparability). Classes: existence (positive and
  negative), defined-in, direct call (positive and negative), import, usage count, arity, 2-hop
  reach. Labels are exact *for the classes where static analysis is sound*, with a manual audit of
  200 items. (b) A *non-decidable* subset of SWE-QA, judged by an LLM and validated on a
  human-labelled sample (report κ).
- **Metrics.** Accuracy; HFR (correct→wrong) and BFR (wrong→correct), following Qu et al.; a
  selectivity measure following Ma et al.; harm above the speaker-free floor (#9); unresolved rate
  plus a selective-accuracy curve; error correlation inside the panel; calls, tokens, and wall
  time.
- **Effort and cost.** About 3–5 weeks of engineering and analysis. API cost is driven by
  items × arms × pressure conditions × calls per arm. Example: 600 items × 6 arms × 3 conditions ×
  about 6 calls ≈ 65k calls, about 100M tokens at roughly 1.5k each. Open-weight models served
  locally or free tiers make this feasible but slow. Free-tier rate limits are the practical
  bottleneck (the logs show 503s and disabled keys). Confederate peers are scripted, so they cost
  nothing.
- **Threats.** Static-analysis labels are not ground truth for dynamic Python (restrict the
  classes and audit). Decidable questions may be "too easy" (report difficulty and initial
  accuracy per class, and include multi-hop). A "by construction" critique (answer with BFR and
  the non-decidable fragment). Provider drift (pin versions and dates, log everything).
  Confederate realism (also run natural disagreements).
- **Format.** Full paper for an ACL-family venue (ARR) or the ICML main track. A workshop paper is
  feasible earlier using a subset.

### D2. *Verifier-weighted aggregation across heterogeneous LLMs: when partial grounding helps and how it fails*
Evaluate the current mechanism (after the E1, E2, and E5 fixes) against majority vote and
self-consistency at matched budgets on the decidable set. Add the failure taxonomy (C4).
Short paper or workshop. Effort about 1–2 weeks. Risk: a likely null result versus
self-consistency on a strong model. That is fine for a findings or negative-results workshop.

### D3. *How much of repository QA can program structure decide?*
Coverage and precision study (C2). Use real question distributions (SWE-QA plus anonymized chat
logs, if the user approves), a typed claim extractor, and an oracle precision audit. Workshop or
short paper. It is a component of D1, so do it first.

### D4. *Debate with a partial oracle* (theory plus a small experiment)
Extend Choi et al.'s DCM model with oracle coverage *c* and precision *p*. Predict the expected
gain, and test with synthetic plus decidable items. Only worth doing with a theory collaborator.
Otherwise keep it as one proposition inside D1.

**Ranking (significance × defensibility × feasibility ÷ effort):** D1 > D3 (as D1's first
milestone) > D2 > D4.

---

## 7. Recommended direction: D1 roadmap

### 7.1 Protocol to implement [P]
Each agent's answer for a decidable item is a set of typed **atoms**, for example
`CALLS(foo, qux) = false`, plus optional free text. Verification is **tri-state**:
`verified | refuted | unchecked`, and it fails closed (unchecked never counts as verified).
The channel sends each agent only the *other* atoms whose state is `verified` or `refuted`. It
sends no answer text, model identity, confidence, or rationale.

**Revision gate:** a revised atom set is accepted only if every changed atom is (a) itself
verified, or (b) implied by a received verified or refuted atom. Otherwise the round-1 card is kept
and a *rejected-revision* event is logged.

User challenges go through the same gate: the user's assertion is parsed into atoms and verified
like any peer's. Aggregation runs over atoms (fixing defects 3 and 1). The final answer is the
oracle value where an atom is decidable, a majority over atoms otherwise, and "unresolved" when
tied.

### 7.2 Repository changes, prioritized [P]
| ID | Change | Research question / limitation | Files | Isolating experiment | Success / what a negative result means |
|---|---|---|---|---|---|
| E1 **Essential** | Tri-state, fail-closed verification in the Quorum path | Defect 4 inflates "verified" | `verification.py` (return status), `quorum.py:_verify` | Fabricated-claim injection: count how often unverifiable claims change the winner, old vs. new | Fabricated claims never count as verified. If rankings barely change, the defect was latent; report it anyway |
| E2 **Essential** | Answer-as-atoms, plus scoring only answer-relevant atoms (no padding) | Defect 1 | `quorum.py` (`_ANSWER_PROMPT`, `_parse`, `_rank`) | Padding-adversary confederate | Padding has no effect. If models can't produce atoms reliably (parse rate under 90%), the protocol needs a separate extractor, which adds LLM error |
| E3 **Essential** | Code-enforced revision gate with rejected-revision logging | Defect 5; the core H1/H2 | `quorum.py:_debate_round` | Arms "prompt gate" vs. "hard gate" | HFR drops by a CI-separated margin. If the prompt gate already gets HFR near 0, the hard gate is unnecessary (a publishable negative) |
| E4 **Essential** | Configurable channel content (answer text, identity, confidence, rationale, verified atoms) | H3; component attribution | `quorum.py` (peer summary builder) | Factorial or leave-one-in channel ablation | Find which component drives harm. If answer text dominates, that echoes #9 in a code setting |
| E5 **Essential** | Atom-level or normalized agreement instead of string equality | Defect 3 | `quorum.py:172,180` | Paraphrase test set | Paraphrases count as agreement |
| E6 **Essential** | More claim types: `CALLS`, `IMPORTS`, `DEFINED_IN`, `ARITY`, plus negative and closed-world versions marked unsound where dynamic dispatch applies | Oracle coverage (C2) | `verification.py` | Coverage and precision audit | Coverage numbers per class. Low coverage narrows the paper's scope (that is a finding) |
| E7 **Essential** | Offline experiment runner: pinned models and dates, temperature, seeds, confederate and user-pushback injection, JSONL logging of every card, flip, and rejected revision, tokens and latency | All RQs, reproducibility | New `tests/benchmarks/quorum_sycophancy/` (mirrors the existing benchmark layout) | — | — |
| V1 Valuable | Majority-over-atoms fallback when there is no verified signal | Defect 2 | `quorum.py:_rank` | Majority-override cases | Wrong-minority wins disappear |
| V2 Valuable | Record graph commit or hash and listing size in `QuorumDecision`; make the listing relevance-ranked, not an alphabetical prefix | Reproducibility; grounding bias | `quorum.py:_record,_repo_listing` | Large-repository items | Same accuracy on late-alphabet files |
| V3 Valuable | Calibration ablation (on/off; per repository vs. pooled) | Is calibration a component worth keeping? | `quorum.py:_model_calibration` | On/off | Likely negligible. If so, drop it from the paper |
| O1 Optional | Fix confidence 0.0 → 0.5 and the per-target verified count | Defects 6, 7 | `quorum.py:341,363` | Unit tests | — |

Per AGENTS.md, each change ships with unit tests that cover the **gating behaviour**
(safety-load-bearing) and must not edit the existing failing or legacy tests.

### 7.3 Evaluation protocol [P]
- **Arms:** A0 single agent; A1 self-consistency on the strongest model (matched calls); A2
  majority vote over the panel; A3 free-text MAD; A4 MAD with anonymization; A5 MAD with the
  current prompt gate; A6 evidence-only channel without the hard gate; A7 evidence-only channel
  with the hard gate (proposed). Plus the current Quorum ranking.
- **Pressure conditions:** none; confederate peers (wrong answer × {with or without speaker
  attribution, high or low confidence, persuasive rationale, padding}); natural disagreement;
  user pushback (wrong and correct challenges; FlipFlop or SycEval templates).
- **Panels:** homogeneous (3 samples of one model) vs. heterogeneous (3 providers), to measure the
  value of diversity and the correlation in the panel's errors.
- **Repetitions:** 3 seeds or samples per item and arm. Report run-to-run flip variance (#6 found
  37% spontaneous instability in a related setting, so a plain re-ask control is mandatory).
- **Statistics:** paired bootstrap 95% CIs over items; McNemar for paired accuracy;
  mixed-effects logistic regression for flips (random effects for item, model, and repository).
  Pre-register H1–H5 and the primary metric (HFR on initially correct, decidable items).
- **Budget fairness:** every arm reports calls, tokens, and latency. The headline compares A7 to
  A1 and A2 at matched calls. Quality-cost Pareto plot.
- **LLM judge (non-decidable fragment only):** two judges from different providers; validated
  against 150 human-labelled items; report κ and position or verbosity bias checks.
- **Failure analysis:** hand-code 100 rejected revisions and 100 accepted ones; residual harmful
  flips outside the fragment; oracle false positives and negatives.
- **Reproducibility:** release the item generator, pinned repository commits, prompts, all JSONL
  logs, and model IDs with access dates.

---

## 8. Paper outline (D1)
1. **Introduction.** Peer and user sycophancy; the martingale result (#1); the selectivity problem
   (#10). Contribution: a deterministic evidence-only channel plus a measured decidable fragment in
   code. *Figure 1: protocol diagram (a free-text channel next to the evidence-only gate).*
2. **Related work.** §4 condensed: MAD and its failures; conformity measurement; anonymization;
   evidence gating (#11); verifier selection (#26).
3. **Setting and protocol.** Atoms, tri-state oracle, gate, aggregation. A proposition: zero
   harmful flips on decidable atoms under a sound oracle, and the expected beneficial-flip rate as
   a function of coverage (C3). *Requires E1–E5.*
4. **Benchmark.** Decidable item generator and classes; label audit; non-decidable SWE-QA subset.
   *Table 1: classes, counts, label precision. Requires E6, E7.*
5. **Experiments.** *Table 2: accuracy, HFR, BFR, selectivity per arm under each pressure
   condition. Figure 2: channel-component ablation (H3). Figure 3: quality vs. cost Pareto.
   Figure 4: benefit vs. oracle coverage per class (H5, C3). Table 3: user pushback results (H4).*
6. **Analysis.** Error correlation in the panel; rejected-revision taxonomy; where the gate blocks
   *good* updates; when the protocol does worse than its strongest model.
7. **Limitations.** Static-analysis soundness; the fragment is code-specific; confederate
   realism; provider drift.
8. **Appendix.** Prompts, items, full CIs, the failure taxonomy of the current implementation (C4).

None of these tables or figures can be filled from existing evidence. All need new runs.

---

## 9. Claim–evidence matrix
| Claim | Code | Existing results | Closest prior work | Gap |
|---|---|---|---|---|
| The hard gate removes harmful flips on decidable atoms | Not implemented (E3) | None | #11, #1 (oracle), #2 | Implementation and the A5 vs. A7 runs |
| The gate keeps beneficial updating | Not implemented | None | #10 | BFR measurement |
| Answer text in the channel drives most of the conformity | Configurable channel needed (E4) | None | #9 | Channel ablation |
| A meaningful share of repository QA is decidable | Partial (3 claim types) | None | — | E6 plus a coverage study |
| Heterogeneous panels reduce correlated errors | Provider-diverse panel exists | None | #14, #7 | Homogeneous vs. heterogeneous arm |
| Verified-claim ranking beats confidence | `_rank` | Unit tests only | #26 | Real runs. Also fix padding first |
| Quorum is cost-effective | — | 31 logged calls, no outcomes | #6 | Pareto vs. matched baselines |
| Quorum "avoids sycophancy" (current docs) | Prompt only | None | — | **Remove this claim from the docs until evidence exists** |

---

## 10. Essential questions
1. **Which sycophancy?** User-directed (yielding to the person asking), peer-directed (agents
   yielding to each other), or both? This changes the benchmark and the headline. The
   recommendation assumes both, with peer pressure as the primary measure.
2. **Relation to the anchored-memory paper.** `docs/research/paper_plan.md` and today's earlier
   `conference_assessment_2026-10-07.md` exclude Quorum. Does this replace that paper or run in
   parallel? Each is a multi-week effort.
3. **Compute and models.** Which providers and keys can be used for about 50–100k calls? Is local
   GPU inference for open-weight models available? Free-tier limits decide feasibility.
4. **Unseen evidence.** Are there Quorum outputs outside the repository, such as
   `QuorumDecision` rows in Postgres or notes from the September runs? This pass could not inspect
   the database.
5. **Venue and timeline.** Verified: ARR's October 2026 cycle (deadline 12 Oct 2026, feeding
   NAACL 2027 and COLING 2027) is too close. ARR lists a January 2027 cycle for ACL 2027; its exact
   date is not yet published ([aclrollingreview.org/dates](http://aclrollingreview.org/dates)).
   ICML 2027 dates seen online (about 16 and 22 Jan 2027) are third-party estimates, not an
   official call. Is a January 2027 submission the target, or a workshop first?

---

## Appendix A: what was inspected
`AGENTS.md`; `backend/agents/quorum.py` (whole file); `backend/agents/verification.py` (whole
file); `backend/agents/api.py`; `backend/main.py` wiring; `backend/agents/llm.py` (tiers,
temperature); `backend/graph/schemas.py`; `tests/test_quorum.py`;
`tests/audit/codexa_claims/test_claim_quorum.py` plus its evidence JSON; `README.md`;
`CODEXA_CLAIMS_AND_PROOF_AUDIT.md` (Quorum sections); `docs/research/paper_gap_analysis.md`,
`paper_plan.md`, `novelty_matrix.md`, `conference_assessment_2026-10-07.md` (Quorum mentions);
`graph-viz` Quorum UI and API client; `.codexa/usage*.jsonl` (all `quorum*` rows);
`.codexa/keepalive/backend.log` (Quorum lines); `backend/data/jobs/*.json` (mentions only; no
Quorum results). `git log` has 2 commits that touch Quorum.

**Local verification:** `pytest tests/test_quorum.py tests/audit/codexa_claims/test_claim_quorum.py`
gave 25 passed. A probe with a scripted fake LLM reproduced defects 1–6, and a direct
`verify_claims` call reproduced defect 4.

## Appendix B: searches run (web, 2026-10-07)
Debate-or-Vote martingale; sycophancy and conformity in MAD (2025–2026); structured or
evidence-only communication protocols; Tool-MAD; verifier-gated belief update; Free-MAD;
sycophancy in coding assistants (SycoCode, SycoBench); harmful vs. beneficial revision;
repository QA benchmarks (SWE-QA, CodeRepoQA); speaker-free conformity floor; Active Provenance
Gate; Minority Sentinel; identity anonymization; Peacemaker or Troublemaker; CONSENSAGENT; Too
Polite to Disagree; MAD with code execution; LEVER and CodeT; correlated errors; Sharma
sycophancy and FlipFlop; ReConcile; Du et al. MAD; Agora protocol; SycEval; pre-exposure claim
verification; ARR 2027 dates; ICML 2027 dates; package hallucination; Talk Isn't Always Cheap;
verification-status laundering.

Not verified: full texts of most 2026 preprints; the exact gate mechanism in #11; SycoCode (a
GitHub repository only, no paper found); Active Provenance Gate (2609.31422, seen only in search
snippets, not cited above); author lists marked "et al." beyond those shown.
