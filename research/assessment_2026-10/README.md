# Research assessment (2026-10)

- `RESEARCH_ASSESSMENT.md` — the full report.
- `PROTOCOL.md` — draft measurement protocol (approved for drafting and a small validation pilot only).
- `scripts/payload_recheck.py` — re-runs the retrieval-payload metric with an added grep arm and graph
  precision/recall vs textual and jedi ground truth. Usage:
  `CODEXA_DATA_DIR=<dir with repos/<name>/.codexa-repo.json> TOKMODE=regex|c4 OUT=<dir> python scripts/payload_recheck.py <repo>`
  (needs `pip install jedi`; tiktoken was unreachable here, so tokens are proxied).
- `scripts/selbias.py` — unconditioned-sample recall check (Python repos).
- `results/` — 3-repo engineering pilot (biased by sampling, jedi oracle and task mismatch; not findings) for httpx `b5addb6`, click `2247b35`, axios `2b169bb`.

Read-only investigation: no application code was changed.
