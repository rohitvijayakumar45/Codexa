> **Superseded.** The submission text is `forge/main.tex`. Numbers in this draft predate the post-freeze scoring fix and the round-3 review changes (see `../FREEZE.md`); do not cite them.

# What Does "N× Fewer Tokens" Measure? Baselines, Sampling and Output Format in the Evaluation of Repository-Navigation Tools

*Draft. Every number is from `research/navbench/results/main`, unless the text says pre-fix or pilot. Venue formatting and page limits are not yet applied: the FORGE Data & Benchmarking track is 4+1 pages and the SANER RENE track 10+2, so this draft must be condensed.*

## Abstract

Repository-graph tools for coding agents are often promoted with large token-reduction ratios. We ask how much such a ratio depends on how it is measured. We built a fully automatic, model-free benchmark with three layers:
- seeded fixtures whose call sites are known by construction;
- 17 public Python and TypeScript/JavaScript repositories, with query targets sampled independently of any graph;
- runtime-observed calls from the Python repositories' test suites.

We measured two Tree-sitter graph tools (Codexa, and codebase-memory-mcp in its paper-era and current versions), ripgrep, and two language servers.

Re-applying a published-style method to public repositories reproduces its headline: graph answers are 85× smaller than the whole files they replace (repository-level geometric mean). The same graph outputs are 3.0× smaller than `ripgrep -w` output, 1.3–3.0× smaller than raw language-server JSON, and 1.1–2.3× *larger* than the same language-server results printed as one location per line.

Sampling targets from the graph's own edges inflates the graph tools' coverage:
- non-empty answers rise from 47% to 100% for Codexa and from 56% to 88% for codebase-memory;
- recall on runtime-observed calls rises from 0.65 to 0.85 and from 0.61 to 0.79.

On held-out fixtures, at matched completeness, the most complete graph tool returned as many tokens as ripgrep (ratio 1.03, 95% CI 0.94–1.13). The cheapest graph tool was complete on 40% of targets, against 80% for ripgrep.

We release the harness and recommend that token-efficiency claims report the baseline, the sampling frame, the output form and answer completeness together.

## 1. Introduction

Coding agents spend much of their context budget locating code. Graph-based navigation tools promise to cut that cost by answering structural questions, such as "who calls X?", from a pre-built index. Reported savings range from about 10× to "99% fewer tokens".

A token ratio has three hidden parameters:
1. **What the graph is compared against:** whole files, grep, or a language server.
2. **Which queries are asked:** often symbols that already have edges in the graph.
3. **How outputs are counted:** names only, locations, or source.

None of these is a property of the tool.

We ask three questions:
- **Q1.** How does the choice of baseline change measured payload ratios?
- **Q2.** How does sampling targets independently of the graph change measured coverage and rankings?
- **Q3.** Under the same output format and labels that no evaluated tool produced, which tools reach useful token–quality trade-offs?

Contributions:
1. An open, model-free measurement harness with three label layers that never treats an evaluated tool as ground truth. It includes automatic gates for manifest–index–trace agreement and output-form equivalence.
2. Evidence that, for identical graph outputs, the measured ratio spans more than two orders of magnitude depending on baseline and output format. A published-style 85× result reproduces under its own definition and shrinks to 3× against grep.
3. Evidence that graph-conditioned sampling substantially overstates graph-tool coverage and recall.
4. Pattern-level correctness profiles, and recall on runtime-observed calls, for graph, lexical and language-server retrieval.
5. Reporting recommendations.

## 2. Study design

The full protocol is in `PROTOCOL.md`; the frozen configuration and every change made before or after freezing are in `FREEZE.md`. Per-section method details are in `methods_draft.md`.

- **Tasks.**
  - T1 (primary): direct call sites of a target declaration.
  - T2: definition lookup from a call site.
