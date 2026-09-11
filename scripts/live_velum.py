"""Live VELUM benchmark driver against a fresh repository, with continuous telemetry.

A focused variant of scripts/overnight_benchmark.py for validating the September 8 fixes
(recovery-budget pre-seeding, intervention messages carrying validation detail) under real
autonomous execution. Differences from the overnight driver:

  - One benchmark (VELUM), one fresh repository (velum2), one session.
  - Telemetry is continuously recorded to LIVE_BENCHMARK_LOG.md: every round reports
    task status, tool counts, cut streaks, reasoning volume and artifact growth.
  - Tracks the exact metrics the incident log measures: time to first artifact,
    no-progress rounds, repeated tool calls, cuts, interventions, recoveries.
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
LOG_PATH = ROOT / "LIVE_BENCHMARK_LOG.md"
JOBS_DIR = ROOT / "backend" / "data" / "jobs"
REPO = "velum2"
PROMPT_PATH = ROOT / "prompts" / "overnight" / "1-velum.md"
ARTIFACTS = ["index.html"]

POLL_SECONDS = 20
STALE_AFTER_SECONDS = 15 * 60
BUILD_SLICE_SECONDS = 75 * 60
REFINE_SLICE_SECONDS = 40 * 60
REFINE_PASSES = 2
MAX_RECOVERIES = 6


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
            api("/repository/create", {"name": name, "description": "live VELUM benchmark (Sept 8 fixes)"})
            return
        except urllib.error.HTTPError as exc:
            if exc.code == 400:  # already exists
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


def quiesce(repo: str | None = None, timeout: int = 120) -> None:
    ids = running_jobs(repo)
    if not ids:
        return
    log(f"- `{now()}` quiescing {len(ids)} job(s)")
    for jid in ids:
        try:
            api(f"/chat/agent/job/{jid}/cancel", {}, timeout=30)
        except Exception:  # noqa: BLE001
            pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not running_jobs(repo):
            return
        time.sleep(4)
    for jid in running_jobs(repo):
        path = JOBS_DIR / f"{jid}.json"
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            d["status"], d["cancelled"] = "interrupted", True
            path.write_text(json.dumps(d), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass
    log(f"- `{now()}` WARNING: forced job(s) to interrupted after {timeout}s")


def artifacts_ok(repo: str, artifacts: list[str]) -> tuple[bool, str]:
    """Reality check using the platform's own substance rule."""
    from backend.agents.validators import _substance_problem

    root = ROOT / ".codexa" / "repos" / repo
    if not root.exists():
        return False, "repository does not exist yet"
    problems = []
    for rel in artifacts:
        problem = _substance_problem(root / rel)
        if problem:
            problems.append(f"{rel} {problem}")
    if problems:
        return False, "; ".join(problems)
    return True, ", ".join(f"{a} ({(root / a).stat().st_size:,} bytes)" for a in artifacts)


def start_job(repo: str, prompt: str) -> str:
    quiesce()  # no two benchmark jobs may overlap
    last: Exception | None = None
    for _ in range(10):
        try:
            return api("/chat/agent", {"repository": repo,
                                       "messages": [{"role": "user", "content": prompt}]})["job_id"]
        except Exception as exc:  # noqa: BLE001
            last = exc
            log(f"- `{now()}` could not start job ({type(exc).__name__}); waiting for backend")
            if not wait_for_backend(attempts=24):
                time.sleep(15)
    raise RuntimeError(f"backend never accepted a job: {last}")


