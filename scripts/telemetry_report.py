"""Read back what backend/agents/round_telemetry.py recorded, and print the comparison.

    python scripts/telemetry_report.py                 # every job in the log
    python scripts/telemetry_report.py <job_id>        # one job
    python scripts/telemetry_report.py --rounds <job>  # round by round

The question this exists to settle: is a job's deliberation driven by ACCUMULATED HISTORY (prior
tasks' prose and tool results piling up in the transcript) or by the STANDING CONTEXT it gets on
every round regardless of history (the design brief, the task prompt, the objective)?

Read the per-task table left to right. If reasoning tracks `prior` — climbing as history grows —
history is the amplifier and per-task transcript scoping is the fix. If reasoning is worst on the
FIRST task, where `prior` is zero, history is not the cause and the standing context is.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents import round_telemetry as telemetry  # noqa: E402


# Windows consoles default to cp1252, which cannot encode a block character — printing one raised
# UnicodeEncodeError and took the whole report down after it had already produced the useful tables.
# A reporting script must not be able to fail on the last line.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def _n(value: object) -> str:
    return f"{int(value or 0):,}"


def _bar(part: int, whole: int, width: int = 24) -> str:
    if whole <= 0:
        return " " * width
    filled = max(0, min(width, round(width * part / whole)))
    return "#" * filled + "." * (width - filled)


def per_task(rows: list[dict]) -> None:
    summary = telemetry.summarize(rows)
    tasks = summary["tasks"]
    if not tasks:
        print("no rounds recorded")
        return

    peak = max(t["context_tokens"] for t in tasks) or 1
    print()
    print(f"{'task':<34} {'rnd':>4} {'context':>9} {'prior':>9} {'prior%':>7} "
          f"{'reasoning':>10} {'tools':>6} {'cuts':>5}")
    print("-" * 92)
    for task in tasks:
        objective = (task["objective"] or task["task_id"])[:33]
        ctx, prior = task["context_tokens"], task["prior_task_tokens"]
        share = f"{(100 * prior / ctx):.0f}%" if ctx else "-"
        print(f"{objective:<34} {task['rounds']:>4} {_n(ctx):>9} {_n(prior):>9} {share:>7} "
              f"{_n(task['reasoning_chars']):>10} {task['tool_calls']:>6} {task['cuts']:>5}")
    print()
    print("context volume by task (# = share of the heaviest task)")
    for task in tasks:
        objective = (task["objective"] or task["task_id"])[:33]
        print(f"  {objective:<34} {_bar(task['context_tokens'], peak)} {_n(task['context_tokens'])}")


def composition(rows: list[dict]) -> None:
    """Where the standing context goes, averaged over rounds. Answers 'is the brief the problem?'"""
    if not rows:
        return
    buckets = [
        "system_base", "task_prompt", "design_brief", "task_context", "directive",
        "user", "assistant_text", "assistant_tool_args", "tool_results",
    ]
    totals = {b: 0 for b in buckets}
    for row in rows:
        ctx = row.get("context") or {}
        for b in buckets:
            totals[b] += int(ctx.get(b, 0))
    grand = sum(totals.values()) or 1
    print()
    print(f"context composition across {len(rows)} round(s) — sum of every round's request")
    print("-" * 92)
    for bucket, value in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"  {bucket:<22} {_n(value):>12}  {100 * value / grand:5.1f}%  {_bar(value, grand)}")


def per_round(rows: list[dict]) -> None:
    print()
    # A cut round never reaches mark_generation_done, so generation_ms is null exactly where the
    # elapsed time is most interesting. Fall back to the round's total, which is always recorded.
    print(f"{'rnd':>4} {'task':<24} {'context':>9} {'prior':>9} {'reason':>8} {'ms':>8} "
          f"{'ttft':>7} {'out':<8} tools")
    print("-" * 100)
    for row in rows:
        ctx = row.get("context") or {}
        objective = (row.get("task_objective") or "-")[:23]
        tools = ",".join(row.get("tool_calls") or []) or "-"
        print(f"{row.get('round', 0):>4} {objective:<24} "
              f"{_n(ctx.get('total')):>9} {_n(ctx.get('prior_task_total')):>9} "
              f"{_n(row.get('reasoning_chars')):>8} "
              f"{_n(row.get('generation_ms') or row.get('total_round_ms')):>8} "
              f"{_n(row.get('first_token_ms')):>7} {row.get('outcome', '-'):<8} {tools[:40]}")


def main() -> int:
    args = [a for a in sys.argv[1:]]
    show_rounds = "--rounds" in args
    args = [a for a in args if not a.startswith("--")]
    job_id = args[0] if args else None

    rows = telemetry.load(job_id=job_id)
    if not rows:
        where = telemetry._path()
        print(f"no telemetry at {where}"
              + (f" for job {job_id}" if job_id else "")
              + "\nRun a job with CODEXA_ROUND_TELEMETRY unset or =1, then try again.")
        return 1

    jobs = sorted({r.get("job_id") for r in rows})
    print(f"{len(rows)} round(s) across {len(jobs)} job(s): {', '.join(str(j) for j in jobs[:6])}"
          + (" ..." if len(jobs) > 6 else ""))

    if show_rounds:
        per_round(rows)
    per_task(rows)
    composition(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
