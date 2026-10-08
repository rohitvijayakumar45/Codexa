# RQ1 Claims audit — coding scheme (v0.1, 2026-10-08)

**Unit of analysis:** one quantitative efficiency claim about a context provider for coding agents.
A context provider is either an on-demand navigation tool (grep, LSP, code graph, retrieval,
compression) or persisted context (context files, agent memory, experience banks). One source can
contain several claims.

## Inclusion

- Public source: a paper (arXiv or proceedings), a tool README or docs, or an official vendor blog.
- 2024-01 to 2026-12.
- A **numeric** claim about tokens, cost, runtime, tool calls, or success *attributable to the
  context provider*.
- Tool READMEs: only tools with ≥ 200 GitHub stars at audit time, or tools cited by an included
  paper.

## Fields

| Field | Values | Notes |
|---|---|---|
| `id` | C### | |
| `source`, `url`, `date`, `kind` | paper / readme / blog / docs | |
| `provider_family` | on-demand / persisted / compression | |
| `provider` | tool or technique name | |
| `claim_text` | ≤ 25 words, paraphrased; a quote only if ≤ 15 words | copyright: no long quotes |
| `metric` | tokens / cost / runtime / tool_calls / success / quality | |
| `headline_value` | e.g. "10×", "−28.6%" | |
| `level` | payload (model-free) / agent | Was an agent in the loop? |
| `baseline` | whole_file / grep_only / grep_read_agent / lsp / no_tool / no_context / vendor_default / unspecified | **B1** |
| `sampling` | graph_conditioned / independent / task_benchmark / self_repo / unspecified | **B2**: were queries drawn from what the tool indexes? |
| `output_form_controlled` | yes / no / na | **B3**: same information content across arms? |
| `completeness_reported` | yes / no | **B4**: quality/recall reported next to the efficiency number? |
| `freshness_considered` | yes / no / na | **B5**: persisted context only — is staleness of context addressed? |
| `variance_reported` | ci / sd / reps_only / none | |
| `n_repos`, `n_queries_or_tasks`, `models` | | |
| `cost_includes_caching` | yes / no / na | agent-level claims |
| `self_evaluation` | yes / no | Did the tool's authors evaluate their own tool? |
| `verified_by` | which coder(s) checked the primary source | |
| `notes` | | |

## Coding protocol

1. Two coders independently code every claim from the **primary source**: full text for papers,
   the README/docs for tools.
2. Report Cohen's κ per field before discussion (target ≥ 0.7 on B1–B5). Resolve disagreements by
   discussion and record the resolution.
3. Re-measurement subset: the 8–10 most-cited claims whose tools are installable are re-run under
   two setups:
   - (a) their own setup, as described;
   - (b) NavBench controls: independent sampling, matched completeness, common form.

## Status

`claims.csv` is the **seed list, coder 1 only**. Coder 1 is the assistant: it extracted these from
abstracts, READMEs and secondary summaries during the literature search. Rows not marked
`verified_by=primary` **must be re-checked against the primary source by a human coder** before use.
