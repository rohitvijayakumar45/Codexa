# Anchored Memory & Budgeted Annotation — Implementation and Experiments

This document describes what was built for the paper proposed in
[`paper_gap_analysis.md`](paper_gap_analysis.md), and how to reproduce every number.

Two contributions, both deterministic and LLM-free at evaluation time:

1. **Code-anchored memory with deterministic invalidation.** Each memory record can be pinned to
   hashable pieces of the repository. When those pieces change, the record is invalidated. The
   exception is episodic history, which is flagged as outdated instead.
2. **Budgeted symbol annotation.** When only K symbols can receive an LLM-written meaning, this
   asks which K to pick. Several selection policies are compared against real future demand
   mined from git history.

---

## 1. What was implemented

### 1.1 Anchors — `backend/memory/anchors.py`

| Anchor kind | Pins a record to | Stale when |
|---|---|---|
| `file` | a repo-relative path and the sha256 of its bytes (or `None`, meaning "must not exist") | the bytes change, the file is deleted, or the file appears |
| `symbol` | `file#qualname` and the content hash of that symbol's source span | that one symbol's source changes, or the symbol disappears |
| `tree` | a hash of the sorted list of every path | a path is added or removed |
| `symbols_index` | a hash of the sorted list of every symbol key | a symbol is added, removed or renamed |
| `query` | a hash of a deterministic graph query result: `callers(X)`, `callees(X)`, `imports(f)`, including whether the subject exists | the answer to the query changes |

`check_anchors(root, anchors)` returns one of three statuses:
- `valid`
- `stale`, together with the anchors that changed
- `unanchored`

Unknown anchor kinds are treated as matching, so the destructive side fails open.

`sweep_repository(store, repo, root)` re-checks every active anchored record:
- **Descriptive** records (`semantic`, `procedural`, `organizational`) are claims about the current
  code. A stale one is soft-invalidated through `invalid_at`: it is kept for audit and never served.
- **Episodic** records are history, which stays true after the code moves on. A stale one gets
  `metadata.outdated_at`. Retrieval still serves it, prefixed with `(code changed since)`.

The sweep only parses the repository when a symbol, tree, index or query anchor needs it. Records
with no anchors are never touched.

### 1.2 Memory store — `backend/memory/store.py`

- `MemoryRecord.anchors` is persisted with the record.
- `add(..., anchors=)` accepts anchors. When the same claim is observed again (corroboration),
  its anchors are re-pinned to the current code and any outdated flag is cleared.
- `invalidate(record_id, reason=)`, `update_metadata(record_id, updates)` and `get(record_id)`
  are new.

### 1.3 Repository ingestion — `backend/repository/api.py::_ingest`

Ingestion used to call `store.remove(repo, source="repo_load")` blindly on every (re)load. It now
works like this:

1. It runs `sweep_repository` over **all** anchored memory of the repository. That covers the
   repo-load digests and the agent-written experience.
2. It rewrites each digest fact with anchors:

   | Fact | Anchored to |
   |---|---|
   | "What X is" | manifests and README |
   | "Project structure" | `tree` |
   | "Stack & conventions" | manifests and `tree` |
   | "How to build & run" | manifests (absent root manifests are anchored as "must not exist") |
   | "Key functions & components" | `symbols_index` |

3. Identical digests corroborate the existing record, which keeps the same id. Changed digests
   explicitly replace it.
4. "Loaded into Codexa (date)" is append-only episodic history. It is written once per explicit
   (re)load. It is not written for startup rehydration or for the post-edit reindex
   (`record_load_event=False`).
5. `CodeSymbol` graph nodes now carry `content_hash` and `end_line`.

### 1.4 Experiential memory — `backend/memory/experience.py`

`JobManager._record_experience` runs once a job has finished for good. It is controlled by
`CODEXA_EXPERIENCE_MEMORY` (default on) and never raises.

It reads the job's **real tool calls** and the exit codes captured from the subprocess. It does
not use the model's narration. From these it writes:

- **Episodic** — `Task <id8>: <request>`: outcome, files modified, deleted and read, and commands
  that exited 0 or failed. It is anchored to the post-job bytes of the touched files, so a later
  change flags it as outdated. It is idempotent per job id.
- **Procedural** — `Verified command: <cmd>`: build, test or run commands (npm, pytest, cargo,
  go, …) that exited 0. The content is stable, so re-verification corroborates the existing record
  and raises its trust. It is anchored to the manifests, so a changed `package.json` invalidates
  "this works here".

### 1.5 Retrieval — `backend/memory/context.py`

- **Retrieval-time freshness.** Records anchored purely to files are re-hashed when they are
  retrieved, which is cheap. Stale descriptive records are invalidated on the spot. Stale episodic
  records are served with the `(code changed since)` prefix. Anchors that need a parse are left to
  the ingest-time sweep.
- **Memory-type ablation.** `CODEXA_MEMORY_TYPES=semantic,procedural` restricts retrieval to the
  listed types. This lets each type's contribution be measured in isolation.

### 1.6 Annotation policies — `backend/repository/annotation_policy.py`

| Policy | Order |
|---|---|
| `callers` (default, the former `_priority`) | library before tests, public before private, then call sites counted by bare name (a class counts as 3) |
| `callers_exact` | the same, but call sites are counted per exact `file#qualname` |
| `pagerank` | PageRank over the call graph (caller → callee) |
| `degree` | in-degree plus out-degree |
| `git_churn` | files most touched in the last 50 commits first; `callers` breaks ties |
| `file_order` | parser order |
| `random` | seeded random order |
| `lazy` | nothing eagerly; a symbol is annotated on its first `lookup_symbol` |