- **Labels.**
  - Layer A: generator manifests for 32 held-out fixture repositories (16 Python, 16 TypeScript), 160 targets with explicit call sites. A further 4+4 calibration fixtures were used only to debug adapters.
  - Layer B: no accuracy labels. We report agreement, availability, size and failures.
  - Layer C: runtime-observed, entry-confirmed calls from the full test suites of 9 Python repositories.
- **Sampling.**
  - S-ind (primary): a stratified sample from an independent declaration frame (Python `ast`, TypeScript compiler).
  - S-cond (diagnostic): declarations with at least one incoming Codexa edge, the original benchmark's rule.
  - In total, 585 S-ind and 331 S-cond natural targets.
- **Arms.**
  - `ripgrep -w` with 0 or 3 context lines.
  - pyright 1.1.414 and the TypeScript 5.9.3 language service.
  - Codexa `find_references`, and the original benchmark's `lookup_symbol` + `get_dependencies`.
  - codebase-memory-mcp v0.5.7 (paper era) and the 2026-10-07 main branch, through MCP sessions.
- **Scoring.** Site, caller and file units. A complete answer has caller-level recall of 1. Three output forms are counted per result. Tokens use cl100k_base.
- **Statistics.** Repository-macro estimates with 95% hierarchical-bootstrap intervals. The primary contrast and the 1.5× margin were fixed before held-out data.

## 3. Results

### 3.1 Q1: the baseline determines the ratio (Fig. 1)

Payload ratio of each baseline to each graph arm's native output; natural repositories, S-ind, targets where the graph arm answered; repository-macro geometric mean [95% CI].

| graph arm | whole files (graph-selected) | rg -w | rg -w -C3 | LSP JSON | LSP location form |
|---|---|---|---|---|---|
| Codexa find_references | 131.7 [85.0, 212.7] | 6.32 [4.63, 9.00] | 27.7 [20.8, 38.0] | 3.04 [1.69, 5.45] | 0.93 [0.63, 1.46] |
| Codexa lookup+deps (original pair) | 84.8 [50.9, 139.9] | 3.00 [2.20, 4.43] | 13.1 [10.1, 18.1] | 2.18 [1.41, 3.27] | 0.49 [0.35, 0.72] |
| codebase-memory (current) | 42.6 [26.1, 73.3] | 3.01 [2.28, 4.06] | 13.1 [10.2, 16.8] | 1.93 [1.33, 2.83] | 0.46 [0.33, 0.67] |
| codebase-memory (v0.5.7) | 54.4 [33.4, 89.9] | 3.54 [2.72, 4.67] | 15.5 [12.2, 19.8] | 1.31 [0.81, 2.15] | 0.44 [0.32, 0.62] |

- **The published-style result replicates.** Applying the original Codexa benchmark's definition to the 17 public repositories gives 85.3× as a repository-level geometric mean (152.8× pooled; 328 targets). The definition is: graph-conditioned targets, whole files the graph selects, and the `lookup_symbol` + `get_dependencies` output. The original report gave 85.8× on five private repositories.
- **The same outputs give 3.0× against ripgrep** (9.3× pooled). Pooled ratios are larger because a few common names produce very long grep outputs.
- **Output format alone can reverse the direction.** The language server's results printed one location per line are smaller than every graph tool's native output (ratio < 1 in all rows), whereas its raw JSON is larger.
- **Exploratory regression:** the log ratio of ripgrep to graph tokens rises with the number of occurrences of the target's name in the repository, with an elasticity of about 0.75 (95% CI about 0.66–0.88) for both Codexa and codebase-memory. Grep is expensive mainly for ambiguous, common names.

### 3.2 Q2: graph-conditioned sampling overstates coverage (Fig. 3)

