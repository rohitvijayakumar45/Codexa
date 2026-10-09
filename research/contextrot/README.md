# contextrot — how fast does agent context go stale? (combined paper, RQ3)

**`cr/extract.py`** pulls atomic claims from AGENTS.md / CLAUDE.md / copilot-instructions / .cursorrules
etc. Extraction is deterministic: path, command, symbol, dependency (with scoped negation —
"never introduce MongoDB" claims *absence*), directory-tree structure, and residual prose.

**`cr/oracles.py`** checks each claim against a repository snapshot (tracked files only) and returns
`true`, `false`, or `unknown`. `unknown` is never counted as rot.
- Commands must resolve: a package.json script, a Makefile target, `python -m` to a repo module or
  dependency, a `cd` target that exists, path arguments that exist.
- Symbols must be declared (tree-sitter, via Codexa) or present in source text.
- Dependencies must be declared in a manifest, with the major version matching unless the claim
  says "N+".

**`cr/rot.py`** tracks every claim through the file's full git history. For each claim it records
whether it was born stale, rotted, got fixed, or is still valid. It reports per-class Kaplan–Meier
time-to-rot, in commits and in days.

**`pilot.py`** runs this on a seeded random sample of the Baltes et al. dataset (Zenodo
10.5281/zenodo.19375880, CC BY 4.0). Download `context_files.csv` into `data/`; that folder is
gitignored.

```bash
python pilot.py --n 20 --every 25 --max-points 25     # -> work/pilot/{summary.json, lifecycles.jsonl, verdicts_false.jsonl}
```

`verdicts_false.jsonl` is the audit sheet. Before any number is used, a human must check a random
sample of `false` verdicts to estimate oracle precision; gate G1 requires ≥ 0.85.

Tests: `tests/test_contextrot.py`.