Configuration uses `CODEXA_ANNOTATE_POLICY` and `CODEXA_ANNOTATE_BUDGET` (defaults `callers`
and 80).

`lookup_symbol` never serves a meaning whose stored hash differs from the node's current
`content_hash`. With the `lazy` policy, it writes the meaning on demand under the same cache key.

---

## 2. Experiment A — git-history replay of memory invalidation

`tests/benchmarks/memory_anchoring/replay.py` and `anchoring_facts.py`.

### Method

1. Sample commit pairs (t, t+k) for k ∈ {1, 5, 20}.
2. Export both snapshots with `git archive`, so the working tree is never touched.
3. Parse both snapshots with the production tree-sitter analyzer.
4. At t, extract ground-truth facts:

   | Fact | Content |
   |---|---|
   | F1 | signature: the declaration header, **not** the source hash, so that symbol anchors are not their own ground truth |
   | F2 | callers(X) |
   | F3 | callees(X) |
   | F4 | imports(file) |
   | F5 | build scripts |
   | F6 | dependencies |

5. A fact is **actually stale** if its value recomputed at t+k differs, or if its subject is gone.
6. A fact is **predicted stale** by each policy. For anchor policies, the prediction comes from the
   production `check_anchors`.

### Policies

| Policy | Rule |
|---|---|
| A0 | never invalidate (what memory did between reloads) |
| A1 | repository-level wipe on any change (what reload did) |
| A2 | file anchors |
| A3 | symbol anchors |
| A4 | A3 plus file anchors on the 1-hop graph neighbourhood |
| A5 | graph-query anchors |
| TTL-n | invalidate once n or more commits have passed (time-based expiry baseline) |

### Metrics

| Metric | Meaning |
|---|---|
| precision, recall, F1 | of staleness detection |
| **false-invalidation rate** (FIR) | still-true facts thrown away |
| **stale-served rate** (SSR) | stale facts still served |
| mean anchors per record | storage and check cost |

### Commands

```bash
python tests/benchmarks/memory_anchoring/replay.py --repo .codexa/repos/httpx --ks 1,5,20 --pairs 12 --max-facts 300 --out tests/benchmarks/memory_anchoring/results
```

Repeat `--repo` to run several repositories. The directory must be a git repository **root**;
the harness refuses a subdirectory of an enclosing repository.

## 3. Experiment B — annotation budget vs. future demand

`tests/benchmarks/annotation_budget/run.py`.

### Method

At sampled commits t, each policy ranks the symbols of snapshot t. Every policy is a pure
function, so no LLM calls are made. For each budget K ∈ {0, 20, 40, 80, 160, all}, the top K is
compared against the following demand sets:

| Demand | Definition |
|---|---|
| **D_edit** | symbols whose source changes in the next N commits (the code people work on next) |
| **D_file** | symbols in files that change in the next N commits |
| **D_gold** (optional) | gold symbols of real questions (`--questions` JSONL with fields `question` and `gold_symbols`) |

### Metrics

| Metric | Meaning |
|---|---|
| coverage | the share of each demand set that falls in the top K |
| invalidated_share | the share of the K annotations that are invalidated again within N commits (the cost side of annotating hot code) |
| cost_tokens | prompt-token proxy for the annotation calls |

`random` is the floor and `oracle` is the ceiling. The `lazy` row reports deferred on-demand calls.

### Command

```bash
python tests/benchmarks/annotation_budget/run.py --repo .codexa/repos/httpx --horizon 20 --bases 10 --out tests/benchmarks/annotation_budget/results
```

## 4. Tests

| File | Covers |
|---|---|
| `tests/test_memory_anchors.py` | anchor kinds; store; sweep (descriptive invalidated, episodic flagged, unanchored untouched, idempotent, scoped to one repository); retrieval freshness; ablation switch; anchored ingest (unchanged facts keep their id, changed facts are replaced, no load-event spam, agent facts swept) |
| `tests/test_experience_memory.py` | extraction from real tool calls (compacted arguments, dotfiles, move/delete, unknown exit codes); episode and procedural writes; corroboration; per-job idempotence; anchoring behaviour after code changes; the job hook's env gate, cancelled jobs and never-raise |
| `tests/test_annotation_policy.py` | every policy is a permutation; the `callers` policy is identical to the former production priority; PageRank and degree properties; seeded random; git churn; env configuration; the budget caps LLM calls; the lazy pass makes no calls; on-demand annotation cache; `lookup_symbol` never serves a stale meaning |
| `tests/test_anchor_replay.py` | query anchors; the replay harness on a synthetic five-commit history where every expected hit and miss is known; the annotation harness end to end |

## 5. Known limitations (state these in the paper)

- **F1 exposes the precision cost of content anchors.** A symbol anchor fires on body-only edits
  that leave the signature unchanged.
- **Query anchors are exact by construction** for facts that *are* graph queries. The interesting
  regime is claims that cannot be recomputed, such as LLM glosses and experience. For those, the
  content-anchor results are the relevant ones.
- **A4 neighbourhood file anchors over-invalidate.** Any edit to a caller's file fires them. The
  point of A4 is to fix A3's recall on callers facts at the price of precision.
- **D_edit is a proxy for demand, not observed agent queries.** It measures the code people work
  on next. The gold-question mode exists to pair it with labelled questions.
- **Single-language skew.** httpx dominates the fact count. Report per-repository numbers, not
  only pooled ones.
