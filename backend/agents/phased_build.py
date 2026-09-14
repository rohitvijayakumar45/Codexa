"""Phased build orchestration: decomposes a large, multi-hour-scope spec into an ordered chain of
smaller, independently-completable jobs, each starting with a FRESH conversation, instead of one
continuously-growing history.

Real overnight evidence motivated this: two full-stack build attempts (each from a single
monolithic spec) pushed past 100-300+ tool-calling rounds in one continuous job. Round-budget and
stall-recovery fixes kept them alive that whole time, but round count alone was never the actual
problem — a single job's conversation history growing that large correlates with real degradation
(a compaction placeholder written back as literal file content in one run; repeated identical
stall-nudge messages piling up and coinciding with the connection going completely and permanently
silent in another). No amount of retry-bounding fixes that; the fix is to not let any ONE job's
history grow that unbounded in the first place.

Splitting a big spec into phases keeps every individual job's history small (each starts fresh) and
its scope achievable in roughly 10-20 rounds, with each phase inspecting the REAL repo state left by
the previous phase's actual file writes instead of carrying forward a bloated conversation.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from backend.agents.jobs import JobManager
from backend.agents.llm import LLMClient
from backend.agents.task import build_task_prompt, generate_contract

logger = logging.getLogger(__name__)

PHASED_BUILDS_DIR = Path(__file__).parent.parent / "data" / "phased_builds"

# Hard ceiling on how many phases one decomposition can produce — protects against a decomposition
# call itself misbehaving (e.g. a model that lists 40 tiny phases instead of a handful of real
# ones), not a claim that 8 is always the right number for every spec.
_MAX_PHASES = 8
_POLL_INTERVAL_SECONDS = 5.0

_DECOMPOSE_SYSTEM_PROMPT = """You are a senior engineering lead splitting a large product spec into
an ordered sequence of independently-completable build phases for an autonomous coding agent.