class Telemetry:
    """Accumulates the metrics the incident log measures."""

    def __init__(self) -> None:
        self.started = time.time()
        self.first_artifact_at: float | None = None
        self.first_tool_at: float | None = None
        self.cuts = 0
        self.interventions = 0
        self.recoveries = 0
        self.tool_counts: dict[str, int] = {}
        self.no_progress_rounds = 0
        self.rounds = 0

    def observe(self, data: dict) -> None:
        tools = data.get("tools_called", [])
        if tools and self.first_tool_at is None:
            self.first_tool_at = time.time() - self.started
        for t in tools:
            self.tool_counts[t] = self.tool_counts.get(t, 0) + 1
        # counts are cumulative; diff against last seen below
        self.rounds = max(self.rounds, data.get("round", 0) + 1)
        self.cuts = max(self.cuts, data.get("consecutive_cuts", 0))

    def report(self, plan_tasks: list[dict]) -> str:
        done = sum(1 for t in plan_tasks if t.get("status") == "COMPLETED")
        failed = sum(1 for t in plan_tasks if t.get("status") == "FAILED")
        active = next((t["objective"][:48] for t in plan_tasks if t.get("status") == "IN_PROGRESS"), "-")
        top = sorted(self.tool_counts.items(), key=lambda kv: -kv[1])[:4]
        mins = (time.time() - self.started) / 60
        fa = f"{self.first_artifact_at / 60:.1f}m" if self.first_artifact_at else "—"
        ft = f"{self.first_tool_at / 60:.1f}m" if self.first_tool_at else "—"
        return (f"r{self.rounds} · tasks {done}✓/{failed}✗ · {active} · tools {top} · "
                f"cuts {self.cuts} · first-artifact {fa} · first-tool {ft} · {mins:.0f}m elapsed")


def watch(name: str, repo: str, job_id: str, prompt: str, artifacts: list[str],
          slice_seconds: int, phase: str, tel: Telemetry) -> str:
    """Drive one job to a conclusion within its slice. Returns complete/deferred/failed."""
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
            entry(name, f"Deferred ({phase})", observed_problem=f"slice of {slice_seconds // 60} min spent",
                  result="paused and requeued", artifacts=detail)
            return "deferred"

        data = checkpoint(job_id)
        if data is None:
            continue

        status, rnd = data.get("status"), data.get("round", 0)
        if rnd != last_round:
            last_round, last_change = rnd, time.time()
            plan = data.get("plan") or {}
            tasks = plan.get("tasks", [])
            tel.observe(data)
            log(f"- `{now()}` {name} [{phase}] {tel.report(tasks)}")
            # artifact watch
            root = ROOT / ".codexa" / "repos" / repo / "index.html"
            if root.exists() and tel.first_artifact_at is None and root.stat().st_size > 200:
                tel.first_artifact_at = time.time() - tel.started
                log(f"  ★ first artifact on disk: {root.stat().st_size:,} bytes "
                    f"({tel.first_artifact_at / 60:.1f} minutes after job start)")

        stalled = time.time() - last_change > STALE_AFTER_SECONDS
        if status == "running" and not stalled:
            continue

        ok, detail = artifacts_ok(repo, artifacts)
        if status == "done" and ok:
            return "complete"

        recoveries += 1
        tel.recoveries = recoveries
        if recoveries > MAX_RECOVERIES:
            entry(name, f"Recovery budget spent ({phase})", observed_problem=detail,
                  result="stopping this phase")
            quiesce(repo)
            return "failed"

        reason = data.get("error_reason")
        if status == "done" and not ok:
            entry(name, "Completion claim rejected", observed_problem=f"reported done but {detail}",
                  likely_cause="a narrative reply treated as delivery",
                  solution="re-issued against the same repository", result=f"recovery {recoveries}/{MAX_RECOVERIES}")
            job_id = start_job(repo, prompt)
        elif stalled and status == "running":
            entry(name, "Stalled", observed_problem=f"no checkpoint for {STALE_AFTER_SECONDS // 60} min",
                  likely_cause="provider stopped responding mid-round",
                  solution="cancelled and relaunched", result=f"recovery {recoveries}/{MAX_RECOVERIES}")
            quiesce(repo)
            job_id = start_job(repo, prompt)
        else:
            entry(name, "Error", observed_problem=f"error_reason={reason}",
                  solution="continue" if reason else "relaunch", result=f"recovery {recoveries}/{MAX_RECOVERIES}")
            resumed = False
            if reason:
                try:
                    api(f"/chat/agent/job/{job_id}/continue", {})
                    resumed = True
                except Exception as exc:  # noqa: BLE001
                    log(f"- continue failed ({exc}); relaunching")
            if not resumed:
                job_id = start_job(repo, prompt)
        last_change, last_round = time.time(), -1


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


