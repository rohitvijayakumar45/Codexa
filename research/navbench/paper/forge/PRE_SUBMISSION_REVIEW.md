# Pre-submission review (FORGE 2027 Data & Benchmarking)

Acceptance cannot be guaranteed. This document records what was checked, what was fixed, and the residual risks.

## Venue fit (checked against the official track description, via search index)
- The track solicits "new or improved datasets, benchmarks, evaluation methodologies, tools, empirical findings, replications, or critical analyses of current practices". This paper is a benchmark, an evaluation methodology, and a replication.
- Stated criteria (FORGE 2026 wording): relevance to the FORGE audience, originality, clarity, and usefulness of tools and datasets.
- FORGE 2026 Data & Benchmarking reportedly accepted 9 of 10 submissions (search snippet; unverified, and a track that small can change).
- Format: IEEE conference template, 4 pages + 1 page of references, double-anonymous. Compiled: 4 pages in total, no overfull boxes.

## Numbers
- Every decimal number in `main.tex` was checked automatically against `results/main/analysis/report.md`. The exceptions, now committed and reproducible, are:
  - 85.3× [57.2, 126.9] and 3.0× [2.4, 4.0] in `results/main/analysis/original_method.json` (`nb/replicate_original.py`);
  - the 1.5 margin (from FREEZE.md);
  - 2.3 (= 1/0.44);
  - arXiv identifiers.
- The original 85.8× lies inside the replication interval.

## Consistency with published work
| Our finding | Published evidence | Agreement |
|---|---|---|
| Graph tools' recall on observed Python calls 0.64–0.75 | PyCG (ICSE 2021): ≈70% recall for static Python call graphs | Consistent |
| Lexical search ≥ graph tools on recall; graph close behind | Codebase-Memory: graph agent 83% vs grep-and-read explorer 92% quality | Same direction |
| Language-server JSON costs more tokens than grep or graph | Xu 2026: LSP costs tokens on localization | Consistent |
| Graph-derived query sampling biases evaluation | CodeNib states its queries come from the static graph | We quantify it, adjusted for composition |
| (context only) grep beats vector retrieval for agent memory | Sen et al. 2026: LongMemEval *conversation* retrieval, not code | Not direct evidence; cited only as context |
(Prior-work statements are from abstracts and search snippets. Read the full texts before submission.)

## Mock review: likely objections and responses (fixes applied)
| # | Likely objection | Response / fix |
|---|---|---|
| 1 | "No foundation model in the loop; is this FORGE-relevant?" | Intro now frames the tools as MCP context providers for FM agents, where payload enters the model's context. The model-free design is a stated strength: deterministic, with no 30× run-to-run variance. |
| 2 | "One tool is the authors' own" | Disclosed (anonymously) in the introduction and in Threats; G1's failures are reported in full. |
| 3 | "Is 'LSP JSON' really native output?" | Method states it is the LSP `Location` JSON rebuilt from the returned URIs and ranges. |
| 4 | "Replication number lacks uncertainty" | 95% CI added; the original value lies inside it. |
| 5 | "Synthetic fixtures are toy code" | Three layers; fixtures are used only for pattern-level correctness. Natural-repository and runtime layers are reported separately; limits stated. |
| 6 | "Selection of 17 repositories" | Criteria fixed before results; purposive, not random (stated). |
| 7 | "Primary contrast conditions on joint completeness" | Complete-answer rates are reported next to every ratio. |
| 8 | "Tokenizer substitute" | Stated; validated against known ids; a local tiktoken cross-check is recommended. |
| 9 | "Post-freeze change" | Disclosed with before/after numbers; pre-fix results released. |

## External review, round 3 (applied)
| # | Point | Verdict | Change |
|---|---|---|---|
| 1 | The most complete graph tool has a large precision advantage (0.98 vs 0.35) | Correct | Abstract, Q3 and recommendations now report the token–recall–precision trade-off (F1 0.95 vs 0.50). |
| 2 | Jointly complete subsets are selected on success and differ by arm | Correct | n per arm stated (64/64/127/79/128 of 160). Full-workload ratio added (1.01 [0.93, 1.09]). Wording says "jointly complete targets", not "matched operating points". |
| 3 | S-cond vs S-ind differences may be target composition, not conditioning | Partly correct | Post-stratified on repo × kind × fan-out. G1, the conditioning tool, keeps +32/+42 points of answer rate. Its recall gap shrinks to +0.13, with CIs reaching 0. The language server shows no difference (−1 [−5, 3]), and the other graph tool shrinks to +8–9. The earlier claim "sampling from the graph's own edges" for all graph tools was wrong for codebase-memory, because S-cond uses G1's edges; it has been corrected. While checking this, a **scoring bug** was found and fixed: 76 S-ind targets also drawn into S-cond had been dropped from S-ind. See FREEZE.md; S-ind numbers changed, conclusions did not. |
| 4 | Normalised-form results should be shown | Correct | Location-form column added to Table III; form ratios in the text (graph tools 0.24–0.28 of rg). Caveat: different units (callers vs occurrences). |
| 5 | Caller-level credit may reward comment/declaration hits inside a caller | Checked | Strict variant: rg/LSP recall changes by at most 0.01, no contrast changes. A human audit was not done (author decision: fully automatic); stated as a limitation. |
| 6 | codebase-memory's paper evaluates v0.5.5, not v0.5.7 | Correct (search-index evidence; arXiv blocked here) | v0.5.5 was built and run on the frozen targets. It matches v0.5.7 on all fixture queries; on natural code it differs on 5.8% of queries, about as often as v0.5.7 differs from its own re-run (5.3%; current version 0.4%). The aggregates agree within 0.03, so the paper uses one row, "v0.5.5/7" (`results/main/supplement_cbm_versions/`). Current is pinned to `bf93f0b7` in the paper. |
| 7 | Artifact link is a placeholder | Correct | Still an author action (below). |
| 8 | 1.03 reads as an equivalence claim; 0.65 rule unclear | Correct | "No evidence of a substantial saving (not an equivalence test)"; 0.65 [0.62, 0.672] explained against 1/1.5 = 0.667. |
| 9 | Xu 2026 overlap; Sen et al. is conversation memory; 85× is G1's own definition, not codebase-memory's 10× | Correct | Related work and Q1 reworded accordingly. |

## Residual risks (not fixable by editing)
- Reviewers may prefer an agent-level outcome (resolve rate or answer quality). Mitigation, if wanted: a small agent slice, which needs an API budget.
- The novelty margin over Xu 2026 and CodeNib depends on reviewers accepting "model-free, cross-tool, independent labels, sampling quantified" as sufficient.
- Anonymity: the searchable "85.8×" figure and G1's README could identify the authors.
- Citation details: CodeNib authors still marked VERIFY.

## Before submission (author actions)
1. Read the full texts of [4], [5], [6], [7] and confirm every statement attributed to them.
2. Fill in CodeNib's authors.
3. Create the anonymized artifact (anonymous.4open.science) and replace the `XXXX` link.
4. Decide on the "85.8×" wording for anonymity.
5. Confirm the deadline and submission system on the official FORGE page.
