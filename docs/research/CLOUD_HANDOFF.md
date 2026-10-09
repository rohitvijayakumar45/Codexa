# Cloud-environment handoff — combined paper (cost × completeness × currency)

**Branch:** `research/combined-paper`.

**Plan:** [`combined_paper_plan.md`](combined_paper_plan.md).

**Status:** local pilots done (results below, filled in when they finish). Everything here needs a
Linux box with network access, gcc/make, Node 22 and Python ≥ 3.12: the environment where the
frozen `/work/nb` run happened.

## Cloud run status (2026-10-08, branch `claude/upbeat-hamilton-zhq0os`)

| Section | Status |
|---|---|
| §1 NavBench v2 | **Done.** All 81 jobs ran. The frozen arms reproduce `results/main`: rg, LSP and T2 are identical; the only differences are known codebase-memory noise, plus G1 rows that hit an output cap. Results and write-up: `research/navbench/results/v2/RESULTS_V2.md`. **G1-v2 does not transfer to real code:** layer-C recall is 0.69 vs v1's 0.76, because of star re-exports and calls dispatched to overrides. **No routing policy beats rg0 on real code** at matched completeness. |
| §2 Context rot | **Blocked.** The environment's network policy denies `zenodo.org`, so `context_files.csv` cannot be downloaded. Either allow the host or commit the CSV. GitHub clones work. |
| §3 Agent study | **Harder tasks are ready:** `research/agentbench/tasks/natural_v1.json` (see the paragraph below). The `cbm_cur` condition is wired. **The run waits only on a provider API key in this environment** (the keys are in the local `.env`, which is gitignored), a pinned model and a budget. |
| §4 Claims audit | Not started (desk work; needs a second human coder for κ). |

**The natural_v1 task set.**
- 40 change-signature tasks on 9 real Python repositories, graded by each repository's hidden test suite.
- All 40 were validated automatically: the reference solution passes, and omitting any single gold site fails.
- 18 tasks are rg-hostile. Precision is measured by `strict_success`, which requires no over-edits.
- They were drawn from 75 valid tasks out of 286 candidates.
- `ab.natural selftest` passes on all 40 with every condition and no model calls. Flaky tests are deselected (`rebaseline`).
- Run command: `research/agentbench/README.md`.

The scoring fix from NavBench review round 3 (S-ind rows keyed by (declaration, sample)) is merged into `nb/score.py` here.

## 0. Setup (once)

```bash
git fetch origin && git checkout research/combined-paper
python -m pip install -e .[dev] numpy scipy matplotlib pandas jedi
(cd research/navbench && npm ci)                        # pyright 1.1.414, typescript 5.9.3, gpt-tokenizer
# codebase-memory binaries, the corpus at pinned SHAs and the Layer C venvs: research/navbench/REPRODUCE.md §1-4
```

## 1. NavBench full run with the new features (RQ2, RQ5-routing)

Same frozen protocol, with the new arms and tasks added:

```bash
cd research/navbench
python -m nb.fixtures /work/nb/repos && python -m nb.fixtures /work/nb/repos --fresh
python -m nb.gate_fixtures /work/nb/repos                  # must print: GATE fixtures: PASS (now also checks T3 edges)
# per repository (or edit run_all.sh to add the flags):
python -m nb.run <repo> <py|ts> <fixture|natural> /work/nb/out-v2 \
    --arms rg0,rg3,lsp,codexa,codexa2,cbm_cur,cbm_057 --tasks T1,T2,T3
CODEXA_DATA_DIR=/work/nb python -m nb.score /work/nb/out-v2
python -m nb.leaderboard /work/nb/out-v2/scored.jsonl /work/nb/out-v2/lb
python -m nb.policy /work/nb/out-v2/scored.jsonl /work/nb/out-v2/policy --layer A --token-key tok_msa_cl100k
python -m nb.policy /work/nb/out-v2/scored.jsonl /work/nb/out-v2/policy --layer C --token-key tok_msa_cl100k
```

Check that the frozen arms in out-v2 reproduce `results/main` facts. The equivalence script logic is
in `results/features-local/equivalence_v1_frozen.txt`; on Linux, tokens should match exactly.

**Still to build for the scale-up** (plan §3): ~30 repositories meeting the shared corpus criteria
(context file + tests + ≥ 300 commits), Go adapters (optional), a 300-target human audit sheet.

