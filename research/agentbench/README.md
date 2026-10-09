# agentbench — do payload results carry over to agents? (combined paper, RQ4/RQ5)

**Task (T-callers).** Add a required trailing parameter to a function or method, and update every
call site. The repository's own execution is the oracle:
- Python: `python main.py` runs every call path.
- TypeScript: `tsc --noEmit --strict`.

Both reject a missed call site *and* a wrongly edited look-alike, so success measures the
completeness and precision of the agent's call-site knowledge with no LLM judge. Tasks are
generated from NavBench fixtures, so gold sites are known for per-site diagnosis.

**Agent.** `ab/agent.py` is a minimal tool-calling loop over litellm. Its tools are structured:
list, read, exact-replace, `search` (ripgrep -w, which every condition has), run the program, and
finish. There is no shell, so it is safe without Docker; this is a threat to validity, because
production agents have shells.

**Conditions** add a `find_callers` tool backed by NavBench adapters:

| Condition | `find_callers` backed by |
|---|---|
| `rg` | none (search only) |
| `lsp` | language server |
| `codexa` | frozen G1 |
| `codexa2` | G1-v2 |
| `routed` | codexa2, plus an rg fallback on a weak answer |
| `cbm_cur` | codebase-memory-mcp (current build, `$NB_CBM_CUR`), `trace_path` inbound depth 1 |

```bash
python -m ab.run --fixtures <navbench fixtures> --split fresh --n-tasks 24 \
  --conditions rg,lsp,codexa,codexa2,routed --model nvidia_nim/z-ai/glm-5.3 --reps 2 --out <dir>
python -m ab.analyze <dir>/results.jsonl --navbench-scored <scored_fresh.jsonl> --out <dir>/report.md
```

**Natural-repository tasks (harder; `ab/natural.py`).** These are change-signature tasks on the 9 pinned
NavBench Python repositories, graded by each repository's own test suite. The suite stays hidden from the
agent: its `run_program` is only a syntax check.

Every task is validated automatically:
- the reference solution passes;
- omitting any single gold call site makes tests fail;
- look-alike detection is recorded.

`strict_success` additionally requires no static over-edits, i.e. no call outside the gold sites gets the new
argument. Selection is stratified by repository and by rg-hostility (name occurrences per gold site ≥ 3).

```bash
NB_DATA_DIR=/work/nb python -m ab.natural build <navbench out-v2> <build_dir>     # validate candidates
python -m ab.natural select <build_dir>/validated.jsonl tasks/natural_v1.json --n 40
CODEXA_DATA_DIR=/work/ab python -m ab.natural selftest tasks/natural_v1.json <build_dir>/validated.jsonl   # no LLM
CODEXA_DATA_DIR=/work/ab python -m ab.run --tasks-file tasks/natural_v1.json --n-tasks 40 \
   --conditions rg,lsp,codexa,codexa2,routed,cbm_cur --model <pinned model> --reps 3 \
   --max-steps 40 --token-budget 200000 --min-interval 2 --out /work/ab/natural-run
```

Requirements:
- `CODEXA_DATA_DIR` must point at a scratch folder; each run's sandbox lives in `$CODEXA_DATA_DIR/repos`.
- ripgrep must be on PATH.
- `npm ci` must have been run in research/navbench (pyright, typescript).

Tests: `tests/test_agentbench.py`.
