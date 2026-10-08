# RQ4 agent pilot — change-signature tasks on fresh fixtures (2026-10-08/09)

**Setup.** 24 tasks (12 Python, 12 TypeScript) from the NavBench `fresh` fixtures. Target kinds:
direct, method (M), re-export, decorated. Five conditions:
- rg
- lsp
- codexa (v1 resolution)
- codexa2
- routed

2 repetitions each, 240 runs planned. Model `nvidia_nim/z-ai/glm-5.3`, temperature 0, at most 30
steps. Tools are structured only, with no shell.

## What went wrong, and what was fixed

1. **Rate limits.** 178 of 240 runs ended at step 1 on NVIDIA NIM `429 Too Many Requests`.
2. **Oracle defect.** Those untouched runs were scored as *successes*, because an untouched fixture
   still runs and type-checks. This produced an apparent "100% success, 0 failures" interim status.
   Now:
   - success also requires the target to carry the new required last parameter, with no default
     (`tasks.signature_changed`);
   - errored runs are excluded from analysis and re-run on resume;
   - requests are spaced (`--min-interval`) and back off longer on 429.
3. **Regrade.** All 240 runs were regraded by replaying their transcripts (`ab/regrade.py`). The
   178 errored runs flipped to failure and are excluded. All 62 valid runs still pass under the
   strict oracle (signature changed and program OK).
4. **Re-run blocked.** A re-run of the 178 errored runs was started and then stopped. NIM still
   returned 429 on a single probe request, so the account appears to be quota-limited.

## Results on the 62 valid runs

Coverage: 13 of 24 tasks, rep 0 only, and only 1 TypeScript task.

| condition | runs | success | mean tokens | steps | sites recall | find_callers / run |
|---|---:|---:|---:|---:|---:|---:|
| rg | 13 | 100% | 16,100 | 8.4 | 1.00 | 0.0 |
| lsp | 13 | 100% | 17,714 | 8.5 | 1.00 | 0.5 |
| codexa | 12 | 100% | 18,758 | 9.2 | 1.00 | 0.6 |
| codexa2 | 12 | 100% | 18,914 | 9.1 | 1.00 | 1.4 |
| routed | 12 | 100% | 17,491 | 8.8 | 1.00 | 0.9 |

On the 12 tasks where all five conditions have a valid run, median tokens per run were:

| condition | median tokens |
|---|---:|
| rg | 11,355 |
| codexa2 | 12,030 |
| codexa | 13,943 |
| routed | 16,330 |
| lsp | 16,548 |

## Reading

- **Ceiling effect, so gate G2 (20–80% success) fails.** Every valid run succeeds in every
  condition, so these fixtures cannot separate the navigators by outcome. The fixtures are small
  (a few files) and the agent can read all of them. Agent success is decoupled from payload
  completeness: codexa's NavBench payload completeness is 36%, yet the agent succeeds 100%, because
  it falls back to reading files.
- **Tokens.** With structure tools available, the agent spends slightly *more* tokens than with
  plain rg. It calls the tool and still reads and searches. This is consistent with the NavBench
  finding that structure does not substitute for search. The samples are too small for a claim.
- **Consequence for the full study.** The tasks must be harder:
  - natural repositories, large enough that reading everything is not an option;
  - targets whose call sites rg alone misses or over-matches (aliases, re-exports, look-alike
    methods);
  - a step or token budget, so that incomplete navigation shows up as failure.

  The re-run of the missing runs needs either a provider without the NIM quota or a slower schedule.

Raw rows and transcripts are in the session scratchpad (`ab-pilot/`). They are not committed.
