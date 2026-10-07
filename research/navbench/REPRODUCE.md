# Reproducing the navbench study

Linux (or WSL), Python ≥ 3.12 (`sys.monitoring`), Node 22, gcc/make, ripgrep 14. About 3–4 hours on 4 cores.

```bash
# 0. Codexa backend dependencies + analysis libraries (any venv)
python -m pip install -e ../..[dev] numpy scipy matplotlib pandas jedi
cd research/navbench && npm ci          # pinned: pyright 1.1.414, typescript 5.9.3, gpt-tokenizer 4.0.0

# 1. codebase-memory-mcp: current (bf93f0b7) and paper-era (v0.5.7 = b31d1770)
git clone https://github.com/DeusData/codebase-memory-mcp cbm && (cd cbm && git checkout bf93f0b7 && make -f Makefile.cbm cbm CC=gcc CXX=g++ -j4)
git -C cbm worktree add ../cbm057 v0.5.7 && (cd cbm057 && make -f Makefile.cbm cbm CC=gcc CXX=g++ -j4)
mkdir -p /work/nb/bin && cp cbm/build/c/codebase-memory-mcp /work/nb/bin/cbm-cur && cp cbm057/build/c/codebase-memory-mcp /work/nb/bin/cbm-057

# 2. Corpus at the pinned commits (results/corpus_shas.txt); each repo needs .codexa-repo.json
#    Clone each URL from corpus.json into /work/nb/repos/<name>, check out the listed SHA,
#    and write {"url": "<url>"} to /work/nb/repos/<name>/.codexa-repo.json

# 3. Fixtures (deterministic) and the fixture gate
python -m nb.fixtures /work/nb/repos && python -m nb.gate_fixtures /work/nb/repos

# 4. Python test environments for layer C: one venv per repo under /work/nb/venvs/<name>,
#    with `pip install -e .`, the `tests`/`dev` dependency groups (`pip install --group ...`),
#    pytest and pytest-timeout. Then trace:
./trace_all.sh "$(which python)"

# 5. Confirmatory run, scoring, analysis, figures, error taxonomy
./run_all.sh "$(which python)" /work/nb/out-main
CODEXA_DATA_DIR=/work/nb python -m nb.score /work/nb/out-main
python -m nb.analyze /work/nb/out-main/scored.jsonl /work/nb/out-main/analysis
python -m nb.figures /work/nb/out-main/scored.jsonl /work/nb/out-main/figs
CODEXA_DATA_DIR=/work/nb python -m nb.taxonomy /work/nb/out-main

# 6. Post-freeze supplement: codebase-memory-mcp v0.5.5 on the frozen targets, then robustness analyses
git -C cbm worktree add ../cbm055 v0.5.5 && (cd cbm055 && make -f Makefile.cbm cbm CC=gcc CXX=g++ -j4) && cp cbm055/build/c/codebase-memory-mcp /work/nb/bin/cbm-055
# run repositories one at a time (concurrent runs sharing one cache directory can hang)
python -m nb.run_extra_arm /work/nb/out-main <repo> <py|ts> <fixture|natural> /work/nb/out-055   # for every repo in run_all.sh
python -m nb.compare_versions /work/nb/out-main cbm_057 /work/nb/out-055 cbm_055 results/main/supplement_cbm_versions/cbm055_vs_057.json
# run-to-run stability: re-run an existing version on the same targets (label + binary), then compare
python -m nb.run_extra_arm /work/nb/out-main <repo> <py|ts> natural /work/nb/out-057rerun 057 /work/nb/bin/cbm-057
python -m nb.run_extra_arm /work/nb/out-main <repo> <py|ts> natural /work/nb/out-currerun cur /work/nb/bin/cbm-cur
CODEXA_DATA_DIR=/work/nb python -m nb.robustness /work/nb/out-main /work/nb/out-main/scored.jsonl /work/nb/out-main/analysis
```

Re-analysis without re-running: `results/main/scored.jsonl.gz` holds every scored row. Gunzip it and pass it to `nb.analyze` / `nb.figures`. Raw per-query tool outputs (facts, statuses, token counts) are in `results/main/raw_results.tar.gz`.

Token counts use gpt-tokenizer's bundled cl100k/o200k ranks, because tiktoken's vocabulary host was unreachable in the build environment. To cross-check with `tiktoken`, recount `native`/`loc` text from a re-run; the raw output text itself is not stored, only its counts and facts.