## 2. Context rot at scale (RQ3, S1 + S4)

```bash
cd research/contextrot
mkdir -p data && curl -L -o data/context_files.csv https://zenodo.org/api/records/20090356/files/context_files.csv/content
python pilot.py --n 400 --every 25 --max-points 25        # scale n up; partial clones (blob:limit=512k)
```

- **Gate G1:** a human audits 200 random rows of `work/pilot/verdicts_false.jsonl` (two
  annotators, κ). Required: oracle precision ≥ 0.85, otherwise fix the oracles before reporting.
- **S4 detection baselines still to build:** DOCER-style regex, TTL-28d, whole-file LLM auditor,
  per-claim LLM judge (Anand prompt), Copilot-style just-in-time verification. Also evaluate on
  Anand 2026's released benchmark (arXiv 2609.25130).

## 3. Agent study (RQ4/RQ5)

```bash
cd research/agentbench
export CODEXA_DATA_DIR=/work/ab                            # sandbox root
python -m ab.run --fixtures /work/nb/repos --split fresh --n-tasks 40 \
   --conditions rg,lsp,codexa,codexa2,routed,cbm_cur --model <pinned open model> --reps 3 --out /work/ab/full
python -m ab.analyze /work/ab/full/results.jsonl --navbench-scored /work/nb/out-v2/scored.jsonl --out /work/ab/full/report.md
```

Note: a `cbm_cur` condition is not yet wired in `ab/run.py`'s Navigator. Add a branch that calls the
NavBench `CbmCur` adapter (trace_path) when the binary exists.

**Still to build:**
- natural-repository tasks (from the human-audited targets);
- persisted-context cells C2–C4 (stale AGENTS.md with historical values; anchor-verified;
  "verify first" instruction), which need a restricted `run_command` tool to observe stale-command
  attempts;
- Docker sandboxing in place of structured-only tools.

## 4. RQ1 claims audit (desk work, any environment)

`docs/research/claims_audit/`: extend `claims.csv` to ≥ 50 claims. A second human coder codes all
rows independently; report κ. Re-measure the 8–10 most-cited installable tools under NavBench
controls.

## Local pilot results

### S1 context-rot pilot (RQ3): done

Full write-up: `research/contextrot/PILOT_S1.md`. 20 repositories, 1,275 checkable claims, oracle v2.

- **Rot (true → false):** 8 claims in total, 4 path and 4 symbol. All 8 look genuine on inspection,
  and 3 were later fixed in the file. The signal is precise but sparse.
- **Born stale:** path 119, symbol 60, command 10, dependency 4. Coder-1 self-audit precision is only
  about 0.4 for path, 0.5 for command and 0.1 for symbol, so **gate G1 is not passed**. Born-stale
  counts are an upper bound only.
- **Decisions for the cloud run:**
  1. The primary metric is transition-based rot.
  2. Use ≥ 1,000 repositories (about 50× the pilot) and prefer older context files.
  3. Add an "is this an assertion about the current repository?" classifier, with its own
     human-validated precision.
  4. Run a human audit of 200 false verdicts by two annotators, reporting κ, before publishing any
     number.

### RQ4 agent pilot: partial (provider quota)

Full write-up: `research/agentbench/PILOT_RQ4.md`.

- 178 of 240 runs died on NVIDIA NIM 429 errors. The first oracle also counted untouched trees as
  successes. Both are fixed: success now requires the signature change, errored runs are excluded
  and re-run on resume, and requests are throttled. All 240 runs were regraded from transcripts.
- **62 valid runs: 100% success in every condition (ceiling), so gate G2 is not passed.** On the 12
  tasks where all five conditions have a valid run, median tokens were: rg 11.4k, codexa2 12.0k,
  codexa 13.9k, routed 16.3k, lsp 16.5k. Structure tools did not reduce tokens.
- **Decisions for the cloud run:**
  1. Use harder tasks: natural repositories, rg-hostile targets, and a step or token budget.
  2. Pin a model on a provider with enough quota, keeping `--min-interval`.
  3. Wire `cbm_cur`.
  4. Re-running the pilot itself is only a smoke test. Use `--out` on a fresh directory, or resume
     the old one: errored rows are re-run automatically.
