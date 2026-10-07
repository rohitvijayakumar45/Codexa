# Introduction (draft; contribution bullets to be finalised against results)

Coding agents spend much of their context budget finding code, so tools that index repositories as graphs advertise large token savings. Published and tool-reported savings range from about 10× (Codebase-Memory) to "99% fewer tokens" (several MCP servers). A number such as "85.8× fewer tokens" is a property of a measurement, not only of a tool. Three choices drive it:
- what the graph is compared against (whole files, grep, or a language server);
- which queries are sampled (often the graph's own edges);
- in what form outputs are counted (names only, or locations).

We ask:
- **Q1.** How does baseline choice change measured payload ratios?
- **Q2.** How does sampling targets independently, rather than from the graph's own edges, change measured coverage, agreement and tool rankings?
- **Q3.** Which tools reach useful token–quality operating points when outputs follow the same format and quality is measured against labels that no evaluated tool produced?

We answer these with a fully automatic, model-free benchmark. It has three layers:
1. seeded fixtures with generator manifests;
2. 17 public Python and TypeScript repositories, with targets sampled independently of any graph;
3. runtime-observed Python calls.

We apply it to two Tree-sitter graph tools in three versions, ripgrep, and two language servers.

Contributions (wording fixed after results):
1. A measurement protocol and an open harness that separate retrieval coverage from representation size and never use an evaluated tool as ground truth.
2. Quantification of how much baseline choice and graph-conditioned sampling change measured ratios and rankings.
3. Pattern-level correctness profiles of graph, lexical and language-server retrieval on seeded fixtures, plus recall on runtime-observed calls.
4. Reporting recommendations for token-efficiency claims.

# Threats to validity (draft)

**Construct.**
- Payload tokens are not agent tokens or billed cost; agent behaviour and prompt caching are out of scope.
- Caller-level scoring credits a location tool for any returned location inside a true caller.
- Site-level scoring is only defined for location-returning tools.
- Static possible-target labels in fixtures are a semantics choice, not execution truth.

**Internal.**
- The independent index uses Python `ast` and the TypeScript compiler. The latter shares an engine with the TS reference provider, so TS sampling is independent of the graphs but not of the TS language service.
- Tool outputs are mapped to declarations by our resolution rules. Unresolved names are counted and reported, and three resolution fixes were made before the freeze (FREEZE.md).
- Codebase-memory receives the target's qualified name only after it reports ambiguity itself.

**External.**
- Fixtures cover named patterns and are cleaner than natural code.
- The 17 repositories are a purposive, criteria-based selection, not a random sample.
- Two languages only.
- Tool versions drift; we pin a paper-era and a current codebase-memory build.

**Layer C.**
- Recall on observed calls covers only code exercised by test suites within a 900 s budget; tests can over-represent public API calls.
- Unobserved static results are not false positives.
- Subprocesses are not traced.
- No human audit means natural-code accuracy is not measured.