def run_one(prompt: str, tel: Telemetry) -> None:
    ensure_repo(REPO)

    entry("VELUM2", "Build phase", repository=REPO)
    job = start_job(REPO, prompt)
    entry("VELUM2", "Job launched", job_id=job)
    outcome = watch("VELUM2", REPO, job, prompt, ARTIFACTS, BUILD_SLICE_SECONDS, "build", tel)
    ok, detail = artifacts_ok(REPO, ARTIFACTS)
    if ok:
        entry("VELUM2", "Build verified", artifacts=detail, outcome=outcome,
              validation_performed="artifact substance check against the filesystem")
    else:
        entry("VELUM2", "Build incomplete", observed_problem=detail, outcome=outcome)
        return

    for n in range(1, REFINE_PASSES + 1):
        entry("VELUM2", f"Refinement pass {n}/{REFINE_PASSES}")
        brief = REFINE_BRIEF.format(n=n, total=REFINE_PASSES)
        job = start_job(REPO, brief)
        outcome = watch("VELUM2", REPO, job, brief, ARTIFACTS, REFINE_SLICE_SECONDS, f"refine{n}", tel)
        ok, detail = artifacts_ok(REPO, ARTIFACTS)
        if not ok:
            entry("VELUM2", "Refinement damaged the artifact", observed_problem=detail,
                  result="stopping refinement")
            return
        entry("VELUM2", f"Refinement pass {n} done", outcome=outcome, artifacts=detail)

    ok, detail = artifacts_ok(REPO, ARTIFACTS)
    entry("VELUM2", "COMPLETE", artifacts=detail, refinement_passes=REFINE_PASSES)


def main() -> None:
    if not LOG_PATH.exists():
        LOG_PATH.write_text(
            f"# Live VELUM Benchmark — validation of Sept 8 fixes\n\nStarted {now()}.\n\n"
            "Fixes under test: recovery-task intervention pre-seeding; intervention messages\n"
            "carrying the last validation failure detail. Fresh repository: velum2.\n\n---\n\n",
            encoding="utf-8")
    log(f"\n# Session {now()} — VELUM on fresh repo `{REPO}`\n")

    if not wait_for_backend():
        log(f"`{now()}` backend unreachable at {BASE}; nothing to run.")
        return

    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    tel = Telemetry()
    try:
        run_one(prompt, tel)
    except Exception as exc:  # noqa: BLE001 - never leave the log without a verdict
        entry("VELUM2", "Driver error", observed_problem=f"{type(exc).__name__}: {exc}",
              result="not abandoned — rerun scripts/live_velum.py to resume")
    finally:
        quiesce()

    log("\n\n---\n\n## Session summary\n")
    ok, detail = artifacts_ok(REPO, ARTIFACTS)
    mins = (time.time() - tel.started) / 60
    log(f"- **Artifact:** {detail}")
    log(f"- **Time to first tool call:** {tel.first_tool_at / 60:.1f} min" if tel.first_tool_at
        else "- **Time to first tool call:** never")
    log(f"- **Time to first artifact:** {tel.first_artifact_at / 60:.1f} min" if tel.first_artifact_at
        else "- **Time to first artifact:** never")
    log(f"- **Round cuts:** {tel.cuts} · **recoveries:** {tel.recoveries} · **rounds:** {tel.rounds}")
    log(f"- **Top tools:** {sorted(tel.tool_counts.items(), key=lambda kv: -kv[1])[:6]}")
    log(f"- **Total elapsed:** {mins:.0f} min")
    log(f"\nFinished {now()}.\n")


if __name__ == "__main__":
    main()