| arm | non-empty %, S-cond → S-ind | agreement with LSP callers (Jaccard), S-cond → S-ind | observed-call caller recall, S-cond → S-ind |
|---|---|---|---|
| Codexa find_references | 100 → 47.3 | 0.54 → 0.24 | 0.85 → 0.65 |
| Codexa lookup+deps | 99.1 → 35.6 | 0.54 → 0.23 | 0.81 → 0.57 |
| codebase-memory (current) | 87.5 → 56.0 | 0.56 → 0.36 | 0.79 → 0.61 |
| codebase-memory (v0.5.7) | 83.9 → 59.2 | 0.44 → 0.27 | 0.72 → 0.57 |
| language server | 97.4 → 81.2 | (reference) | 0.84 → 0.73 |
| ripgrep -w | 100 → 100 | 0.51 → 0.41 | 0.97 → 0.94 |

Intervals are in `results/main/analysis/report.md`.

Part of the non-empty gap is legitimate: 39% of S-ind targets have no call sites according to the language server. The observed-call recall comparison, however, is restricted to targets with at least one observed call in both samples. That gap therefore reflects conditioning itself: S-cond selects exactly the symbols the graph already connects.

Independently sampled declarations are also often absent from the graph. 16% of S-ind targets are missing from Codexa's graph; coverage of non-test declarations ranges from 91–100% in the Python repositories to 47–68% in five of the eight TS/JS repositories. Two causes:
- object-literal arrow properties are not indexed (e.g. dayjs locale functions);
- same-named nested declarations collapse into one node (e.g. 303 test-local `LocalC` classes in attrs).

### 3.3 Q3: correctness and tokens at matched quality (Fig. 2)

Held-out fixtures, T1, caller level, both languages (160 targets).

| arm | caller recall | caller precision | complete % | native tokens |
|---|---|---|---|---|
| ripgrep -w | 0.95 | 0.35 | 80.0 | 140 |
| ripgrep -w -C3 | 0.95 | 0.35 | 80.0 | 465 |
| language server | 0.97 | 0.64 | 90.0 | 236 |
| Codexa find_references | 0.63 | 0.68 | 40.0 | 50 |
| Codexa lookup+deps | 0.47 | 1.00 | 40.0 | 94 |
| codebase-memory (current) | 0.94 | 0.98 | 89.4 | 160 |
| codebase-memory (v0.5.7) | 0.71 | 0.90 | 49.4 | 70 |

**Primary contrast.** Geometric-mean token ratio of each arm to `ripgrep -w`, on targets where both are complete. "Meaningful" uses the margin fixed before held-out data: the whole interval must lie below 0.667 (a saving) or above 1.5 (a cost).

| arm | ratio | 95% CI | n / 160 | verdict |
|---|---|---|---|---|
| Codexa find_references | 0.35 | 0.33–0.37 | 64 | meaningful saving, but only where it is complete (40%) |
| Codexa lookup+deps | 0.65 | 0.62–0.67 | 64 | not meaningful: the upper bound, 0.672, crosses the margin |
| codebase-memory (current) | 1.03 | 0.94–1.13 | 127 | no difference |
| codebase-memory (v0.5.7) | 0.58 | 0.56–0.62 | 79 | meaningful saving, at 49% completeness |
| language server (JSON) | 1.75 | 1.65–1.85 | 128 | meaningful cost |

Small graph outputs coincide with incomplete answers. The only graph tool as complete as the lexical and language-server baselines needed the same token budget as `ripgrep -w`.

**Pattern profile** (caller recall, both languages; Table in report):
- **ripgrep** misses only calls through an import alias.
- **Pyright** also misses alias calls in Python; the TS language service does not.
- **Codexa's misses on fixtures** (240 missed callers for `lookup+deps`):
  - 96 are wrong resolutions: a call bound to a same-named local function that shadows the target;
  - 32 are module-level calls, which it never attributes to a caller;
  - 112 are relations it does not record at all. By pattern (Table in report), these fall on re-exports, TS constructor calls, and method calls on typed receivers or through `super`.
- **Codexa's recall drops from 0.73 to 0.53 with ambiguous names** (precision 0.83 → 0.54). codebase-memory is unaffected by ambiguity: 0.95 vs 0.94.
- **codebase-memory v0.5.7 misses** typed-receiver method calls and TS constructor calls that the current version finds.

