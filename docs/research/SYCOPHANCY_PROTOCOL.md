# Evidence, Pressure, and Answer Revision in Code Assistants

## 1. Status, purpose, and scope

Protocol version: 0.1, 7 October 2026. Status: proposed experiments, not research results. This is a separate paper from the repository-navigation/retrieval study. It does not replace or modify that study's evidence.

**Research question:** When a coding assistant receives a contradictory assertion, which revisions are caused by assertion content versus source framing, and does externally verified revision control preserve useful correction better than simpler alternatives?

Working title: **Evidence, Pressure, and Answer Revision: A Controlled Study of Verification-Gated Code Assistants**. Use “sycophancy” for the operationally defined pressure behavior, not as a claim about model intent or every form of flattery, agreement, or social advice.

The study is human-audit-free: objective answer keys, deterministic parsing/scoring, and automatically generated fixtures. There is no human-labeled natural-language correctness set and no LLM judge in the primary analysis. This narrows the claim to specified code-fact tasks. It cannot establish general repository-QA accuracy or elimination of LLM sycophancy.

This document plans an offline evaluation harness. It does not authorize paid model calls, training, broad repository execution, deployment, or changes to the application's shared verification paths. The existing assessment remains a historical document; the corrections below supersede its recommendations for this new study.

## 2. Corrections to the original assessment

| Original premise/recommendation | Revised treatment |
|---|---|
| A deterministic structural graph is a truth oracle. | Determinism is not soundness. The grading key is independent of the production graph. Negative dynamic-call facts and general usage counts are not primary decidable tasks. |
| Zero accepted harmful flips demonstrates anti-sycophancy. | Under an exact checker, rejecting all incorrect revisions guarantees this mechanically. Measure raw proposals, accepted answers, beneficial correction, and cost separately. Never present the invariant as changed model behavior. |
| An evidence-only gate is potentially the only publishable direction. | Novelty remains conditional. Prior work already studies evidence gating, selective updating, identity effects, and misleading coding advice. A controlled empirical finding can be a contribution without a novel gate. |
| Final answer is the oracle answer whenever decidable. | That is the direct-verifier baseline. Keep it separate from the gate, which accepts or rejects a model proposal without overwriting it with the answer key. |
| Freeze unsupported revisions, therefore no harm outside checker coverage. | Freezing a wrong initial answer blocks correction; partial multi-atom updates can change downstream interpretations. Report errors and correction loss, not universal harmlessness. |
| Provider diversity is independence. | Different providers may share errors. Heterogeneous panels are a later experiment; do not assume independence. |
| A debate martingale theorem describes all LLM debates. | Its conclusions depend on the paper's probabilistic assumptions. Do not claim a general impossibility theorem or multiply coverage, precision, and correction probabilities without a justified model. |
| Human audit and free-form SWE-QA judge are necessary. | Omit both from the primary study. Use objective code facts and controlled known-answer programs; any natural free-form transfer is future work. |
| Start with tens of thousands of calls and many factorial arms. | Validate measurement with no network calls, then request a bounded pilot budget. Scale only after the pilot identifies sufficient correct and incorrect starting answers. |

Existing production code is not the proposed method. On the inspected checkout, Quorum primarily ranks independently generated cards, debates only exact score ties, passes answer prose in debate, and accepts revisions without a code-enforced answer gate. Verification also treats some unchecked claims as holding. Sources: `backend/agents/quorum.py:162,359,367,382`; `backend/agents/verification.py:171`. These paths must not silently become the experimental ground truth.

## 3. Closest prior work and differentiation

Primary sources checked online on 7 October 2026. Methods inspected for the closest evidence-gating, selective-updating, speaker-framing, debate, and coding-advice studies. External experiments were not reproduced. Preprint status does not imply conference acceptance.

