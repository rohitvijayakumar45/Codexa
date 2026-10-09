# Frozen configuration (written before any held-out fixture or confirmatory repository was run)

Status: **FROZEN** after the pilot gates passed (2026-10-07). Nothing below changed after held-out fixtures or confirmatory repositories were run.

## Tools and versions
| Component | Version / commit |
|---|---|
| Codexa graph (`backend/agents/tools.py`, `backend/repository/analyze.py`) | repo commit `0ea016a` (backend unchanged up to `356b143`) |
| codebase-memory-mcp, current | `bf93f0b7` (main, 2026-10-07), built from source with gcc |
| codebase-memory-mcp, paper era | tag `v0.5.7` = `b31d1770` (2026-03-26; paper posted 2026-03-28) |
| pyright (Python reference provider) | 1.1.414 |
| TypeScript language service (TS/JS reference provider, independent TS/JS index) | 5.9.3 |
| ripgrep | 14.1.0 |
| Token counter | gpt-tokenizer 4.0.0, `cl100k_base` (primary) and `o200k_base`; validated against known cl100k ids |
| Python | 3.13.16 (`sys.monitoring` for layer C) |

## Arms (task T1: direct call sites of a target declaration)
| Arm | Input | Configuration |
|---|---|---|
| `rg0` | bare name | `rg -n --column --no-heading -w -F NAME` with language globs |
| `rg3` | bare name | same with `-C 3` |
| `lsp` | declaration position | pyright / TS language service `references` (declaration excluded); native = LSP JSON locations |
| `codexa_refs` | bare name | `_find_references(name)` |
| `codexa_orig` | bare name | `_lookup_symbol(name)` + `_get_dependencies(name)` (the original benchmark's pair); callers read from the target's own block |
| `cbm_cur` | bare name, then qualified name if the tool answers "ambiguous" | `trace_path --direction inbound --depth 1 --include-tests true`, native tree format; tokens of both calls counted |
| `cbm_057` | bare name | `trace_call_path {direction: inbound, depth: 1}`; payload = inner MCP text |

T2 (definition lookup from one explicit call site): `lsp_def`, `rg_def` (fixed per-language definition regex), `codexa_def` (`_lookup_symbol`), `cbm_cur_def` / `cbm_057_def` (`search_graph` exact name).

No arm receives expected labels; graph tools only receive the target's qualified name when they themselves report ambiguity.

## Scoring units
- site: call-node identity of each returned location (location-returning arms only);
- caller: enclosing declaration of each returned location, or the caller declaration a graph tool names;
- file.
Complete answer = caller-level recall 1.0. Three output forms per result (native, common location, common source-enriched); an automatic check confirms identical fact sets across forms.

## Splits
- Fixtures: calibration seeds 0–3 (adapter debugging only); held-out seeds 100–115 (16 fixture repositories per language, 7 targets each; 5 of the 7 patterns have explicit call sites).
- Natural: pilot repositories `click`, `zod`, `axios` are development only and excluded from confirmatory tables; confirmatory = the other 17 repositories in `corpus.json`.
- Natural sampling: S-ind = stratified (kind × provider call-fan-out bucket) draw of 40 targets from a random pool of ≤300 non-test declarations of the independent frame; S-cond = 20 targets drawn from declarations that have ≥1 incoming Codexa edge (the original benchmark rule). Seed 20261008.

## Primary contrast (stated before held-out data)
On held-out fixtures, T1, caller level: for each graph arm and for `lsp`, the repo-macro geometric-mean ratio of native cl100k tokens (arm / `rg0`) over targets where **both** arms return complete answers, with a 95% hierarchical-bootstrap interval (fixture repositories, then targets). Reported alongside each arm's complete-answer rate (share of targets where it qualifies). A ratio is called a practically meaningful saving only if the whole interval lies below 1/1.5 (≈0.67); a meaningful cost only if the whole interval lies above 1.5.

Secondary (stated in advance): layer-A caller recall/precision by arm, pattern and name ambiguity; T2 hit rate; Q1 baseline payload ratios on S-ind; Q2 S-ind vs S-cond non-empty rate, agreement with the LSP caller set, and layer-C observed-call caller recall (Python). The fan-out/ambiguity regression is exploratory.

## Exclusions
None by outcome. Every target receives every arm; failures, timeouts, empty answers and truncation are reported, never dropped.

## Harness changes made during calibration and pilot (before freezing; none touch the evaluated tools)
1. Manifest: added the `Svc()` constructor call in `run_all`, the `Sub(Svc)` base reference, and the decorator wrapper's implicit call (found by the trace-vs-manifest gate).
2. Columns normalised to character offsets (ast reports UTF-8 bytes).
3. Duplicate declarations sharing (file, qualified name) merged into one identity (found by the form-equivalence gate on click).
4. codebase-memory-mcp queried through persistent MCP sessions instead of one CLI process per query (CLI start-up added ~5 s per call); `include_tests: true` passed explicitly; cold index (cache deleted) before timing.
5. Name resolution for tool outputs: module names with file extensions or `__file__`; nested declarations reported as `module.<name>` (unique same-file bare-name match); Codexa's bare names for nested functions.
6. TS/JS frame: constructors and accessors added as caller units (not sampled as targets).
7. Layer C: lambda/generator callees counted separately as non-declaration callees; locally defined classes mapped; per-test timeout 120 s; traced run capped at 900 s wall clock (SIGTERM saves observed calls), plain run capped at 300 s.

## Gate status at freeze
- Fixture gate (manifest = independent index = runtime trace, all 40 fixtures): PASS.
- Output-form equivalence: 0 failures on calibration fixtures and on the 3 pilot repositories (178 targets).
- Failure accounting: every target has a row for every arm; statuses ok/empty/error/timeout recorded with notes.
- Labels never reach queries: graph tools receive the target's qualified name only after they report ambiguity themselves.

## Post-freeze environment fix (no change to tools, sampling, scoring or analysis)
- Layer C: five Python repositories (marshmallow, itsdangerous, jinja, attrs, rich) initially collected 0 tests because their test dependencies are declared as PEP 735 dependency groups, which the environment script did not install. The groups (plus `attrs` for rich's tests) were installed and these five suites were re-traced with the same budgets. Their first, empty traces were discarded.

## Post-freeze adapter fix: pyright readiness (affects Python language-server results only)
- Found during result review (layer C showed pyright recall of 0.29–0.54 in three repositories). A minimal reproduction showed pyright answers `references` before workspace analysis finishes: the first query returned only the `__all__` entry, and the same query 3 s later returned every reference.
- Fix (`nb/lsp.py: warm`): open every source file, then wait until probe reference queries are stable twice in a row, 2 s apart. Warm-up time and probe counts are recorded per run (`meta.provider_warmup`). Validation: 0 of 80 reference sets changed when re-queried 30 s after warm-up (attrs, itsdangerous).
- All 25 Python jobs (16 held-out fixtures, 9 natural repositories) were re-run. Because pyright fan-out also stratifies Python sampling, Python natural targets were re-drawn with the same seed and rules. TypeScript results are unaffected (the TS language service computes synchronously). Pre-fix results are kept in `results/pre-fix/` for comparison.
- Not changed: tools, sampling rules, scoring, analysis or the primary contrast.
- Separate, genuine behaviour (not an artefact): in repositories that ship `.pyi` stubs (more-itertools, attrs), pyright binds public-API calls to the stub declarations, so references requested on the implementation miss those call sites.

## Post-freeze supplementary run and analyses (added in response to review; labelled post hoc)
- **Scoring fix (found during this review; affects natural-repository S-ind rows only).**
  - The bug: 76 declarations were drawn into both S-ind and S-cond, but `nb/score.py` keyed rows by declaration alone, so each was scored once and labelled S-cond. The analysed S-ind therefore had 585 targets instead of the 661 drawn. The dropped targets are the ones that have G1 edges, so this biased S-ind against G1.
  - The fix: rows are now keyed by (declaration, sample). Layer-C pooled metrics and the error taxonomy count each target once.
  - Effect: all 8,780 previously scored rows are unchanged, and 532 rows were added. Every number in `results/main` was regenerated; the earlier report is kept as `analysis/report_before_scoring_fix.md`.
  - Main changes:
    - S-ind non-empty rates: G1 47→54% and 36→44%; codebase-memory 56→60% (current) and 59→62% (v0.5.7);
    - Q1 ratios: whole files 48–139×, rg 2.9–6.0×;
    - layer C, fixtures, the primary contrast and the original-method replication (S-cond): unchanged.
  - `results/pre-fix/` was re-scored in the same way.
- **codebase-memory-mcp v0.5.5** (`da7e7758`).
  - The Codebase-Memory preprint names v0.5.5 as its evaluated release; the frozen design used v0.5.7 (`b31d1770`, two days before the preprint) as "paper era".
  - v0.5.5 was built from source and queried on the **frozen targets** of `out-main` with the unchanged v0.5.7 adapter (`nb/run_extra_arm.py`, arm `cbm_055`).
  - Comparison: `nb/compare_versions.py` (output in `results/main/supplement_cbm_versions/`).
    - Fixtures: identical facts and tokens on all 384 queries.
    - Natural code: different facts on 58 of 992 queries (5.8%).
    - A re-run of v0.5.7 itself differs from the main run on 53 of 992 (5.3%; same-named declarations resolve differently between runs).
    - The current version differs from its own re-run on only 4 of 992.
  - The version difference is therefore within v0.5.7's own run-to-run variation, and the aggregate metrics agree within 0.03:
    - S-ind non-empty 0.63 vs 0.62;
    - layer-C recall 0.67 vs 0.64;
    - fixtures identical.
  - The paper reports v0.5.5 and v0.5.7 as one row.
- **Robustness analyses** (`nb/robustness.py`, report `results/main/analysis/robustness.md`):
  - R1: full-workload Layer A metrics and ratios, with no completeness conditioning;
  - R2: composition of the jointly-complete subsets;
  - R3: the primary contrast in the common location and source-enriched forms;
  - R4: strict caller credit for location arms (only gold call sites credit a caller);
  - R5: S-cond vs S-ind, post-stratified on repository × kind × language-server call fan-out bucket.
- Apart from the scoring fix above, none of these change the frozen tools, targets, scoring or primary contrast.

## Post-freeze additions (2026-10-08; do not change the frozen configuration)
See FEATURES.md. Default `nb.run` arguments reproduce the frozen arms, sampling and tasks; new arms
(`codexa2_*`), T3 and the `fresh` fixture split are opt-in. Codexa's call resolution now defaults to
v2 in the product; the frozen G1 arms pin `CODEXA_CALL_RESOLUTION=v1` (nb/adapters.py), verified
fact-identical to the stored raw results on 100 regenerated held-out rows
(results/features-local/equivalence_v1_frozen.txt). The generator now also records non-target call
edges in the manifest (T3 gold); every generated source file is byte-identical to before.

## Large-repository extension (2026-10-09; post-freeze, criteria fixed before results)
- Purpose: a falsification test. The rg/graph payload ratio grows with name frequency (elasticity ≈ 0.77), so graph tools should gain in large repositories with common names.
- Repositories:
  - networkx and SQLAlchemy (Python);
  - TypeORM and NestJS (TypeScript).
- Selection: listed with their criteria, SHAs and frame sizes in `corpus.json` → `large_extension`. They were chosen before any NavBench result on them existed; only clone sizes and frame counts had been seen.
- Criterion: ≥ 5,000 declarations in the independent frame. networkx qualifies on all declarations (8,294); it has 2,627 non-test functions, methods and classes.
- Protocol: unchanged, with the frozen arms (`nb.run` defaults) and the same sampling, scoring and analysis, and the (declaration, sample)-keyed scorer.
- Layer C: for Python, the test suites are traced with the same budgets.
- Output: `results/large/`, reported separately from the 17-repository corpus.
- Outcome (2026-10-09), in `results/large/LARGE_RESULTS.md`:
  - all 4 repositories ran with no failures and no gate messages;
  - the traced runs covered only 9% (networkx) and 2% (sqlalchemy) of the suites within the frozen budget;
  - SQLAlchemy's plain run crashed in a compiled extension after 104 s;
  - the prediction (graph tools gain in large repositories) failed: rg/cbm-current is 3.22 [2.42, 4.46], vs 2.92 on the main corpus.
