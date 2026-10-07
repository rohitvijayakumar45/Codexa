# Protocol draft: measuring the navigation efficiency of repository tools

Status: **draft, approved for protocol drafting and a small validation pilot only.** No benchmark has
been implemented or run under this protocol. Scaling to a full corpus requires the pilot gates in §9
to pass first. **The design is fully automatic: no human annotation or audit** (§6). The cost of
that choice is narrower claims (§12): no claim of general accuracy on natural code.

The direction of the result is not assumed. The earlier 3-repo pilot (`results/`) is affected by
selection bias, oracle bias and task-definition bias. Neither the magnitude nor the direction of a
corrected effect is established, and nothing in it is reported as a finding.

## 1. Questions

- **Q1.** How does the choice of baseline change measured payload ratios?
- **Q2.** How does sampling from source declarations, as opposed to from the graph's own edges,
  change measured availability, agreement, observed-call recall and tool rankings?
- **Q3.** Which tools reach useful token–quality operating points when their outputs follow the
  same output format? Quality here means accuracy on seeded fixtures (layer A) or recall on
  runtime-observed Python calls (layer C). Natural-code agreement (layer B) is never used as a
  quality axis.

Primary contrast (stated in advance): for task T1 on held-out seeded fixtures, the difference in
tokens-at-matched-recall between each graph tool and the ripgrep arm. Secondary contrast: the same
on runtime-observed Python call sites in independently sampled natural targets (layer C).
Everything else is secondary or exploratory, and is labelled as such. The three populations are
reported separately and never pooled into an "overall recall".

## 2. Tasks

The first study covers only these two task families.

| Task | Input | Gold unit (known in layers A and C only; §6) | Notes |
|---|---|---|---|
| **T1 Direct call-site retrieval** | Target declaration | Set of call-site locations `(file, line, column)` whose callee resolves to the target | Primary task |
| **T2 Definition lookup** | Use site `(file, line, column)` | Declaration location(s) | Secondary task |
| T3 All-reference retrieval (extension) | Target declaration | All reference locations, including imports, attribute reads and annotations | Scored separately and never merged with T1 |
| Multi-hop dependencies | — | — | **Deferred.** Language-server reference results alone are not a gold dependency graph |

**Dynamic calls.** Gold labels use *static possible-target* semantics. A call site counts if static
analysis of the source can bind it to the target, including through a declared receiver type or an
import alias. Runtime-only dispatch (for example `getattr`, or dynamic `import()` with computed
names) is labelled `dynamic` and reported as its own category. These labels do not represent
execution truth.

## 3. Target identity and sampling

- **Identity.** A target is identified by `(repo commit, file path, declaration start position)`,
  never by bare name. Duplicate names are kept as distinct targets.
- **Independent sampling frame.** Declarations are enumerated by a tool that does not share Codexa's
  parser, filters or caps. For Python that is the stdlib `ast` module; for TypeScript and JavaScript
  it is the TypeScript compiler API. Enumeration runs over all files the repository's own tooling
  would compile, which avoids Codexa's skip list and its limits on file count and file size.
- **Coverage check (automatic).**
  - Report the declarations the frame finds that each graph tool lacks: missing definitions.
  - Report the reverse: declarations a graph tool has that the frame lacks.
  - Report syntax that either side cannot handle, as counts.
- **Two samples, both scored with the same tools and reference sets:**
  - **S-ind (primary):** stratified random draw from the independent frame. Strata are language ×
    symbol kind (function, method, class) × reference fan-out bucket (0, 1–2, 3–9, 10+, measured by
    the reference provider). Graph-missing targets are retained.
  - **S-cond (diagnostic):** the original rule, i.e. graph symbols with ≥1 incoming edge.
  - Q2 is answered by comparing S-ind and S-cond results for the same tool.
- **Inclusion probabilities** are recorded per stratum. All population estimates are weighted.

## 4. Arms

| Arm | Configuration | Applies to |
|---|---|---|
| ripgrep (name-only) | `rg -w --no-heading -n`, fixed include globs, no context lines | T1, T3 |
| ripgrep ±k | Same, with `-C k` for k ∈ {0, 3} | T1, T3 |
| Language server, locations only | pyright (Python), tsserver (TS/JS); `references` / `definition` | T1–T3 |
| Language server, with source | Same, plus the source line for each location | T1–T3 |
| Codexa graph | `tools.py` graph tools, unchanged, native output | T1, T2 |
| codebase-memory-mcp | Paper-era version **and** current version, pinned | T1, T2 |
| Whole-file | Defining file + files holding gold call sites | Sensitivity baseline only (Q1); never the main opponent |
| Definition-only | Declaration location | T2 only |

- **Query tracks.** Each arm receives the same input in one of two tracks:
  - *name-only* (bare identifier);
  - *position-identified* (file + position).
  No arm receives file lists derived from gold labels or from another arm.
- **Languages.** Python and TypeScript/JavaScript first; Go and Java are deferred.