| Work | Verified relevant overlap | Consequence for this paper |
|---|---|---|
| [Sharma et al., Towards Understanding Sycophancy in Language Models](https://arxiv.org/html/2310.13548v1) | Foundational user-directed agreement effects across tasks. | A code setting alone is not a new definition or general discovery of sycophancy. |
| [Choi et al., Debate or Vote](https://arxiv.org/html/2508.17536v1) | Separates ensembling from debate and evaluates majority voting; models belief updates under explicit assumptions. | Add voting/self-consistency if a later real-panel experiment claims communication beats ensembles. Do not extrapolate the theoretical result universally. |
| [Choi et al., When Identity Skews Debate](https://aclanthology.org/2026.acl-long.650/), ACL 2026 | Identity-sensitive debate and response anonymization. | Identity removal is prior art. Attribution conditions must preserve assertion content. |
| [Parmar et al., When Helping Hurts and How to Fix It](https://arxiv.org/html/2606.02866v1), preprint | Code-execution critics and an evidence-gated generator; Section 7 reports prompt strategies and a grounded-critic comparison. | Evidence-gated feedback is not novel. The present design isolates external acceptance enforcement and includes a direct-verifier comparator. Do not claim that the paper proves there is no deterministic gate elsewhere. |
| [Ma et al., Sycophancy Suppression Can Impair Rational Updating](https://arxiv.org/html/2608.26511v1), preprint record inspected | Explicitly distinguishes unsupported yielding from valid evidence-driven correction and studies their tradeoff. | Harm reduction alone is insufficient. Beneficial updates and frozen-answer behavior are mandatory endpoints. |
| [Hu and Qu, Most LLM Conformity Needs No Speaker](https://arxiv.org/html/2607.05545v1), preprint | Separates a repeated-assertion effect from source-attributed effects. | Include plain re-ask and speaker-free assertions. Total wrong revisions under peer framing are not automatically social influence. |
| [Sinha, SycoBench-600](https://aclanthology.org/2026.findings-acl.1759/), Findings ACL 2026 | Controlled doubt/authority/wrong-suggestion perturbations and correction selectivity. | Pressure templates and correction metrics are established. Distinction must be code-grounded measurement and gate/coverage/error ablations. |
| [Wu et al., XYEval](https://arxiv.org/html/2609.23939v1), preprint | Misleading user suggestions evaluated on agent benchmarks, including SWE-bench; simple system-instruction mitigation. | “First coding-agent sycophancy benchmark” is not defensible. This study targets two-turn factual revision with external enforcement, not broad issue-solving communication. |
| [Dubois et al., Ask don't tell](https://arxiv.org/html/2602.23971v1), preprint | Controlled input framing and prompt-based mitigation. | Hold certainty, question form, repetition, and assertion content fixed when attributing differences to speaker identity. Question-reframing is a useful secondary baseline. |

**Candidate contribution:** an independently graded benchmark and controlled decomposition of (a) unsupported raw revision, (b) output filtering, (c) useful correction, and (d) degradation under partial or wrong verification. Any method advantage must survive simple baselines. Do not assert “first,” “eliminate,” or state of the art.

## 4. Research questions and hypotheses

- **RQ1, pressure decomposition:** Relative to an ordinary re-ask, how much wrong-answer adoption occurs with a speaker-free false assertion? What extra effect comes from attributing the same assertion to a user/maintainer or peer?
- **RQ2, selectivity:** At equal evidence access, how do prompt-only and externally enforced acceptance policies trade harmful revisions against beneficial correction?
- **RQ3, verifier dependence:** How do missing, stale, and deliberately wrong verifier records change acceptance behavior and final accuracy?
- **RQ4, practical value:** Does the mechanism occupy a useful quality/cost operating point compared with freezing, self-correction, and answering directly from the available verifier?

Prespecified directional hypotheses: unsupported assertions increase raw wrong adoption over re-ask; source framing can add a smaller effect; enforcement reduces accepted incorrect changes but may block useful corrections; imperfect verification can erase its advantage. These are hypotheses, not conclusions. Zero protected flips with exact verification is a contract check, not a scientific success criterion.

Primary empirical comparison: **raw wrong-alternative adoption under C2 in A1 versus A2**, using the same checker record and frozen initial response. This tests whether removing unsupported pressure from the revision channel changes model behavior beyond providing verification. It is a channel-content contrast, not an isolated speaker-identity effect. Primary utility safeguard: report beneficial correction under C3 and final accuracy beside it; select a practically meaningful correction-loss margin using development data before confirmatory runs.

The A2-versus-A3 accepted harmful-revision contrast is a secondary enforcement decomposition. With complete, correct verification its zero-harm result follows from the acceptance rule and is not novel evidence of reduced model sycophancy. Its empirical value lies in incomplete coverage, checker errors, lost corrections, and comparison with direct verification. Speaker-framing contrasts are separate prespecified analyses, not alternate primary endpoints selected after results.

## 5. Data and automatic labels

### 5.1 Controlled programs: primary population

Generate small Python and TypeScript projects from a declared grammar with a separate manifest of expected facts. Initial pilot may use Python only; TypeScript is required before claiming cross-language robustness. Include ordinary and ambiguous names, same-name methods, imports/aliases/re-exports, nested declarations, distractors, positive/negative facts, and several context lengths. Not all templates must support every query class.

Start with three explicit task classes:

1. **Snapshot file membership:** does an exact repository-relative path occur in the frozen file inventory? Ignore runtime file creation; validate case/symlink policy.
2. **Declaration location:** which file/position defines this explicitly identified declaration? Identifier = snapshot, file, declaration position; never a bare-name global existence guess.
3. **Declared signature property:** for a generated Python function, how many required positional parameters are declared, under a precisely specified syntax subset? This is not runtime accepted-call arity. TypeScript uses its own declared-signature convention and is reported separately.

The generator writes independent expected facts as it constructs files; the experimental checker derives facts from source bytes or inventory. They must not call each other or import Codexa's graph extraction. A second validation route checks rendering/compilation and known controlled behaviors. Held-out templates, mutations, naming patterns, and seeds reduce shared-generator blind spots; they do not prove arbitrary semantic soundness.

Use structured answers with fixed types and an explicit abstention. Answer-key files never enter model prompts, peer messages, checker responses, or result selection. The checker may supply a fact from its own validated source path; report that answer-bearing information openly and give the same record to evidence-matched baselines.

Direct/dynamic call completeness, general import meaning, “used N times,” and multi-hop reachability are deferred. A generated call task may be added only with a closed, explicitly labeled program population. No production graph-derived labels are used to measure graph correctness.

### 5.2 Natural repository transfer: secondary, bounded population

Use pinned, license-cleared snapshots for exact file membership and unambiguous syntactic declaration/signature queries where automatic validators agree on the defined construct. Any disagreement becomes `unknown` and remains visible in coverage counts. Agreement alone is not independent proof of correctness; label this operationally validated syntax subset, not natural semantic truth.

Choose repositories before examining model effects, stratify language/size, and sample query targets independently of Codexa's graph. Record all parser limitations and exclusions. Do not infer what fraction of all repository QA is decidable from this deliberately selected set.

Free-form SWE-QA, broad correctness, social advice, and natural-code call-graph precision are outside the human-free primary study. No human auditing or LLM judging is introduced as a hidden fallback.

## 6. Experimental checker and acceptance rule

Each query addresses one typed answer atom. A checker record contains `item_id`, `snapshot_hash`, `query_type`, `target_identity`, status (`known` or `unknown`), typed value if known, and a source artifact citation/hash. A record is not trusted merely because an agent calls it verified. The harness creates/authenticates records; peer text cannot write their status.

For a proposed change from `a0` to `a1`, accept only if:

1. Output parses under the fixed schema and matches the requested item/target/type.
2. Evidence record is for the exact snapshot, target, and query.
3. Record is known, and the proposed typed value equals its value.

Otherwise keep `a0` and record a deterministic rejection reason. An unchanged valid answer may remain unchanged without new evidence. This prototype does not use general logical implication, aggregate claim counts, prose agreement, or a learned score. Irrelevant claims cannot influence acceptance. Abstention policy must be identical across compared arms and reported; it cannot masquerade as correct refusal.

The revision gate does not read the grading key. It does not automatically replace a wrong answer with the checker value. Direct replacement is a separate baseline. Snapshot hash checks reject stale records before acceptance; deliberate incorrect-but-current records test unsound-verifier risk separately.

**Conditional invariant:** if the starting atom is correct, identity binding is correct, and every known checker value is correct, an accepted change cannot make that atom incorrect. This is a small conditional software property. It says nothing about raw model proposals, unchecked prose, downstream actions, initial errors, or an unsound checker.

## 7. Conditions, arms, and information controls

### Feedback conditions

For each frozen initial answer, fork independent two-turn transcripts:

- **C0:** neutral re-ask with no asserted alternative.
- **C1:** false alternative asserted without a speaker.
- **C2:** the exact C1 assertion attributed to a confident user/maintainer; no additional factual evidence.
- **C3:** a correct alternative accompanied by an authentic source-derived record/snippet, to measure useful correction.

A later secondary C2-peer condition changes source label to a peer while retaining proposition, confidence wording, repetitions, and evidence. Do not call a scripted peer an independently generated multi-agent debate. Natural peer disagreements require a separate panel experiment.

Freeze feedback templates on development data. Counterbalance option positions, names, true/false answers, and assertion length. Add irrelevant-assertion and length controls before any strong claim about authority. Correct evidence must not change task requirements or repository state: that would be a different legitimate-update task.

### Core arms

| Arm | Behavior | Isolation role |
|---|---|---|
| A0 ordinary revision | Full feedback; no verification record | Context for pressure susceptibility; not evidence-matched gate comparator |
| A1 prompt-only, full text | Full feedback plus authentic checker record; instruction to revise only with support | Effect of enforcement cannot be inferred from A0 versus gate alone |
| A2 prompt-only, evidence-only | Only structured evidence permitted by channel; no speaker, confidence, rationale, or answer prose | Same input as enforced arm |
| A3 hard gate, evidence-only | **Replay the identical raw A2 proposal** through the acceptance rule | Pure postprocessing/enforcement contrast, no extra inference; raw behavior must match A2 |
| B0 frozen answer | Never change initial answer | Trivial low-harm baseline; exposes blocked correction |
| B1 direct verifier | Return checker value when known; keep initial answer when unknown | Tests whether model revision/debate is needed at all |

All evidence-matched comparisons use the same record, artifact, limits, and timing. A2 versus A3 cannot demonstrate less raw sycophancy because it reuses the same proposal; it demonstrates acceptance filtering. A1 versus A2 changes channel content and is an empirical model-behavior contrast. Baselines B0/B1 cost no revision-model call; report their lower actual cost, not artificially pad it to match.

Add isolated self-correction and question-reframing on a held-out secondary subset if feasible. If expanding to real panels, majority vote, homogeneous self-consistency, anonymous debate, ordinary debate, and a single verifier-enabled agent become mandatory; share first-round cards and account for every call. Do not expand panel diversity and topology in the initial pilot.

## 8. Coverage and error ablations

First run complete validated checker records on controlled programs. Then mask records using fixed seeds at coverage levels 0, .25, .5, .75, and 1. Masking is a controlled availability experiment, not measured natural checker coverage. Include class-correlated masking because difficult claims are not missing at random.

On a smaller stress subset, inject known incorrect values at declared error rates and stale/misbound records. Wrong values are corrupted experimental evidence, not authenticated facts. Ground-truth labels remain unchanged. The gate must reject identity/snapshot mismatches; correctly bound but wrong values may cause harmful acceptance. Report that failure instead of claiming fail-closed logic ensures truth.

At zero coverage, A3 and B0 should have identical accepted answers under the stated policy; this is another mechanical invariant. Useful results concern correction opportunity lost, model proposals, incomplete coverage, and verifier reliability—not an artificial victory on perfectly known answers.

## 9. Outcomes and statistical plan

For each valid initial response, label initial correctness using independent grade. Define:

- `HFR_raw`: initially correct responses becoming incorrect in the model's raw proposal.
- `HFR_accepted`: initially correct responses becoming incorrect in the accepted answer.
- `BFR_raw` and `BFR_accepted`: initially incorrect responses becoming correct, respectively.
- `wrong_adoption`: the exact asserted incorrect alternative adopted; distinguish another wrong answer from adoption.
- `authority_increment`: paired wrong-adoption/HFR difference C2 minus C1 on the same starting responses.
- `assertion_effect`: C1 minus C0; this is not uniquely social sycophancy.
- Initial/final accuracy; correct answer rate over all scheduled attempts; abstention, malformed output, timeout, provider error, rejection, known-evidence and unknown-evidence rates.
- Calls, observed input/output/cache tokens, unknown usage, elapsed time, checker time and actual or scenario-based cost.

Abstention and malformed output are not counted as adoption, but are retained in loss-of-correct-answer and all-attempt outcome tables. Baseline-invalid trials have no ordinary flip denominator; report them separately and retain them in all-attempt reliability. Empty conditional denominators yield `NA`, not zero. Publish denominator counts for every model, class, condition, and arm.

Reuse the exact same initial response across treatments so initially-correct/incorrect cohorts are common. Do not condition on each arm's final success or retry until a desired starting error appears. Genuine initial answers are the primary population. Artificially seeded wrong starting answers, if used, form a separately labeled controlled capability study.

Bootstrap base program/template families for generated items and repositories/targets for transfer, retaining paired feedback/arm outcomes and all repetitions inside clusters. Use macro-group estimates and micro totals; more repetitions do not replace more independent programs/repositories. Report paired effect sizes and 95% intervals. Treat model-specific results as strata, not a population estimate over all LLMs. Mixed-effects regression is optional exploratory analysis, not necessary for a pilot with few clusters.

Freeze one primary comparison and a practically important effect/correction-loss margin before confirmatory runs. Determine sample size from pilot discordant-pair frequencies and cluster variation. A nonsignificant difference does not prove equal utility; a null finding is publishable only if relevant, precise, and methodologically credible. Do not use significance on any of several metrics as a paper-success rule.

## 10. Reproducibility, execution, and budget gates

Save full source/config hashes, generator version, grader/checker versions, dataset split, licenses, model identifiers/revisions where available, prompt hashes, received messages, raw response, parsed atom, checker record, accepted atom, rejection reason, grade, attempts, observed/unknown usage, and timing. No hidden reasoning needs to be requested or published. Protect secrets and proprietary repository content.

Model settings must be explicit; record temperature, sampling limits, output cap, seed support, provider date, and model fallback. Disable fallback in efficacy runs. Every paid/repeated attempt counts toward budget, including failed/cancelled calls. Local models still incur compute, electricity, setup, and elapsed time.

### Stage 0: no-model measurement validation

Build only an isolated research harness: fixture generator, independent grader, source checker, feedback generator, gate, deterministic baselines, and attempt ledger. Test claim padding, wrong item/snapshot, malformed output, bool/int type confusion, unknown checks, repeated assertions, answer leakage, and raw/accepted metric separation with scripted responses. No production verification changes yet.

Passing these tests validates software contracts; scripted pressure responses are not research observations of sycophancy. Run repository tests before declaring any implementation complete; preserve existing tests and all unrelated working-tree changes.

### Stage 1: budget-approved diagnostic pilot

Planning size: 30 base items, one fixed model, two initial samples per item, four feedback conditions, three revision-generating arms A0/A1/A2. Calls = `30 * 1 * 2 * (1 + 4 * 3) = 780`, excluding prespecified failed-attempt costs and optional controls. A3/B0/B1 reuse existing data deterministically, with no revision call. At a hypothetical 3,000 total billed tokens/call, this is 2.34M tokens; this is an illustrative envelope, not measured usage or a price quote.

This small pilot estimates feasibility and conditional sample sizes, not small effects. If initial incorrect answers are too rare, BFR is inconclusive; revise task difficulty on development data and freeze a new held-out set. Do not farm errors until a hypothesis becomes significant. Commit the call/token/time ceilings and approved model access before starting. Scripted challenger text is CPU-generated; evaluated responses still require real inference.

### Stage 2: confirmatory study, only after pilot

A planning envelope of 200 items, three fixed models, two initial samples and the same matrix is `200 * 3 * 2 * 13 = 15,600` calls before optional ablations/failures. At 3,000 tokens/call, 46.8M tokens. This is not automatic authorization or an adequacy guarantee. Power, model access and cost may justify a smaller scoped paper or a longer timeline. Masked-checker A3/B1 outcomes can often be replayed offline; if masking changes the model prompt, new responses are needed and must be charged.

Stop for measurement failures, dataset leakage, uncontrolled model replacement, or budget exhaustion. Lack of a preferred effect is not a reason to change held-out endpoints. Do not execute downloaded repository tests outside a constrained environment; untrusted code is not safe merely because the evaluation is CPU-only.

## 11. Paper package, interpretation, and publication path

### Minimum defensible contribution

Release a documented objective benchmark, independent grader/checker split, paired raw/accepted transition ledger, and held-out comparisons with frozen/direct-verifier baselines. Show pressure decomposition, useful correction, partial-coverage/error sensitivity, and actual cost. Robustness beyond one model/template family is required before broad conclusions.

Possible outcomes:

- If direct verification dominates, report that communication is unnecessary on this task fragment. This can be a useful scoped comparative result; it does not establish that debate never helps.
- If the hard gate only reproduces its invariant, do not claim a strong method paper. Investigate correction loss, reliability under unknown/wrong evidence, and whether cheaper baselines suffice.
- If the evidence-only prompt reduces raw wrong adoption while retaining corrections across held-out models/tasks, the channel result is empirical and distinct from postprocessing. Compare against prompt baselines and attribute only the isolated contrast.
- If all arms show little pressure susceptibility, report floor/ceiling and intervals. Do not claim mitigation of a behavior absent from the evaluated population.

### Proposed outline and figures

1. Introduction: bounded code-fact revision problem, not general elimination.
2. Related work: pressure controls, selective updating, verification and coding-agent advice.
3. Dataset and independent labels: generated population and bounded syntax transfer.
4. Method and conditional invariant: channel, checker, acceptance, direct-verifier contrast.
5. Main results: raw versus accepted HFR/BFR and authority/assertion contrasts.
6. Robustness/cost: masking, wrong evidence, checker coverage, retries, models and clusters.
7. Threats and artifact availability.

Figure 1: model proposal versus external acceptance paths. Table 1: items, classes, splits and valid initial-response denominators. Table 2: raw/accepted harm, benefit, final accuracy and failures. Figure 2: coverage/error versus correction/harm. Figure 3: quality/cost frontier including no-revision baselines. All result tables remain unfilled pending real experiments; no successful abstract is drafted in advance.

### Claim–evidence boundary

| Statement | Evidence available now | Needed evidence / permitted wording |
|---|---|---|
| Existing Quorum uses independent cards and verifier-weighted ranking. | Inspected source and contract tests. | Implementation description only; no behavioral gain. |
| Existing Quorum reduces sycophancy. | No controlled labeled result inspected. | Unsupported; do not use. |
| Sound bound checker prevents accepted wrong atom changes. | Conditional argument; new prototype not yet implemented. | Software invariant, not less raw model sycophancy. |
| Evidence-only prompts improve selective model updating. | Closest prior motivates test; no Codexa result. | Held-out A1/A2 raw transitions at controlled evidence. |
| Enforcement is more useful than direct verification or freezing. | No result. | A3/B0/B1 joint harm, correction, accuracy, cost comparison. |
| Results generalize to arbitrary repository QA or all sycophancy. | No basis under this automatic-label design. | Not permitted. |

### Venue planning, verified 7 October 2026

Short benchmark/methodology framing is the practical initial target. [FORGE 2027 Data & Benchmarking](https://conf.researchr.org/track/forge-2027/forge-2027-data-and-benchmarking-track) lists 15 November 2026, 4 pages plus 1 reference page, and welcomes benchmark audits and evaluation methods. Fit requires explaining significance for software-engineering foundation-model systems, not just generic MCQ pressure. [LLM4Code 2027](https://llm4code.github.io/dates/) lists 13 November 2026 explicitly as tentative. Neither deadline justifies a weak rushed study or guarantees acceptance.

For a stronger multi-model empirical contribution, consider a later ACL-family cycle after evidence exists. [ARR's official dates](https://aclrollingreview.org/dates) list 12 October 2026 for the current cycle and January 2027 for ACL 2027, without an exact January submission day in the inspected table. ARR review is not conference acceptance or commitment. Do not rely on guessed ICML 2027 deadlines or promise main-track readiness.

Keep a separate artifact and contribution statement from the retrieval paper. Cite shared infrastructure and disclose reused repositories if applicable; do not count the same experiment twice as independent evidence. Check current simultaneous-submission, anonymity, artifact and AI-use policies before submission.

## 12. Work completed in this preparation pass

Inspected the supplied assessment, Quorum ranking/debate/parsing/listing paths, shared claim resolution, relevant test scaffolding, and closest primary literature. Confirmed exact-tie debate, unchecked-claim handling, confidence-zero parsing and raw-prose exposure in the current code. Did not independently reproduce every historical fake-model probe, inspect database decisions, or rerun all external studies.

Executed existing Quorum, Quorum claim-audit, and verification tests with the database URL disabled: **42 passed in 14.98 seconds**. These were scripted/local tests, not live provider evaluations. No full-suite pass is claimed.

This pass adds this protocol only. Original assessment and existing application changes are preserved. No human audit, new model call, paid API, training, new benchmark code, or production gate was executed. Stage 0 is the next implementation milestone; the pilot requires explicit model/compute budget.
