# S1 pilot — context rot in 20 random repositories (2026-10-08)

**Sample.** 20 repositories drawn with seed 20261008 from the Baltes et al. dataset (Zenodo
10.5281/zenodo.19375880). Inclusion: AGENTS.md / CLAUDE.md / copilot-instructions, ≥ 3 commits,
≥ 20 lines.
- 20 of 20 were processed; 16 have trackable claims. The other 4 have 0–1 checkable claims, mostly
  prose, which is itself a finding.
- 1,275 checkable claims.
- Observed history: 2–472 days, median ≈ 300.

**Method.** Each context file was replayed at up to 20 points of its history, with the claims
checked against the code at each point (`cr/rot.py`). This report uses oracle v2, after the fixes
from the v1 self-audit below.

## Results

| Class | Claims | Decidable | Born stale (upper bound) | **True → false (rot)** | Valid | Stale at HEAD (upper bound) |
|---|---:|---:|---:|---:|---:|---:|
| path | 590 | 569 | 119 | **4** | 446 | 96 |
| symbol | 467 | 463 | 60 | **4** | 399 | 35 |
| command | 176 | 135 | 10 | 0 | 125 | 8 |
| dependency | 30 | 25 | 4 | 0 | 21 | 3 |
| structure | 12 | 12 | 0 | 0 | 12 | 0 |

- **15 of 16** repositories have at least one claim flagged stale at HEAD. That is an *upper bound*;
  see the precision notes.
- All 8 true → false cases were inspected by coder 1 (the assistant) and look genuine:
  - deleted directories referenced as current (`packages/discovery-provider`, after 147 days, never
    fixed; `schemas/`, after 226 days);
  - a deleted CI workflow;
  - symbols removed from the code.
  - 3 of the 8 were later fixed in the file.

## Precision (gate G1) — NOT passed yet

**v1 oracle self-audit.** In random samples of false verdicts, most born-stale flags were not
existence claims at all:
- bare filenames that live in sub-directories;
- examples and templates;
- acronyms in backticks;
- container-internal and system paths;
- branch names;
- the English verb "express".

v2 fixed the systematic ones: path flags fell 281 → 119, symbol 142 → 60, structure 11 → 0.

**v2 self-audit, coder 1, 10 per class.** Born-stale precision is still low:

| Class | Approx. precision | Typical false flags |
|---|---|---|
| path | ~0.4 | templates `yyyy-MM-dd_*.csv`, `/opt/...` install paths, `a.cpp/h` shorthand, branch names |
| command | ~0.5 | `cd /workspace` inside a container, generated build dirs, placeholder test ids |
| symbol | ~0.1 | coding-style examples, tool names, prefixes |

**True → false transitions look high-precision** (8 of 8 plausible), because the claim was verifiably
true when written.

**Consequences for the full study:**
1. The **primary rot metric must be transition-based**: claims verified true at some point, later
   false. Born-stale counts are reported only as an upper bound, until an "is this an assertion
   about the current repository?" classifier is added. That classifier would be an LLM step
   (hybrid detection, as Treude & Baltes suggest), and it needs its own human-validated precision.
2. **Volume.** 8 transitions in 1,275 claims over histories of about a year is too few for survival
   curves. The cloud run needs roughly 50× the sample (≥ 1,000 repositories) and older files.
3. A human audit of 200 false verdicts (two annotators, κ) is still required before any number is
   published.

Files are in `work/pilot/` (gitignored; they contain third-party text):
- `summary.json`;
- `lifecycles.jsonl`;
- `verdicts_false.jsonl` (the audit sheet).

The v1 run is kept in `work/pilot_v1/`.