## 5. Output formats (Q3 and formatting control)

Each arm's output is measured in three forms. The set of returned facts is identical across forms.

1. **Native:** the tool's own output.
2. **Common location format:** one `path:line:col` per returned location.
3. **Common source-enriched format:** each location followed by its source line.

Rules:
- A form may only re-serialise facts the tool returned. If a tool returns names without locations
  (Codexa's `lookup_symbol` / `get_dependencies` return caller names only), its common-format rows
  contain only what it can locate unaided. Missing facts are never filled in from the reference
  provider or from another arm.
- Coverage (which facts) and representation size (how many tokens) are reported separately.

## 6. Evaluation layers (fully automatic)

| Layer | Purpose | Permitted claim |
|---|---|---|
| **A. Seeded fixtures** | Known declarations, call sites, targets and distractors | Precision and recall on the specified generated patterns |
| **B. Natural repositories** | Compare tools on independently sampled targets (§3) | Agreement, output size, latency, availability and failure rates. Not natural-code accuracy |
| **C. Python runtime tracing** | Observed caller–callee pairs, independent of all static tools | Recall on successfully mapped, observed calls. Not all possible calls |

### A. Seeded fixtures
- **Patterns:**
  - direct calls and typed method calls;
  - import aliases and re-exports;
  - same-name methods and shadowing;
  - higher-order calls, decorators and wrappers;
  - dynamic calls with predetermined runtime targets;
  - non-call references, comments and strings as distractors.
- **Names:** both unique and ambiguous. Unique names alone make lexical retrieval unrealistically easy.
- **Manifest:** a generator-produced manifest lists the expected declaration identities, source
  locations and relationships. It is produced independently of every evaluated tool.
- **Automatic validation:**
  - fixtures compile or execute;
  - coordinate mappings and expected behaviour are checked;
  - explicit source calls are distinguished from implicit calls introduced by decorators and
    wrappers.
- **Scope:** exact precision and recall are computed only within the closed scope the manifest covers.
- **Splits:** calibration fixtures (used to fix operating points, §8) are kept separate from held-out
  evaluation fixtures. Results describe these patterns, not natural code in general.

### B. Natural repositories
- **Targets:** sampled from source declarations independently of the evaluated graphs (§3), with
  graph-missing targets retained. The sampling machinery is checked automatically on the fixtures,
  and its language and syntax limitations are disclosed.
- **Comparison units:** target identities and comparison units are normalised before computing
  agreement. Caller-function sets are not interchangeable with individual call sites.
- **Measured:**
  - pairwise output agreement and disagreement;
  - missing-target, unsupported-query and unresolved-output rates;
  - native and normalised payload tokens;
  - indexing time, cold and warm latency, resource use;
  - failures, timeouts, truncation.
- **Status of the language server:** it is a reference provider, not an answer key. Smaller payloads
  do not establish greater usefulness.

### C. Python runtime tracing (supplementary)
- **Instrumentation:** each repo's test suite runs under validated instrumentation that records
  caller location → callee pairs.
- **Event semantics:** `sys.monitoring` `CALL` fires *before* invocation, so an attempted invocation
  is distinguished from confirmed entry into a Python callee (via `PY_START` of the resolved code
  object).
- **Mapping validation:** source-position and callable-identity mappings are validated on controlled
  fixtures first.
- **Reported:**
  - successfully mapped, deduplicated source-site → target pairs;
  - unresolved mappings and monitoring gaps;
  - test failures, subprocess coverage and instrumentation overhead;
  - static-tool recall against the recorded pairs.
- **Limits:**
  - Unobserved static results are not false positives; tracing cannot establish their precision.
  - Line coverage does not establish what fraction of all call sites was observed.
- JavaScript tracing is deferred until the Python adapter is validated.

### Checks that are not truth oracles
- **Rename-and-compile:** used only to validate controlled mutations, never to enumerate references.
  A broken import can produce one diagnostic while alias-based calls raise no separate errors.
- **Go-to-definition:** optional. It classifies returned locations as *provider-confirmed*,
  *contradicted* or *unresolved*, reported as provider-based validation, not proven precision.
- **Tool consensus:** agreement does not establish correctness or completeness.
- **LLM judges:** omitted from the primary evaluation.

## 7. Failure accounting and error taxonomy

- **For every arm and repository**, the following are recorded as counts: setup or indexing failure,
  query error, timeout, truncated output, empty result, and excluded target (with reason).
  - A failure is never scored as a valid empty result.
  - Error strings are never counted as answer tokens.
- **For every missed or wrong graph result**, one of these causes is assigned:
  - **missing definition** (target not in the graph);
  - **missing relation** (target present, call site absent);
  - **wrongly resolved relation** (edge to the wrong target);
  - **insufficient returned information** (relation exists but output lacks a location);
  - **truncation** (cap or output limit hit; caps are logged per repo);
  - **ignored file** (skipped by size, count, extension or directory rules);
  - **parse failure**;
  - **lookup ambiguity** (name matched several targets).

## 8. Metrics and statistics

- **Per query:**
  - layers A and C: precision (A only), recall, complete-answer rate (recall = 1);
  - layer B: agreement, availability and failure outcomes;
  - tokens in all three output forms, counted with `tiktoken` `cl100k_base` and `o200k_base` from
    pinned local vocabulary files;
  - latency (cold and warm).
- **Per tool and repo:** indexing time, memory and storage, reported separately from query cost.
- **Matched quality.**
  - Operating points (ripgrep k, result limits, graph depth) are fixed on calibration fixtures and a
    development split of repositories before held-out fixtures or test repositories are touched.
  - A target recall a tool cannot reach is reported as *unreachable*, not cheap.
- **Clustering.**
  - Repositories are the primary clusters.
  - Estimates use a hierarchical bootstrap (repositories, then targets within repositories).
  - Macro per-repo results and pooled totals are reported separately, with language strata.
- **Tests.** Wilcoxon signed-rank on per-repo paired summaries is supplementary. Effect sizes with
  intervals are primary. Symbols are not tested as independent units.
- **Margins.** A practically meaningful token difference (proposed: ≥1.5× at matched recall) and a
  quality margin are fixed before analysis. These are proposals, to be confirmed before the freeze. A non-significant difference is not reported as "no
  benefit".
- **Exploratory regression.** log token ratio ~ name ambiguity + reference fan-out + symbol kind +
  file size + project size + truncation + language, with repository random effects. It is labelled
  exploratory.
- **Token scope.**
  - Single-payload tokens are not cumulative agent tokens, and neither is billed cost.
  - Caching appears only as a labelled scenario.
  - Agent savings are not claimed from this study.

## 9. Validation pilot (next step) and gates to scale

**Pilot.**
- 3 repositories: 1 Python, 1 TypeScript, 1 mixed or JS. Pinned commits, chosen before looking at
  any tool's results.
- About 40 S-ind targets and 20 S-cond targets per repository, plus all fixtures.
- Purpose: debug adapters, fixtures, tracing and the output-format pipeline. Pilot numbers are not
  reported as results.

**Gates (all must pass before scaling):**
1. Benchmark adapters reproduce the expected identities, coordinates and scoring on fixtures, within
   each arm's declared capabilities. The tracing adapter reproduces fixture call pairs.
2. Failed and unsupported cases stay visible. Error strings never count as successful cheap answers,
   and every target has an outcome for every arm.
3. Sampling, configurations, budgets and primary comparisons are frozen.
4. Expected labels never influence retrieval queries or result ordering.
5. Fixture accuracy, natural-code agreement and observed-call recall are kept separately labelled.
6. Output-form equivalence: a script verifies identical fact sets across the three output forms for
   every query.

**Scaling (after the gates).**
- Corpus selection criteria fixed in advance: public, permissive licence, size strata, active
  history, buildable language-server environment. Repositories are drawn at random from candidates
  meeting the criteria. The target count is set from the pilot's variance, with 15–30 repositories
  as a planning range only.
- Freeze commits, tool versions, dependencies and tokenizer files.
- Run S-ind (primary) and S-cond (diagnostic). Save every request, output and failure.

## 10. Planned figures and tables (no results exist)

- Table 1: corpus (repo, language, LOC, declarations, frame coverage per tool, commits).
- Fig. 1 (Q1): per-repo payload ratio distributions by baseline (whole-file, ripgrep ±k, language
  server) for each graph tool.
- Fig. 2 (Q2): availability, agreement, observed-call recall (layer C) and tool ranking, S-ind vs
  S-cond, per tool, with intervals.
- Fig. 3 (Q3): token–recall operating points per tool on held-out fixtures (layer A) and on observed
  calls (layer C), in the common location format; unreachable points marked.
- Table 4: fixture precision and recall per pattern (layer A).
- Table 2: failure and error-taxonomy counts per arm.
- Table 3: formatting sensitivity (native vs common forms).

## 11. Threats to validity (to be addressed in the paper)

- Reference-provider configuration (missing dependencies, environment setup).
- Static-semantics labelling of dynamic calls.
- Fixtures are cleaner than natural code; results hold only for the generated patterns.
- Runtime tracing covers only exercised code, and test suites under-represent some call kinds.
- No human audit: natural-code accuracy is not measured, and reference-provider errors stay unquantified.
- Query types limited to T1 and T2.
- Two languages only.
- Tool version drift; the paper-era vs current graph tool will differ.
- Repository selection.
- Payload tokens are not agent cost.

## 12. Claims this study may and may not support

- **May support:**
  - how baseline choice, sampling frame and output format change *measured* navigation efficiency;
  - controlled correctness on seeded patterns;
  - natural-code agreement and availability trade-offs;
  - recall on observed Python calls.
- **May not support:**
  - comprehensive natural-code accuracy;
  - agent-level token savings or losses;
  - billed cost;
  - universal statements about code graphs;
  - any refutation of Codebase-Memory's agent-level results.
