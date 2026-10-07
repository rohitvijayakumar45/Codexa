# Related work (draft; verify every citation against the full text before submission)

**Code graphs for LLM agents.**
- RepoGraph (Ouyang et al., ICLR 2025), CodexGraph (Liu et al., NAACL 2025) and LocAgent (Chen et al., ACL 2025) give agents repository graphs and report gains on SWE-bench and localization benchmarks. ARISE (2026, preprint) adds statement-level data-flow edges.
- Codebase-Memory (Vogel et al., 2026, preprint) exposes a Tree-sitter knowledge graph over MCP. It compares a graph-tool agent with an agent using file reading and grep, reporting 83% vs 92% answer quality at about 10× fewer tokens.
- "Code Isn't Memory" (2026, preprint) finds that a structural index improves localization within a fixed harness. The resolve gains are language-dependent.
- These studies measure agent-level outcomes. We measure the retrieval step in isolation, with labels that do not come from any evaluated tool.

**Lexical vs semantic retrieval for agents.**
- "Is Grep All You Need?" (Sen et al., 2026, preprint) shows that grep is a strong baseline and that the harness matters as much as the retriever.
- Xu (2026, preprint) measures whether a language server saves tokens for coding agents, in a five-arm ablation that uses pyright as the reference-completeness oracle. LSP costs tokens on localization; on reference tasks it buys precision without saving tokens, and agents rarely invoke it when it is optional.
- CodeNib (2026, preprint) compares static navigation with live language servers on 1,000 requests: 87.4% definition agreement vs 39% reference agreement. It notes that its queries come from the static graph.
- Our study complements these in four ways:
  - it is model-free;
  - it evaluates graph tools against grep and language servers under equivalent output formats;
  - it uses seeded fixtures with independent manifests, and runtime-observed calls, as labels;
  - it measures how sampling from a graph's own edges changes conclusions.

**Call-graph construction.** PyCG (Salis et al., ICSE 2021) reports high precision and about 70% recall for Python call graphs. That bounds what any name-resolving static graph can achieve, and motivates runtime-observed calls as an independent population.

**Token cost of agents.**
- Bai et al. (2026, preprint) report up to 30× run-to-run token variance on the same agentic task.
- Weinberger & Hozez (2026, preprint) show that reducing tool-output tokens can increase billed cost under prompt caching.
- We therefore report payload tokens only, and claim nothing about agent cost.
