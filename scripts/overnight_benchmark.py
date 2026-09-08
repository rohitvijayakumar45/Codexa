"""Overnight autonomous benchmark driver: VELUM, then AURELIA, then HELIX.

Three requirements shape this script, and two of them are in tension:

  1. Strictly sequential. Never two jobs at once — not across benchmarks, and not two on the same
     repository, which was observed happening and left two agents overwriting each other's
     index.html.
  2. Never abandon a benchmark. A project that fails repeatedly is deferred and returned to, not
     written off.
  3. All three must finish, polished.

(2) and (3) pull against each other: under a naive "never give up", a benchmark that cannot succeed
would consume the entire night and leave the other two untested. The resolution is slicing rather
than abandonment. Each benchmark gets a bounded stretch of wall-clock; if it has not finished when
that runs out it is DEFERRED, the driver moves on, and every deferred benchmark is returned to on
the next lap. Nothing is ever marked abandoned, and nothing can monopolise the night.

Completion is decided against the filesystem, never against a job's own status. `status == "done"`
is the model's claim plus Codexa's task validation, and the point of this exercise is that neither
is sufficient alone — a run was seen reporting done having replaced a real 26KB page with the
11-byte string "PLACEHOLDER". A benchmark advances only when its artifact is on disk AND passes the
substance check in backend/agents/validators.py.

Building is not finishing. After the build job completes, each benchmark gets explicit refinement
passes: run it, look at it, fix what looks wrong, look again. "Do not stop at the first successful
build" is a requirement, so it is a phase here rather than a hope about what the model will choose
to do on its own.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# This machine intercepts TLS/HTTP, so a default opener silently fails against localhost.
os.environ["NO_PROXY"] = "*"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

BASE = "http://127.0.0.1:8090"
LOG_PATH = ROOT / "BENCHMARK_LOG.md"
STATE_PATH = ROOT / ".benchmark-state.json"
JOBS_DIR = ROOT / "backend" / "data" / "jobs"

BENCHMARKS = [
    {"name": "VELUM", "repo": "velum", "prompt": "prompts/overnight/1-velum.md",
     "artifacts": ["index.html"], "kind": "single-file"},
    {"name": "AURELIA", "repo": "aurelia", "prompt": "prompts/overnight/2-aurelia.md",
     "artifacts": ["index.html"], "kind": "single-file"},
    {"name": "HELIX", "repo": "helix", "prompt": "prompts/overnight/3-helix.md",
     "artifacts": [], "kind": "full-stack"},
]

POLL_SECONDS = 30
# No checkpoint in this long means the job is not working, whatever its status says. Checkpoints
# happen at every round boundary and task transition, so a busy job — even one generating a very
# large file — touches disk far more often than this.
STALE_AFTER_SECONDS = 18 * 60
# Wall-clock one benchmark may hold before being deferred to the next lap. Not a deadline for
# finishing: a benchmark that runs out is requeued, never dropped.
BUILD_SLICE_SECONDS = 95 * 60
REFINE_SLICE_SECONDS = 45 * 60
# Refinement passes once the artifact exists and is substantive. Three is what "multiple deliberate
# visual refinement passes" asks for: run it, fix what the screenshot shows, run it again.
REFINE_PASSES = 3
TOTAL_HOURS = 8.5


def now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def log(text: str = "") -> None:
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text, flush=True)


def entry(benchmark: str, phase: str, **fields) -> None:
    log(f"\n### {benchmark} · {phase} · {now()}\n")
    for key, value in fields.items():
        if value:
            log(f"**{key.replace('_', ' ').title()}:** {value}\n")


def api(path: str, body: dict | None = None, timeout: int = 120):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with _OPENER.open(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


def wait_for_backend(attempts: int = 60) -> bool:
    for _ in range(attempts):
        try:
            api("/chat/models", timeout=15)
            return True
        except Exception:  # noqa: BLE001
            time.sleep(5)
    return False


def ensure_repo(name: str) -> None:
    for _ in range(6):
        try:
            api("/repository/create", {"name": name, "description": "overnight benchmark"})
            return
        except urllib.error.HTTPError as exc:
            if exc.code == 400:  # already exists — resuming, which is fine
                return
            raise
        except Exception:  # noqa: BLE001 - backend restarting
            wait_for_backend(attempts=24)


def checkpoint(job_id: str) -> dict | None:
    try:
        return json.loads((JOBS_DIR / f"{job_id}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def running_jobs(repo: str | None = None) -> list[str]:
    out = []
    for path in JOBS_DIR.glob("*.json"):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if d.get("status") == "running" and (repo is None or d.get("working_repo") == repo):
            out.append(d["id"])
    return out


def quiesce(repo: str | None = None, timeout: int = 180) -> None:
    """Stop every running job and WAIT until none is left before returning.

    Cancellation in Codexa is cooperative — checked between rounds — so a job mid-round keeps going
    after cancel returns, and a backend restart can revive an orphaned job when a subscriber
    reattaches. Both happened: two jobs ran against `velum` simultaneously, both writing index.html,
    each discarding the other's work. Firing cancel and hoping is not stopping something.
    """
    ids = running_jobs(repo)
    if not ids:
        return
    log(f"  `{now()}` quiescing {len(ids)} job(s){' on ' + repo if repo else ''}")
    for jid in ids:
        try:
            api(f"/chat/agent/job/{jid}/cancel", {}, timeout=30)
        except Exception:  # noqa: BLE001
            pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not running_jobs(repo):
            return
        time.sleep(5)
    for jid in running_jobs(repo):
        path = JOBS_DIR / f"{jid}.json"
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            d["status"], d["cancelled"] = "interrupted", True
            path.write_text(json.dumps(d), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass
    log(f"  `{now()}` WARNING: forced {repo or 'all'} job(s) to interrupted after {timeout}s")


def artifacts_ok(repo: str, artifacts: list[str]) -> tuple[bool, str]:
    """Reality check, using the platform's own substance rule rather than a second opinion — so the
    driver and the agent cannot disagree about what "produced" means."""
    from backend.agents.validators import _substance_problem

    root = ROOT / ".codexa" / "repos" / repo
    if not root.exists():
        return False, "repository does not exist yet"
    if not artifacts:  # full-stack: judged by breadth of real files
        files = [p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts
                 and "node_modules" not in p.parts]
        real = [p for p in files if p.stat().st_size > 200]
        return len(real) >= 8, f"{len(real)} substantive files"
    problems = []
    for rel in artifacts:
        problem = _substance_problem(root / rel)
        if problem:
            problems.append(f"{rel} {problem}")
    if problems:
        return False, "; ".join(problems)
    return True, ", ".join(f"{a} ({(root / a).stat().st_size:,} bytes)" for a in artifacts)


def start_job(repo: str, prompt: str) -> str:
    quiesce()  # global: no two benchmark jobs may ever overlap
    last: Exception | None = None
    for _ in range(10):
        try:
            return api("/chat/agent", {"repository": repo,
                                       "messages": [{"role": "user", "content": prompt}]})["job_id"]
        except Exception as exc:  # noqa: BLE001
            last = exc
            log(f"  `{now()}` could not start job ({type(exc).__name__}); waiting for backend")
            if not wait_for_backend(attempts=24):
                time.sleep(15)
    raise RuntimeError(f"backend never accepted a job: {last}")


def watch(name: str, repo: str, job_id: str, prompt: str, artifacts: list[str],
          slice_seconds: int, phase: str) -> str:
    """Drive one job to a conclusion within its slice.

    Returns "complete" (artifact verified), "deferred" (slice spent), or "failed" (recovery budget
    spent). None of these abandon anything — the caller requeues.
    """
    recoveries = 0
    last_round = -1
    last_change = time.time()
    started = time.time()

    while True:
        time.sleep(POLL_SECONDS)

        if time.time() - started > slice_seconds:
            quiesce(repo)
            ok, detail = artifacts_ok(repo, artifacts)
            if ok and phase != "build":
                return "complete"
            entry(name, f"Deferred ({phase})",
                  observed_problem=f"slice of {slice_seconds // 60} min spent",
                  result="paused and requeued so the other benchmarks get their turn; returned to "
                         "on the next lap, not abandoned",
                  artifacts=detail)
            return "deferred"

        data = checkpoint(job_id)
        if data is None:
            continue

        status, rnd = data.get("status"), data.get("round", 0)
        if rnd != last_round:
            last_round, last_change = rnd, time.time()
            plan = data.get("plan") or {}
            tasks = plan.get("tasks", [])
            done = sum(1 for t in tasks if t["status"] == "COMPLETED")
            active = next((t["objective"] for t in tasks if t["status"] == "IN_PROGRESS"), "-")
            log(f"- `{now()}` {name} [{phase}] r{rnd}/{data.get('round_budget')} · "
                f"{done}/{len(tasks)} tasks · {len(data.get('tools_called', []))} tools · {active[:52]}")

        stalled = time.time() - last_change > STALE_AFTER_SECONDS
        if status == "running" and not stalled:
            continue

        ok, detail = artifacts_ok(repo, artifacts)
        if status == "done" and ok:
            return "complete"

        recoveries += 1
        if recoveries > 8:
            entry(name, f"Recovery budget spent ({phase})", observed_problem=detail,
                  result="requeued for a later lap rather than abandoned")
            quiesce(repo)
            return "failed"

        reason = data.get("error_reason")
        if status == "done" and not ok:
            # The job says finished; the filesystem says otherwise. Believing the job here is exactly
            # the silent-success failure this benchmark exists to detect, so the claim loses.
            entry(name, "Completion claim rejected",
                  observed_problem=f"reported done but {detail}",
                  likely_cause="a narrative reply treated as delivery",
                  solution="re-issued against the same repository",
                  result=f"recovery {recoveries}/8")
            job_id = start_job(repo, prompt)
        elif stalled and status == "running":
            entry(name, "Stalled",
                  observed_problem=f"no checkpoint for {STALE_AFTER_SECONDS // 60} min",
                  likely_cause="provider stopped responding mid-round",
                  solution="cancelled and relaunched", result=f"recovery {recoveries}/8")
            quiesce(repo)
            job_id = start_job(repo, prompt)
        else:
            entry(name, "Error", observed_problem=f"error_reason={reason}",
                  solution="continue" if reason else "relaunch",
                  result=f"recovery {recoveries}/8")
            resumed = False
            if reason:
                try:
                    api(f"/chat/agent/job/{job_id}/continue", {})
                    resumed = True
                except Exception as exc:  # noqa: BLE001
                    log(f"  continue failed ({exc}); relaunching")
            if not resumed:
                job_id = start_job(repo, prompt)
        last_change, last_round = time.time(), -1


# The leading imperative here matters more than it looks. backend/agents/task.py classifies intent
# by the earliest LINE-LEADING verb, and an earlier version of this brief opened its numbered list
# with "Run the application..." — which classified the whole pass as RUN_EXECUTION and produced a
# two-task plan whose first task was "Determine the exact command to run". Refinement is a MODIFY of
# something that already exists, and saying so in the opening line is what gets a plan that requires
# edit_file AND screenshot.
REFINE_BRIEF = """Improve and polish the application that already exists in this repository.

