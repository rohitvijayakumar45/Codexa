# Pre-submission review (FORGE 2027 Data & Benchmarking)

Acceptance cannot be guaranteed. This document records what was checked, what was fixed, and the residual risks.

## Venue fit (checked against the official track description, via search index)
- The track solicits "new or improved datasets, benchmarks, evaluation methodologies, tools, empirical findings, replications, or critical analyses of current practices". This paper is a benchmark, an evaluation methodology, and a replication.
- Stated criteria (FORGE 2026 wording): relevance to the FORGE audience, originality, clarity, and usefulness of tools and datasets.
- FORGE 2026 Data & Benchmarking reportedly accepted 9 of 10 submissions (search snippet; unverified, and a track that small can change).
- Format: IEEE conference template, 4 pages + 1 page of references, double-anonymous. Compiled: 4 pages in total, no overfull boxes.

## Numbers
- Every decimal number in `main.tex` was checked automatically against `results/main/analysis/report.md`. The exceptions, now committed and reproducible, are:
  - 85.3× [56.9, 126.8] and 3.0× [2.4, 4.0] in `results/main/analysis/original_method.json` (`nb/replicate_original.py`);
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
| Graph-derived query sampling biases evaluation | CodeNib states its queries come from the static graph | We quantify it |
| grep is a strong baseline | Sen et al. 2026 | Consistent |
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