Rules:
- Each phase must be completable by itself in roughly 10-20 tool calls (e.g. schema+backend, or
  API layer, or frontend shell+navigation, or the main feature pages, or polish+visual
  verification - that's a reasonable shape, adjust to what the actual spec needs).
- Each phase after the first must explicitly tell the agent to INSPECT the existing repository
  first (it was built by the previous phase) rather than assume nothing exists yet.
- 3 to 6 phases total. Fewer, larger phases beat many tiny ones.
- The LAST phase must include real end-to-end verification (run the app, take a screenshot,
  exercise the core flows) - never end on "written but unverified".
- Respond with ONLY a JSON array, no prose, no markdown fences. Each element:
  {"title": "short phase name", "prompt": "the exact instruction to give the agent for this phase"}
"""


@dataclass
class PhaseResult:
    title: str
    prompt: str
    job_id: str | None = None
    status: str = "pending"  # pending | running | done | error
    detail: str = ""


@dataclass
class PhasedBuild:
    id: str
    repository: str
    spec: str
    model: str | None = None
    phases: list[PhaseResult] = field(default_factory=list)
    current_phase: int = -1
    status: str = "planning"  # planning | running | done | error | cancelled
    cancelled: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_disk(self) -> dict:
        return asdict(self)

    @classmethod
    def from_disk(cls, data: dict) -> "PhasedBuild":
        data = dict(data)
        data["phases"] = [PhaseResult(**p) for p in data.get("phases", [])]
        return cls(**data)


def _parse_phases(raw: str) -> list[dict[str, str]]:
    """The phase list from a model reply: the JSON array itself, or the first one embedded in prose
    or a fenced block (models add both despite being told not to)."""
    text = (raw or "").strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        phases = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    return [
        {"title": str(p["title"]), "prompt": str(p["prompt"])}
        for p in phases if isinstance(p, dict) and p.get("title") and p.get("prompt")
    ][:_MAX_PHASES]


def decompose_into_phases(spec: str, llm: LLMClient, model: str | None = None) -> list[dict[str, str]]:
    """Split `spec` into an ordered phase list with one non-tool-calling call, trying the same fast
    planning models the task planner uses (backend/agents/plan_builder.py) before the job's own.

    It used to call only the default model. Observed: GLM via TokenRouter answered "Connection
    error" twice, so both phased builds that day ran as a single "Build (undecomposed)" phase — the
    exact monolithic job this feature exists to avoid. Never raises; only when every candidate fails
    does it fall back to one phase holding the whole spec."""
    from backend.agents.plan_builder import _planning_models  # local: plan_builder imports jobs too

    messages = [
        {"role": "system", "content": _DECOMPOSE_SYSTEM_PROMPT},
        {"role": "user", "content": spec},
    ]
    try:
        candidates = _planning_models(llm, model or llm.default_model)
    except Exception:  # noqa: BLE001 - a client without tiers just uses the given model
        candidates = [model or llm.default_model]
    for candidate in candidates:
        try:
            raw = llm.complete(messages, model=candidate, agent="phase_decompose", max_tokens=8000, timeout=120)
        except Exception as exc:  # noqa: BLE001 - one provider being down must not end the split
            logger.warning("phase decomposition with %s failed: %s", candidate, str(exc)[:160])
            continue
        phases = _parse_phases(raw if isinstance(raw, str) else "")
        if phases:
            logger.info("phased build: %d phases from %s", len(phases), candidate)
            return phases
        logger.warning("phase decomposition with %s returned no usable phase list", candidate)
    logger.warning("phase decomposition failed on every model, falling back to a single phase")
    return [{"title": "Build (undecomposed)", "prompt": spec}]


class PhasedBuildManager:
    def __init__(self, *, llm: LLMClient, job_manager: JobManager) -> None:
        self._llm = llm
        self._job_manager = job_manager
        self._lock = threading.Lock()
        self._builds: dict[str, PhasedBuild] = {}
        PHASED_BUILDS_DIR.mkdir(parents=True, exist_ok=True)

    # --- persistence ---------------------------------------------------------
    def _checkpoint(self, build: PhasedBuild) -> None:
        build.updated_at = time.time()
        path = PHASED_BUILDS_DIR / f"{build.id}.json"
        tmp = path.with_suffix(".tmp")
        payload = json.dumps(build.to_disk())
        # Retried: under OneDrive the rename fails transiently with "[WinError 5] Access is denied"
        # while the sync client holds the file (seen live on a phased build) — same fix as jobs.py.
        for attempt in range(5):
            try:
                tmp.write_text(payload, encoding="utf-8")
                os.replace(tmp, path)
                return
            except OSError as exc:  # noqa: BLE001 - checkpoint failure shouldn't crash the build
                if attempt == 4:
                    logger.warning("phased build checkpoint failed for %s: %s", build.id, exc)
                else:
                    time.sleep(0.05 * (attempt + 1))

    def resume_unfinished(self) -> list[str]:
        """Restart the orchestration of builds a server restart left mid-flight. Their jobs are
        checkpointed and resumable, but the thread that runs phases in order died with the old
        process — without this a build stayed "running" forever and never reached its next phase."""
        resumed: list[str] = []
        for path in PHASED_BUILDS_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("status") not in ("planning", "running") or data.get("cancelled"):
                continue
            build = self.get(str(data.get("id")))
            if build is None or not build.phases:
                continue
            with self._lock:
                self._builds[build.id] = build
            threading.Thread(target=self._run_phases, args=(build,), daemon=True).start()
            resumed.append(build.id)
        if resumed:
            logger.info("resumed %d unfinished phased build(s): %s", len(resumed), ", ".join(resumed))
        return resumed

    def cancel(self, build_id: str) -> bool:
        """Stop the build: cancel the running phase's job, and start no further phases."""
        build = self.get(build_id)
        if build is None:
            return False
        build.cancelled = True
        phase = build.phases[build.current_phase] if 0 <= build.current_phase < len(build.phases) else None
        if phase is not None and phase.job_id:
            self._job_manager.cancel(phase.job_id)
        if build.status in ("planning", "running"):
            build.status = "cancelled"
        self._checkpoint(build)
        return True

    def get(self, build_id: str) -> PhasedBuild | None:
        with self._lock:
            build = self._builds.get(build_id)
        if build is not None:
            return build
        path = PHASED_BUILDS_DIR / f"{build_id}.json"
        if not path.exists():
            return None
        try:
            return PhasedBuild.from_disk(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning("phased build checkpoint unreadable for %s: %s", build_id, exc)
            return None

    # --- lifecycle -------------------------------------------------------------
    def start(self, spec: str, repository: str, *, model: str | None = None) -> PhasedBuild:
        phase_dicts = decompose_into_phases(spec, self._llm, model)
        build = PhasedBuild(
            id=str(uuid.uuid4()), repository=repository, spec=spec, model=model,
            phases=[PhaseResult(title=p["title"], prompt=p["prompt"]) for p in phase_dicts],
        )
        with self._lock:
            self._builds[build.id] = build
        self._checkpoint(build)
        thread = threading.Thread(target=self._run_phases, args=(build,), daemon=True)
        thread.start()
        return build

    def _phase_message(self, build: PhasedBuild, index: int) -> str:
        phase = build.phases[index]
        if index == 0:
            return phase.prompt
        completed = "\n".join(
            f"- Phase {i + 1} ({p.title}): {p.detail or 'completed'}"
            for i, p in enumerate(build.phases[:index])
        )
        return (
            f"You're continuing an in-progress build in the '{build.repository}' repository. "
            f"Previous phases already completed real work here:\n{completed}\n\n"
            "Inspect the existing repository first (list_directory, read_file) before writing "
            f"anything — do not assume it's empty or redo earlier phases. Now do phase "
            f"{index + 1} of {len(build.phases)}: {phase.title}.\n\n{phase.prompt}"
        )

    def _run_phases(self, build: PhasedBuild) -> None:
        model = build.model if (build.model and build.model in self._llm.available) else self._llm.default_model
        for i, phase in enumerate(build.phases):
            if phase.status == "done":
                continue  # finished before a restart; resume_unfinished picks up after it
            if build.cancelled:
                build.status = "cancelled"
                self._checkpoint(build)
                return
            build.current_phase = i
            build.status = "running"
            phase.status = "running"
            self._checkpoint(build)

            message_text = self._phase_message(build, i)
            task_prompt = build_task_prompt(generate_contract(message_text))
            messages = [{"role": "user", "content": message_text}]
            if task_prompt:
                messages.insert(0, {"role": "system", "content": task_prompt})

            if phase.job_id:
                # Resumed after a restart: this phase's job already exists. Continue it (resume
                # restarts an interrupted job from its last checkpoint) rather than starting a
                # second job that would redo the same work on top of it.
                job_id = phase.job_id
                self._job_manager.resume(job_id)
            else:
                job = self._job_manager.create(repository=build.repository, model=model, messages=messages)
                job_id = job.id
                phase.job_id = job_id
                self._checkpoint(build)
                self._job_manager.start(job, last_user_text=message_text)

            current = None
            while True:
                time.sleep(_POLL_INTERVAL_SECONDS)
                current = self._job_manager.get(job_id)
                if current is None or current.status in ("done", "error"):
                    break

            if build.cancelled:
                phase.status = "cancelled"
                phase.detail = "stopped by the user"
                build.status = "cancelled"
                self._checkpoint(build)
                return
            if current is None:
                phase.status = "error"
                phase.detail = "job disappeared"
                build.status = "error"
                self._checkpoint(build)
                return
            if current.status != "done":
                # Never build the next phase on top of a phase that didn't actually finish - that's
                # exactly the "declares success without doing the work" failure this whole session
                # was about fixing, just one level up (phase-level instead of tool-call-level).
                phase.status = "error"
                phase.detail = "this phase's job errored out — stopping here rather than building on an incomplete foundation"
                build.status = "error"
                self._checkpoint(build)
                return
            phase.status = "done"
            phase.detail = f"{len(current.tools_called)} tool calls"
            self._checkpoint(build)

        build.status = "done"
        self._checkpoint(build)