This is refinement pass {n} of {total}. The project is already built. Do NOT start over and do NOT rewrite whole files from scratch - read what is there and improve it in place with edit_file.

Inspect before you change anything:
- start_dev_server, then screenshot, and actually look at the screenshot
- check the browser console and fix every error you find
- screenshot at 1440px, 834px and 390px; mobile must be a recomposed layout, not stacked desktop

Then fix what you actually saw, in this priority order:
1. broken, missing or non-functional interactions
2. visual hierarchy, typography, spacing and alignment
3. motion quality, and interaction states - hover, focus, active, loading, empty, error

Screenshot again afterwards and confirm your changes actually landed.

Judge the result against one question: would this pass as the work of a team that cares enormously about typography, motion and detail? Fix whatever makes the answer no. Keep the classical light design system coherent - do not drift toward generic SaaS styling.

Do not report success without having looked at a screenshot taken after your last change."""


def run_one(bench: dict, state: dict) -> str:
    """One lap of work on one benchmark."""
    name, repo, artifacts = bench["name"], bench["repo"], bench["artifacts"]
    prompt = (ROOT / bench["prompt"]).read_text(encoding="utf-8")
    st = state[name]

    ensure_repo(repo)

    if not st["built"]:
        entry(name, "Build phase", repository=repo, lap=st["laps"] + 1)
        job = start_job(repo, prompt)
        entry(name, "Job launched", job_id=job)
        outcome = watch(name, repo, job, prompt, artifacts, BUILD_SLICE_SECONDS, "build")
        ok, detail = artifacts_ok(repo, artifacts)
        if ok:
            st["built"] = True
            entry(name, "Build verified", artifacts=detail,
                  validation_performed="artifact substance check against the filesystem")
        else:
            st["laps"] += 1
            entry(name, "Build incomplete", observed_problem=detail,
                  result=f"outcome={outcome}; requeued for the next lap")
            return "building"

    while st["refined"] < REFINE_PASSES:
        n = st["refined"] + 1
        entry(name, f"Refinement pass {n}/{REFINE_PASSES}")
        brief = REFINE_BRIEF.format(n=n, total=REFINE_PASSES)
        job = start_job(repo, brief)
        outcome = watch(name, repo, job, brief, artifacts, REFINE_SLICE_SECONDS, f"refine{n}")
        ok, detail = artifacts_ok(repo, artifacts)
        if not ok:
            # A refinement pass that destroyed the artifact is worse than one that did nothing.
            entry(name, "Refinement damaged the artifact", observed_problem=detail,
                  result="build phase reopened")
            st["built"] = False
            st["laps"] += 1
            return "building"
        st["refined"] = n
        entry(name, f"Refinement pass {n} done", result=f"outcome={outcome}", artifacts=detail)
        if outcome == "deferred":
            return "refining"

    st["complete"] = True
    ok, detail = artifacts_ok(repo, artifacts)
    entry(name, "COMPLETE", artifacts=detail, refinement_passes=st["refined"],
          laps=st["laps"] + 1)
    return "complete"


def main() -> None:
    if not LOG_PATH.exists():
        LOG_PATH.write_text(
            f"# Codexa Overnight Autonomous Benchmark\n\nStarted {now()}.\n", encoding="utf-8")
    log(f"\n\n---\n\n# Session {now()} - VELUM, AURELIA, HELIX; sequential; never abandoned\n")

    if not wait_for_backend():
        log(f"`{now()}` backend unreachable at {BASE}; nothing to run.")
        return

    state: dict = {}
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
    for b in BENCHMARKS:
        state.setdefault(b["name"], {"built": False, "refined": 0, "complete": False, "laps": 0})

    # Work already on disk from an earlier session counts — the run resumes rather than redoing it.
    for b in BENCHMARKS:
        ok, detail = artifacts_ok(b["repo"], b["artifacts"])
        if ok and not state[b["name"]]["built"]:
            state[b["name"]]["built"] = True
            log(f"- `{now()}` {b['name']} already has a verified artifact ({detail}); "
                "resuming at the refinement phase")

    deadline = time.time() + TOTAL_HOURS * 3600
    lap = 0
    while time.time() < deadline:
        lap += 1
        pending = [b for b in BENCHMARKS if not state[b["name"]]["complete"]]
        if not pending:
            break
        log(f"\n`{now()}` - lap {lap}: {', '.join(b['name'] for b in pending)} outstanding\n")
        for bench in pending:
            if time.time() >= deadline:
                break
            try:
                run_one(bench, state)
            except Exception as exc:  # noqa: BLE001 - one failure must never end the night
                state[bench["name"]]["laps"] += 1
                entry(bench["name"], "Driver error",
                      observed_problem=f"{type(exc).__name__}: {exc}",
                      result="requeued for the next lap; not abandoned")
            STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

    quiesce()
    log("\n\n---\n\n## Run summary\n")
    for b in BENCHMARKS:
        st = state[b["name"]]
        ok, detail = artifacts_ok(b["repo"], b["artifacts"])
        log(f"- **{b['name']}** - {'COMPLETE' if st['complete'] else 'INCOMPLETE'} · "
            f"built={st['built']} · refinement passes={st['refined']}/{REFINE_PASSES} · "
            f"laps={st['laps'] + 1} · artifacts: {detail}")
    log(f"\nFinished {now()}.\n")


if __name__ == "__main__":
    main()
