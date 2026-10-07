# Methods (draft, results-independent)

## Study design
We compare repository-navigation tools on two tasks, using three evaluation layers that are reported
separately and never pooled:

- **T1, direct call-site retrieval** (primary). Input: a target declaration. Gold unit: the call expressions
  whose callee statically binds to the target (static possible-target semantics).
- **T2, definition lookup** (secondary). Input: one call site. Gold: the target declaration.

| Layer | Population | What it can establish |
|---|---|---|
| A. Seeded fixtures | 40 generated repositories (Python, TypeScript), 280 targets; calibration seeds 0–3, held-out seeds 100–115 | Precision and recall on specified patterns |
| B. Natural repositories | 17 confirmatory public repositories (+3 pilot repositories, excluded) | Agreement, availability, payload size, latency, failure rates; **not** natural-code accuracy |
| C. Runtime tracing (Python) | Test suites of the Python repositories in B, within a fixed wall-clock budget | Recall on successfully mapped, observed calls |

No human annotation is used. All labels come from generator manifests (A) or runtime observation (C).

## Fixtures
Each fixture is a small, executable repository that contains one instance of each pattern:
- direct calls;
- calls through an import alias;
- calls through a module or namespace attribute;
- calls through a re-export barrel;
- constructor calls;
- calls on a typed receiver, including `self`/`this` and `super`;
- a same-named method on another class;
- local shadowing;
- a target passed as a callback;
- dynamic dispatch by string;
- decorator wrappers (Python);
- arrow-function declarations (TypeScript);
- module-level calls;
- comment and string distractors.

Half of the fixtures use unique identifiers. The other half draw names from a pool of common identifiers and add unrelated same-named declarations and calls ("ambiguous").

The generator records every expected declaration, call site and distractor position in a manifest that is independent of all evaluated tools.

Validation:
- Python fixtures execute.
- TypeScript fixtures compile under `--strict` and run.
- For every Python target, the set of runtime-observed call lines equals the manifest's explicit, dynamic and indirect sites.

Validation found three omissions in the first manifest version, all repaired before any held-out data was produced:
- a constructor call;
- a base-class reference;
- the decorator wrapper's implicit call.

## Independent index and sampling frame
Declarations and call expressions are enumerated by tools that share no code with the evaluated graphs: Python's `ast` module, and the TypeScript compiler API for TS/JS.

Target identity is (commit, file, declaration-name position). Declarations sharing a (file, qualified name) pair, such as alternative definitions under `if` branches, are merged into one identity, because that is the finest identity a qualified-name-returning tool can express.

**S-ind (primary):**
- Draw a random pool of ≤300 non-test function, method and class declarations.
- Measure each declaration's call fan-out with the reference provider.
- Draw 40 targets stratified by kind × fan-out bucket (0, 1–2, 3–9, ≥10), recording inclusion weights.

**S-cond (diagnostic):** 20 targets drawn from declarations with ≥1 incoming Codexa edge, the rule of the original benchmark.

## Arms
- **ripgrep:** `-w` with zero or three context lines, given the bare name.
- **Language server:** references at the declaration position. Pyright for Python; the TypeScript language service for TS/JS.
- **Codexa:** `find_references`; and `lookup_symbol` + `get_dependencies`, the original benchmark's pair.
- **codebase-memory-mcp:** inbound `trace_path`/`trace_call_path` at depth 1.
  - Two versions: the paper-era release v0.5.7 and the current main branch.
  - Queried through persistent MCP stdio sessions.
  - When a tool reports ambiguity, the follow-up call uses the target's qualified name, and the tokens of both calls are counted.

## Output forms and token counting
Each result is measured in three forms:
1. native output;
2. a common location form (one location, or one caller declaration, per line);
3. a common source-enriched form (location forms only).

Forms re-serialise only facts the tool returned. An automatic check verifies identical fact sets across forms for every query.

Tokens are counted with `cl100k_base` (primary) and `o200k_base`.

## Scoring
Returned facts are mapped to three units:
- **call nodes** (site level; location-returning tools only);
- **enclosing declarations** (caller level; all tools);
- **files**.

A **complete answer** has caller-level recall 1.0.

Failures, empty answers, truncation and unresolved names are counted per arm; error strings are never counted as answers.

## Statistics
- **Clusters:** repositories, with each fixture repository a cluster.
- **Intervals:** 95% percentile intervals from a hierarchical bootstrap (2,000 resamples: repositories, then targets within repositories).
- **Means:** repository-macro means.
- **Primary contrast, fixed before held-out data:** the repository-macro geometric-mean token ratio of each arm to `rg0`, over targets where both arms are complete.
- **Margins:** a saving or cost counts as practically meaningful only if the whole interval lies beyond 1/1.5 or 1.5.
