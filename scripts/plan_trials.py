"""Run the real planning call N times and report what came back each time.

Planning had been failing silently for most of this project's life, and every fix so far was made
against a single observation: one timeout, one truncated reply, one 503. A single run cannot tell a
fixed planner from a lucky one — the failures are provider-dependent and intermittent by nature, so
the only meaningful acceptance test is consecutive successes.

    python scripts/plan_trials.py                 # 3 trials, the LUMEN benchmark request
    python scripts/plan_trials.py 5               # 5 trials
    python scripts/plan_trials.py 3 prompts/bench/small-tidepool.md

Each trial prints the model that answered, the wall clock, the provenance, and — on failure — the
exact reason, which is the thing that was missing every previous time this broke. Exit code is 0
only when every trial proposed a plan.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from backend.agents.llm import LLMClient  # noqa: E402
from backend.agents.plan_builder import _planning_models, build_plan  # noqa: E402
from backend.agents.task import generate_contract  # noqa: E402

# A model writing a non-breaking hyphen into an objective killed this script mid-run on a cp1252
# console — after two trials had already succeeded, so the batch was lost to its own reporting. A
# harness must not be able to fail on the content it is measuring.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

# The job model stays the heavy reasoning model on purpose: it is what actually executes every
# round, and the point of routing PLANNING elsewhere is that decomposition is a helper's job while
# the build is not. Passing it here also exercises the last-resort branch of _planning_models.
JOB_MODEL = "tokenrouter/z-ai/glm-5.3-free"

DEFAULT_REQUEST = """## Benchmark — LUMEN

Build a **single self-contained HTML application** called **LUMEN**, a beautifully designed
**personal journal and life dashboard**.

The home view shows recent entries, a mood and energy summary, and the current streak. Writing an
entry opens a richer reading and editing surface. Entries can be searched and filtered by mood and
by date. Include a signature interaction the product is remembered for, a motion system with one
easing curve and one duration scale, and a deliberate mobile layout with reconsidered navigation
and touch targets. Realistic mock data throughout — no lorem ipsum, no "Entry 1".

Build something beautiful, but more importantly, make the beauty emerge from excellent product and
interaction design rather than decoration alone."""


def trial(n: int, request: str, llm: LLMClient) -> dict:
    contract = generate_contract(request)
    started = time.time()
    plan = build_plan(request, contract, llm=llm, model=JOB_MODEL, repository="Lumen")
    elapsed = time.time() - started

    ok = plan.source == "proposed"
    print(f"\n--- trial {n}: {'PROPOSED' if ok else 'FELL BACK'}  {elapsed:.1f}s  "
          f"{len(plan.tasks)} tasks")
    if not ok:
        print(f"    reason: {plan.source_detail}")
    for i, task in enumerate(plan.tasks, 1):
        print(f"    {i}. {task.objective[:96]}")
    return {"ok": ok, "seconds": elapsed, "detail": plan.source_detail,
            "objectives": [t.objective for t in plan.tasks]}


def main() -> int:
    args = sys.argv[1:]
    trials = int(args[0]) if args and args[0].isdigit() else 3
    source = args[1] if len(args) > 1 else None
    request = Path(source).read_text(encoding="utf-8") if source else DEFAULT_REQUEST

    llm = LLMClient()
    print(f"job model : {JOB_MODEL}")
    print(f"planners  : {' -> '.join(_planning_models(llm, JOB_MODEL))}")
    print(f"request   : {len(request)} chars, {trials} trial(s)")

    results = []
    for i in range(1, trials + 1):
        try:
            results.append(trial(i, request, llm))
        except Exception as exc:  # noqa: BLE001 - a lost trial must not cost the whole batch
            print(f"\n--- trial {i}: HARNESS ERROR {type(exc).__name__}: {exc}")
            results.append({"ok": False, "seconds": 0.0,
                            "detail": f"harness error: {type(exc).__name__}", "objectives": []})

    passed = sum(1 for r in results if r["ok"])
    print("\n" + "=" * 70)
    print(f"{passed}/{len(results)} proposed"
          f"   median {sorted(r['seconds'] for r in results)[len(results) // 2]:.1f}s")
    for i, r in enumerate(results, 1):
        print(f"  trial {i}: {'ok' if r['ok'] else 'FELL BACK — ' + r['detail'][:90]}")

    # Two different plans for the same request would mean the planner is unstable, which matters as
    # much as whether it succeeds: a plan that changes shape run to run cannot be reasoned about.
    shapes = {len(r["objectives"]) for r in results if r["ok"]}
    if len(shapes) > 1:
        print(f"  note: proposed plans varied in length across trials: {sorted(shapes)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
