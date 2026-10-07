# Frozen configuration (written before any held-out fixture or confirmatory repository was run)

Status: DRAFT until the pilot gates pass; the commit that marks it FROZEN is recorded at the bottom.

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
- Fixtures: calibration seeds 0–3 (adapter debugging only); held-out seeds 100–115 (16 per language, 112 targets per language, 64 with explicit call sites per language… exact counts in results).
- Natural: pilot repositories `click`, `zod`, `axios` are development only and excluded from confirmatory tables; confirmatory = the other 17 repositories in `corpus.json`.
- Natural sampling: S-ind = stratified (kind × provider call-fan-out bucket) draw of 40 targets from a random pool of ≤300 non-test declarations of the independent frame; S-cond = 20 targets drawn from declarations that have ≥1 incoming Codexa edge (the original benchmark rule). Seed 20261008.

## Primary contrast (stated before held-out data)
On held-out fixtures, T1, caller level: for each graph arm and for `lsp`, the repo-macro geometric-mean ratio of native cl100k tokens (arm / `rg0`) over targets where **both** arms return complete answers, with a 95% hierarchical-bootstrap interval (fixture repositories, then targets). Reported alongside each arm's complete-answer rate (share of targets where it qualifies). A ratio is called a practically meaningful saving only if the whole interval lies below 1/1.5 (≈0.67); a meaningful cost only if the whole interval lies above 1.5.

Secondary (stated in advance): layer-A caller recall/precision by arm, pattern and name ambiguity; T2 hit rate; Q1 baseline payload ratios on S-ind; Q2 S-ind vs S-cond non-empty rate, agreement with the LSP caller set, and layer-C observed-call caller recall (Python). The fan-out/ambiguity regression is exploratory.

## Exclusions
None by outcome. Every target receives every arm; failures, timeouts, empty answers and truncation are reported, never dropped.