**T2 (definition lookup).** Every arm found the definition for all 160 targets. Only the language server returned a single, exact answer (precision 1.00). The others returned same-named candidates (precision 0.68–0.76), at 37–98 tokens.

### 3.4 Layer C: recall on runtime-observed calls

Nine Python repositories; full test suites traced; 323 targets with at least one observed call.

| arm | caller recall | complete % |
|---|---|---|
| ripgrep -w | 0.95 [0.92, 0.98] | 92.5 |
| language server | 0.79 [0.64, 0.90] | 72.5 |
| Codexa find_references | 0.75 [0.68, 0.82] | 61.9 |
| Codexa lookup+deps | 0.69 [0.61, 0.78] | 56.4 |
| codebase-memory (current) | 0.70 [0.60, 0.79] | 58.9 |
| codebase-memory (v0.5.7) | 0.64 [0.53, 0.74] | 53.2 |

- **Lexical retrieval has the highest recall on observed calls.**
- **Language-server misses are concentrated in repositories that ship `.pyi` stubs** (more-itertools, attrs): pyright binds public-API calls to the stub declarations.
- **Codexa's misses on observed calls split three ways:** 503 callers with no recorded relation, 445 whose enclosing declaration is absent from the graph, and 30 truncated outputs.

Unobserved static results are not false positives, so precision cannot be judged in this layer.

## 4. Discussion and recommendations

- **Report the baseline, and more than one.** For the same graph outputs, the ratio ranged from 0.44 to 134 depending on baseline and format. Whole-file baselines measure "an index is smaller than the files it indexes", not navigation efficiency.
- **Sample targets independently of the tool under test.** Edge-conditioned sampling raised the graph tools' non-empty-answer rates by 25–64 percentage points, and their recall on observed calls by 0.15–0.24.
- **Count tokens in a common output form,** and report what each form contains. Names-only outputs look cheap partly because they carry less information.
- **Report completeness next to tokens.** In our data the smallest outputs were the least complete. A matched-quality comparison removed the advantage of the most complete graph tool.
- **Payload tokens are not agent cost.** Agent behaviour, retries and prompt caching (Bai et al. 2026; Weinberger & Hozez 2026) are out of scope. Agent-level comparisons such as Codebase-Memory's measure something different and are not contradicted by these results.

## 5. Threats to validity

See `intro_threats_draft.md`. Additional threats from execution:

1. **A post-freeze adapter fix.** Pyright answered before indexing finished. All Python jobs were re-run; pre-fix results are kept in `results/pre-fix/`. The fix changed layer-C language-server recall from 0.73 to 0.79 and no conclusion. Python natural targets were re-drawn with the same seed, because language-server fan-out drives stratification.
2. **A post-freeze environment fix.** Five test suites needed dependency groups installed before they could be traced.
3. **Three pre-freeze harness corrections to name resolution.** These were made to avoid penalising graph tools for our own matching rules. Unresolved tool output remains at 0–6% of returned units and is counted against the tool.
4. **Substitute tokenizer.** Tokens were counted with gpt-tokenizer's bundled cl100k/o200k ranks, validated against known token ids. tiktoken itself was unreachable from the build environment.

## 6. Related work

See `related_work_draft.md`. The closest prior studies:
- Codebase-Memory: agent-level, graph vs grep and file reading;
- Xu 2026: language server vs grep in agents;
- CodeNib: static vs live language-server agreement, with graph-derived queries.

Our contribution is model-free and cross-tool, uses labels independent of every evaluated tool, and measures how sampling and output form change the conclusions.

## 7. Artefact

`research/navbench`, containing:
- the harness (`nb/`);
- the protocol and frozen configuration;
- pinned corpus commits (`results/corpus_shas.txt`);
- raw per-query outputs, scored rows, traces, analysis and figures (`results/`).
