"""The 2x2 that separates "declares an artifact" from "must generate a lot of text".

A live run produced a clean split: every task with `expected_artifacts` went to the reasoning
ceiling and was cut (5 of 5), and every task without one acted immediately (0 of 3). Two tasks run
back to back at 91% inherited context spent 40,056 characters and 0 respectively, which rules out
history and rules out context volume.

But the two candidate causes are perfectly confounded in that run: every artifact task was also a
task that had to emit thousands of tokens of source. So "the task names an artifact" and "the round
must generate a large payload" predict the data equally well, and they imply completely different
fixes — one belongs in the task contract, the other in the generation budget.

This separates them. Four single-task jobs, same model, same repository, same design brief:

    A  artifact + tiny output     add one meta tag to an existing file
    B  no artifact + large output write a long analysis into the reply, touch nothing
    C  artifact + large output    write a complete page          (the pathological case)
    D  no artifact + tiny output  name one constraint in a sentence   (the control)

Read the result as a table. Reasoning high in A and C means the ARTIFACT is the trigger. High in
B and C means GENERATION SIZE is. High only in C means it takes both. High everywhere means neither
and the cause is somewhere else entirely.

Each arm runs as its own job id, so backend/agents/round_telemetry.py separates them for free:

    python scripts/experiment_2x2.py            # all four, in order
    python scripts/experiment_2x2.py A C        # only these arms
    python scripts/telemetry_report.py exp-A-artifact-tiny --rounds

Run it with the backend idle. The free GLM endpoint is rate limited per key, and an arm competing
with a live benchmark for that quota measures the queue rather than the model.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from backend.agents import round_telemetry as telemetry  # noqa: E402
from backend.agents.jobs import Job, JobManager, _attach_preamble  # noqa: E402
from backend.agents.design_intent import brief as design_brief, derive as derive_design  # noqa: E402
from backend.agents.llm import LLMClient  # noqa: E402
from backend.agents.plan import ExecutionPlan, make_task  # noqa: E402
from backend.agents.task import (  # noqa: E402
    build_task_prompt,
    classify_intent,
    generate_contract,
)
from backend.agents.tools import groups_providing  # noqa: E402

MODEL = "tokenrouter/z-ai/glm-5.3-free"
REPOS = ROOT / ".codexa" / "repos"

# A small, real page for the arms that edit rather than create. Written fresh for each run so arm A
# always starts from identical bytes — an arm whose starting file differs between runs is not a
# controlled arm.
SEED_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Tidepool</title>
<style>
  :root { --paper: #f7f4ee; --ink: #23201b; }
  body { background: var(--paper); color: var(--ink); font-family: Georgia, serif; margin: 0; }
  main { max-width: 40rem; margin: 4rem auto; padding: 0 1.5rem; }
  h1 { font-size: 2rem; font-weight: 400; }
</style>
</head>
<body>
<main>
  <h1>Tidepool</h1>
  <p>A field guide to twelve rock-pool creatures.</p>
</main>
</body>
</html>
"""

ARMS = {
    "A": {
        "id": "exp-A-artifact-tiny",
        "label": "artifact + tiny output",
        "repo": "exp-a-artifact-tiny",
        "seed": True,
        "_asks": (
            "Add a theme-color meta tag to index.html so the browser chrome matches the page's "
            "paper background. Change nothing else."
        ),
        "objective": 'Add <meta name="theme-color" content="#f7f4ee"> to index.html',
        "artifacts": ["index.html"],
        "tools": ["edit_file"],
        "criteria": ["index.html contains a theme-color meta tag", "Nothing else in the file changed"],
    },
    "B": {
        "id": "exp-B-noartifact-large",
        "label": "no artifact + large output",
        "repo": "exp-b-noartifact-large",
        "seed": True,
        "_asks": (
            "Read index.html and write a long, detailed critique of its typography, colour, "
            "spacing and structure directly in your reply — at least 1,500 words. Do not modify "
            "any file."
        ),
        "objective": (
            "Read index.html and write a 1,500-word critique of it in your reply, changing no files"
        ),
        "artifacts": [],
        "tools": ["read_file"],
        "criteria": ["The critique is in the reply itself", "No file on disk was modified"],
    },
    "C": {
        "id": "exp-C-artifact-large",
        "label": "artifact + large output",
        "repo": "exp-c-artifact-large",
        "seed": False,
        "_asks": (
            "Build a single self-contained HTML page called TIDEPOOL: a field guide to twelve "
            "rock-pool creatures, roughly 300-500 lines, one file, index.html."
        ),
        "objective": "Write the complete first version of index.html",
        "artifacts": ["index.html"],
        "tools": ["write_file"],
        "criteria": ["The file exists on disk and is complete enough to open"],
    },
    "D": {
        "id": "exp-D-noartifact-tiny",
        "label": "no artifact + tiny output",
        "repo": "exp-d-noartifact-tiny",
        "seed": True,
        "_asks": (
            "Look at index.html and name, in one sentence, the single most important design "
            "constraint it is working under. Do not modify any file."
        ),
        "objective": "Read index.html and name its primary design constraint in one sentence",
        "artifacts": [],
        "tools": ["read_file"],
        "criteria": ["One sentence, naming one constraint", "No file was modified"],
    },
}


def prepare_repo(arm: dict) -> str:
    """A fresh repository per arm, so no arm inherits another's files or another's history."""
    path = REPOS / arm["repo"]
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    if arm["seed"]:
        (path / "index.html").write_text(SEED_PAGE, encoding="utf-8")
    return arm["repo"]


# Every arm is given the SAME request, the same contract, the same design brief and the same tool
# set. A first draft of this experiment derived each of those from the arm's own wording, and the
# dry run showed the damage immediately: arm B came out as CREATE_ARTIFACT with no design brief at
# all while the others were MODIFY_ARTIFACT with one. That would have made "no artifact" and "no
# design brief" the same column, and any difference between arms unattributable.
#
# So the standing context is fixed and the plan's single task is the only thing that varies, which
# is exactly the variable under test.
COMMON_REQUEST = (
    "Build a single self-contained HTML page called TIDEPOOL: a field guide to twelve rock-pool "
    "creatures. One file, index.html, roughly 300-500 lines. A light, calm, field-notebook feel: "
    "warm paper background, ink-dark text, one restrained accent, hairline rules, generous "
    "whitespace. Filtering by tide zone that reorganises the list, and a detail view for each "
    "creature."
)


def _shared_context() -> tuple[dict, object, str, list[str]]:
    """Contract, design intent, preamble and tool groups — derived once, reused by every arm."""
    contract = generate_contract(COMMON_REQUEST)
    intent = derive_design(COMMON_REQUEST, contract)
    groups = set(classify_intent(COMMON_REQUEST)) | groups_providing(contract.required_tools)
    # The union of every arm's tools, so no arm is distinguishable by what it was allowed to call.
    for arm in ARMS.values():
        groups |= groups_providing(arm["tools"])
    if intent is not None:
        groups |= groups_providing(["get_design_guidance", "screenshot", "start_dev_server"])
    preamble = "\n\n".join(x for x in (build_task_prompt(contract), design_brief(intent)) if x)
    contract_dict = {
        "intent": contract.intent.value,
        "required_tools": contract.required_tools,
        "allowed_tools": contract.allowed_tools,
        "success_criteria": contract.success_criteria,
        "constraints": contract.constraints,
        "suggested_workflow": contract.suggested_workflow,
    }
    return contract_dict, intent, preamble, sorted(groups)


def build_job(arm: dict, shared: tuple) -> Job:
    """Assemble a job exactly as JobManager.start would, then replace its plan with one task."""
    contract_dict, intent, preamble, groups = shared
    job = Job(
        id=arm["id"],
        repository=arm["repo"],
        model=MODEL,
        working_repo=arm["repo"],
        messages=[{"role": "user", "content": COMMON_REQUEST}],
        message_rounds=[0],
        contract_source=COMMON_REQUEST,
        active_tool_groups=list(groups),
        contract=dict(contract_dict),
        design=intent.to_dict() if intent else None,
    )
    _attach_preamble(job, preamble)

    # The variable under test. One task, so an arm measures one task's behaviour and nothing else.
    plan = ExecutionPlan(objective=COMMON_REQUEST, tasks=[make_task(
        objective=arm["objective"],
        index=0,
        required_tools=arm["tools"],
        expected_artifacts=arm["artifacts"],
        completion_criteria=arm["criteria"],
    )])
    job.plan = plan.to_dict()
    # Generous but finite: an arm that runs away should end, not hang the experiment.
    job.round_budget = 8
    return job


def run_arm(key: str, manager: JobManager, shared: tuple) -> dict:
    arm = ARMS[key]
    prepare_repo(arm)
    job = build_job(arm, shared)
    print(f"\n=== arm {key}: {arm['label']} — {arm['objective'][:60]}")
    started = time.time()
    try:
        manager._loop(job, resuming=False)
    except Exception as exc:  # noqa: BLE001 - one arm failing must not lose the other three
        print(f"    arm {key} raised: {type(exc).__name__}: {exc}")
    elapsed = time.time() - started

    rows = telemetry.load(job_id=arm["id"])
    reasoning = sum(int(r.get("reasoning_chars", 0)) for r in rows)
    cuts = sum(1 for r in rows if r.get("outcome") == "cut")
    tools = [t for r in rows for t in (r.get("tool_calls") or [])]
    artifact = REPOS / arm["repo"] / "index.html"
    print(f"    rounds={len(rows)} reasoning={reasoning:,} cuts={cuts} "
          f"tools={','.join(tools) or '-'} status={job.status} {elapsed:.0f}s")
    return {
        "arm": key,
        "label": arm["label"],
        "artifact_declared": bool(arm["artifacts"]),
        "rounds": len(rows),
        "reasoning_chars": reasoning,
        "cuts": cuts,
        "tools": tools,
        "status": job.status,
        "seconds": round(elapsed),
        "artifact_bytes": artifact.stat().st_size if artifact.exists() else 0,
    }


def main() -> int:
    wanted = [a.upper() for a in sys.argv[1:] if a.upper() in ARMS] or list(ARMS)
    manager = JobManager(llm=LLMClient(), graph=None, store=None)
    shared = _shared_context()
    print(f"shared context: intent={shared[0]['intent']} "
          f"design_brief={'DESIGN INTENT' in shared[2]} tool_groups={len(shared[3])}")
    results = [run_arm(key, manager, shared) for key in wanted]

    print("\n" + "=" * 78)
    print(f"{'arm':<4} {'shape':<28} {'rounds':>7} {'reasoning':>11} {'cuts':>5} {'bytes':>8}")
    print("-" * 78)
    for row in results:
        print(f"{row['arm']:<4} {row['label']:<28} {row['rounds']:>7} "
              f"{row['reasoning_chars']:>11,} {row['cuts']:>5} {row['artifact_bytes']:>8,}")

    print("""
How to read it:
  high in A and C, low in B  -> the ARTIFACT declaration is the trigger
  high in B and C, low in A  -> GENERATION SIZE is the trigger
  high only in C             -> it takes both together
  high everywhere            -> neither; the cause is elsewhere""")

    out = ROOT / ".codexa" / "experiment_2x2.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwritten to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
