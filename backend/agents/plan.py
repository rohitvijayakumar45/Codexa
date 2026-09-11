"""The execution plan: a persistent, Codexa-owned state machine for a job's work.

Why this exists
---------------
Before this module, a job was one flat loop: hand the model the entire problem, let it decide when
it was finished, and hope. That put the single most important judgement — "is this done?" — in the
hands of the one participant with no way to check. Two failure modes followed directly from it.

The first is silent success: a model replies "Done." having written nothing, and the loop believes
it. The task contract (backend/agents/task.py) closed part of that by requiring specific tools, but
it only checks the whole job at the very end, so it can only say "you never called write_file" long
after the run is over.

The second is the expensive one, and the reason this module is a state machine rather than another
validator: a model asked to solve an entire large problem in one context will reason about the
entire large problem. A real observed build sat in a single round for 48 minutes emitting 39,655
reasoning tokens — designing three complete, different products and discarding two — without writing
a byte. Nothing noticed, because every guard in the loop acted BETWEEN rounds and that round never
ended. Bounding reasoning per round (backend/agents/jobs.py) made that recoverable, but recovery
alone doesn't stop it recurring: the model kept re-deriving the whole plan because the whole plan is
what it was being asked about, every single round.

The fix is structural. Give the job an explicit, ordered plan; make exactly one task active at a
time; tell the model about that one task rather than the whole problem; and let only Codexa decide
when a task is finished — from artifacts on disk and command exit codes, never from the model's own
claim. A model can still think deeply. It can no longer think about everything at once, and it can
no longer talk its way to "complete".

Ownership boundary
------------------
The model may PROPOSE a plan (see backend/agents/plan_builder.py) and does the actual work. Codexa
owns: which task is active, what remains, whether progress occurred, whether completion is valid,
and what happens next. Nothing in this module trusts model output; it takes plain data and enforces
transitions. It deliberately has no LLM, graph, or filesystem dependency — validation against
reality lives in backend/agents/validators.py, so this stays pure state and stays trivially testable.
"""

from __future__ import annotations

import os

import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


#: A task whose status is one of these will never be worked on again by this plan.
TERMINAL_STATUSES = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED})


class ValidationState(str, Enum):
    UNVALIDATED = "UNVALIDATED"
    PASSED = "PASSED"
    FAILED = "FAILED"


# How many times a single task may be attempted before the plan gives up on it. An "attempt" is
# counted when validation rejects a completion claim, or when the task is abandoned for lack of
# progress — not per round, since a legitimately large task (write a 1,200-line file, then refine it)
# takes many rounds without ever failing. Three is deliberately small: a task that has failed
# validation three times is not going to pass on the fourth by repetition, and the useful recovery
# is a different approach (a repair task) rather than the same one again.
MAX_ATTEMPTS_PER_TASK = 3

# A plan may be revised — the agent discovers a task needs a subtask, or that one is unnecessary —
# but only this many times. Unbounded revision is its own hang: rewriting the plan is indistinguish-
# able from progress to any round-counting guard, and it is exactly what a model that would rather
# design than build will do when told "you may update the plan". After this many revisions the plan
# is frozen and the only legal move is to execute what is already there.
MAX_PLAN_REVISIONS = 5


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:40].rstrip("-") or fallback)


@dataclass
class Task:
    """One unit of work Codexa tracks independently.

    Granularity target: concrete enough that finishing it is observable from outside the model
    (a file exists, a command exited 0, a screenshot was taken), but not so fine that every tool
    call is its own task — a plan of thirty trivial steps reintroduces the planning overhead this
    is meant to remove.
    """

    id: str
    objective: str
    status: TaskStatus = TaskStatus.PENDING
    #: Task ids that must be COMPLETED before this one may start.
    depends_on: list[str] = field(default_factory=list)
    #: Tools this task cannot plausibly be finished without. Drives both the prompt the model sees
    #: and, when a task stops making progress, exactly which tool call gets forced.
    required_tools: list[str] = field(default_factory=list)
    #: Repository-relative paths this task is expected to leave on disk. The strongest completion
    #: signal available, because it is checked against the filesystem rather than the transcript.
    expected_artifacts: list[str] = field(default_factory=list)
    #: Human-readable, shown to the model. Not enforced — `validators` is what is enforced.
    completion_criteria: list[str] = field(default_factory=list)
    #: Names resolved by backend/agents/validators.py. Empty means "nothing mechanical to check",
    #: which is legitimate for genuinely non-artifact tasks (inspect the repo, decide a direction).
    validators: list[str] = field(default_factory=list)
    validation_state: ValidationState = ValidationState.UNVALIDATED
    validation_detail: str = ""
    #: How many times a claimed completion was REJECTED by validation. Bounded by
    #: MAX_ATTEMPTS_PER_TASK.
    attempts: int = 0
    #: How many times the controller had to force this task forward because it stopped advancing.
    #: Counted separately from `attempts` on purpose: they are different failures with different
    #: right responses. A rejected completion means the model believes it is finished and is wrong,
    #: so the useful move is to say what is missing. An intervention means the model is not
    #: finishing at all, so the useful move is to force the call. Folding them into one counter
    #: (which an earlier version of this did) meant three slow-but-legitimate rounds could exhaust
    #: the validation budget of a task that had never once claimed to be done.
    interventions: int = 0
    #: True for a task inserted to repair a failed one. Recovery does not recurse — see
    #: ExecutionController.recover — so this is what stops "Recover: Recover: Recover: ..." chains
    #: from consuming the plan's whole revision budget on a task that is simply not achievable.
    is_recovery: bool = False
    rounds_spent: int = 0
    #: Consecutive rounds inside this task that produced no repository change and no meaningful tool
    #: result. Reset by real progress; drives the unproductive-task intervention in jobs.py.
    rounds_without_progress: int = 0
    #: Reasoning characters spent on this task across all its rounds. Distinct from the per-round
    #: budget: a task can stay under the round cap every round and still spend an hour thinking.
    reasoning_chars: int = 0
    #: Short, factual notes about what actually happened ("wrote index.html (41,203 bytes)").
    #: Carried into the model's context in place of the reasoning that produced them — the point is
    #: to preserve decisions and outcomes without replaying deliberation.
    progress_notes: list[str] = field(default_factory=list)
    failure_reason: str = ""
    #: What Codexa believes should happen next inside this task. Set by the controller when it
    #: intervenes, so the recovery instruction survives a checkpoint/restart.
    next_action: str = ""
    started_at: float | None = None
    completed_at: float | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def note(self, text: str, *, limit: int = 12) -> None:
        """Record a progress note, keeping only the most recent `limit`. Bounded because these are
        re-sent to the model every round of this task; an unbounded list would recreate, in miniature,
        the transcript growth this whole design exists to avoid."""
        text = text.strip()
        if not text:
            return
        self.progress_notes.append(text)
        if len(self.progress_notes) > limit:
            del self.progress_notes[: len(self.progress_notes) - limit]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["validation_state"] = self.validation_state.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        data = dict(data)
        data["status"] = TaskStatus(data.get("status", TaskStatus.PENDING.value))
        data["validation_state"] = ValidationState(
            data.get("validation_state", ValidationState.UNVALIDATED.value)
        )
        known = {f for f in cls.__dataclass_fields__}  # tolerate checkpoints from an older shape
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class ExecutionPlan:
    """The authoritative record of what this job is doing and how far it has got.

    Persisted with the job checkpoint, so a restart, a model rotation, or a user clicking Continue
    all resume at the same task with the same history — the execution position is Codexa's, not
    something reconstructed from whatever the model happens to remember.
    """

    objective: str = ""
    tasks: list[Task] = field(default_factory=list)
    revisions: int = 0
    #: True once the model has committed to a direction. After this, plan edits are additive
    #: (insert a subtask, drop one that became unnecessary); wholesale replacement is refused.
    committed: bool = False
    created_at: float = field(default_factory=time.time)
    #: Where this plan's tasks came from: "proposed" (the model decomposed the actual request),
    #: "template" (the deterministic fallback in plan_builder), or "" for a plan built before this
    #: was recorded. Load-bearing, not decorative: the proposal path is allowed to fail silently
    #: into the template on any error, and it does — a timeout on the planning call turned a
    #: specific request ("filtering by tide zone that reorganises the list, a count that updates")
    #: into the generic nine-task build plan, and nothing anywhere said so. A feature that degrades
    #: invisibly is indistinguishable from one that was never built.
    source: str = ""
    #: Why the proposal path was not used, when it was not. Free text, shown in the UI beside the
    #: plan so the fallback is visible at the moment it matters rather than in a log nobody reads.
    source_detail: str = ""

    # --- lookup ---------------------------------------------------------------
    def get(self, task_id: str) -> Task | None:
        return next((t for t in self.tasks if t.id == task_id), None)

    def index_of(self, task_id: str) -> int:
        return next((i for i, t in enumerate(self.tasks) if t.id == task_id), -1)

    def is_ready(self, task: Task) -> bool:
        """A task may start once every dependency has REACHED A TERMINAL STATE — completed or failed.

        Not "completed". In the plans this system actually produces, `depends_on` expresses ORDER,
        not impossibility: "implement the core experience" follows "create the primary artifact"
        because doing them the other way round is silly, not because the second is unattemptable if
        the first went wrong. Requiring completion made every failure fatal to the entire remainder
        of the plan — one task failing validation three times deadlocked all seven tasks behind it
        and killed jobs that were still perfectly capable of producing the artifact (the later task
        would have written the file itself, which is precisely what the earlier one failed to do).

        A dependency that does not exist at all is different, and still blocks: that is a malformed
        plan, and proceeding on it would mean running a task whose prerequisites are unknowable.
        """
        for dep_id in task.depends_on:
            dep = self.get(dep_id)
            if dep is None or not dep.is_terminal:
                return False
        return True

    def current(self) -> Task | None:
        """The one task the model should be working on right now.

        Resolution order is deliberate: an already-started task wins, so a round that arrives after
        a restart continues rather than jumping ahead; otherwise the earliest ready PENDING task, so
        plan order is respected. None means there is nothing left that can be worked on — either the
        plan is finished, or everything remaining is blocked behind a failure.
        """
        started = next((t for t in self.tasks if t.status is TaskStatus.IN_PROGRESS), None)
        if started is not None:
            return started
        return next(
            (t for t in self.tasks if t.status is TaskStatus.PENDING and self.is_ready(t)),
            None,
        )

    def remaining(self) -> list[Task]:
        return [t for t in self.tasks if not t.is_terminal]

    def completed(self) -> list[Task]:
        return [t for t in self.tasks if t.status is TaskStatus.COMPLETED]

    def is_complete(self) -> bool:
        """Every task reached a terminal state AND at least one actually succeeded.

        The second half matters: a plan whose every task FAILED has also "finished", and reporting
        that as job completion is precisely the silent-success failure in a new costume.
        """
        if not self.tasks:
            return False
        if any(not t.is_terminal for t in self.tasks):
            return False
        return any(t.status is TaskStatus.COMPLETED for t in self.tasks)

    def is_stuck(self) -> bool:
        """Work remains but none of it can be started — every non-terminal task is BLOCKED, or is
        waiting on a dependency that failed. Distinct from is_complete(): the job must surface this
        rather than either looping forever looking for a current task or reporting success."""
        return bool(self.remaining()) and self.current() is None

    # --- transitions (Codexa-owned; nothing here takes the model's word) ------
    def begin(self, task: Task) -> None:
        if task.status is TaskStatus.IN_PROGRESS:
            return
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = task.started_at or time.time()
        task.validation_state = ValidationState.UNVALIDATED
        task.validation_detail = ""

    def complete(self, task: Task, *, detail: str = "") -> None:
        """Mark a task done. Callers must have validated first — `record_validation` is the gate,
        and jobs.py routes every completion claim through it. Kept as a separate call rather than
        folded into validation so the controller can also complete a task that had nothing
        mechanical to check (an inspection step), which is a different judgement entirely."""
        task.status = TaskStatus.COMPLETED
        task.completed_at = time.time()
        task.validation_state = ValidationState.PASSED
        if detail:
            task.validation_detail = detail
        task.next_action = ""
        task.rounds_without_progress = 0

    def fail(self, task: Task, reason: str) -> None:
        """Give up on one task. Deliberately does NOT cascade to its dependents.

        Cascading was the first implementation and it was wrong. Because a generated build plan is a
        linear chain, blocking dependents on failure meant any single failed task took the whole
        remaining plan down with it — the job then reported "blocked with work outstanding" while
        every one of those outstanding tasks was independently attemptable. A failure should cost
        one task, stay visible in the plan as FAILED, and let the run continue; the job-level
        contract check is what decides whether what remains added up to the actual request.
        """
        task.status = TaskStatus.FAILED
        task.completed_at = time.time()
        task.failure_reason = reason

    def block(self, task: Task, reason: str) -> None:
        task.status = TaskStatus.BLOCKED
        task.failure_reason = reason

    def unblock(self, task: Task) -> None:
        if task.status is TaskStatus.BLOCKED:
            task.status = TaskStatus.PENDING
            task.failure_reason = ""

    def record_validation(self, task: Task, passed: bool, detail: str) -> bool:
        """The single gate between "the model says it finished" and COMPLETED.

        On failure the task stays active and burns an attempt; once attempts are exhausted the task
        FAILS rather than being retried forever, because the same approach failing a fourth time is
        not new information. Returns True if the task is now complete.
        """
        task.validation_detail = detail
        if passed:
            task.validation_state = ValidationState.PASSED
            self.complete(task, detail=detail)
            return True
        task.validation_state = ValidationState.FAILED
        task.attempts += 1
        if task.attempts >= MAX_ATTEMPTS_PER_TASK:
            self.fail(task, f"failed validation {task.attempts} times: {detail}")
        return False

    # --- revision (bounded on purpose) ----------------------------------------
    def can_revise(self) -> bool:
        return self.revisions < MAX_PLAN_REVISIONS

    def insert_after(self, task_id: str, new_task: Task) -> bool:
        """Add a discovered subtask or a repair step directly after an existing task. This is the
        only supported way to grow a plan mid-run: additive, positioned, and counted. Refused once
        the revision budget is spent, which is what stops replanning from becoming the work."""
        if not self.can_revise() or self.get(new_task.id) is not None:
            return False
        idx = self.index_of(task_id)
        if idx < 0:
            return False
        self.tasks.insert(idx + 1, new_task)
        self.revisions += 1
        return True

    def drop(self, task_id: str, reason: str) -> bool:
        """Retire a task that turned out to be unnecessary. Recorded as COMPLETED-with-reason rather
        than deleted, so the history of what the plan decided stays auditable and any dependents
        remain satisfiable."""
        task = self.get(task_id)
        if task is None or task.is_terminal or not self.can_revise():
            return False
        task.status = TaskStatus.COMPLETED
        task.completed_at = time.time()
        task.validation_state = ValidationState.PASSED
        task.validation_detail = f"not needed: {reason}"
        self.revisions += 1
        return True

    # --- rendering ------------------------------------------------------------
    def render_progress(self) -> str:
        """Compact plan view for the model's context — the "what has been done / what remains" half
        of task-driven context. Symbols match what the UI shows so a screenshot and a transcript
        describe the same thing."""
        lines = []
        current = self.current()
        for t in self.tasks:
            if t.status is TaskStatus.COMPLETED:
                mark = "[x]"
            elif t is current or t.status is TaskStatus.IN_PROGRESS:
                mark = "[>]"
            elif t.status is TaskStatus.FAILED:
                mark = "[!]"
            elif t.status is TaskStatus.BLOCKED:
                mark = "[~]"
            else:
                mark = "[ ]"
            lines.append(f"{mark} {t.objective}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "objective": self.objective,
            "tasks": [t.to_dict() for t in self.tasks],
            "revisions": self.revisions,
            "committed": self.committed,
            "created_at": self.created_at,
            "source": self.source,
            "source_detail": self.source_detail,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "ExecutionPlan | None":
        if not data:
            return None
        return cls(
            objective=data.get("objective", ""),
            tasks=[Task.from_dict(t) for t in data.get("tasks", [])],
            revisions=int(data.get("revisions", 0)),
            committed=bool(data.get("committed", False)),
            created_at=float(data.get("created_at", time.time())),
            source=str(data.get("source", "")),
            source_detail=str(data.get("source_detail", "")),
        )


def make_task(
    objective: str,
    *,
    index: int,
    depends_on: Iterable[str] = (),
    required_tools: Iterable[str] = (),
    expected_artifacts: Iterable[str] = (),
    completion_criteria: Iterable[str] = (),
    validators: Iterable[str] = (),
    task_id: str | None = None,
) -> Task:
    """Build a task with a stable, readable id (`t1-write-index-html`).

    Readable rather than a uuid because these ids appear in dependency lists, in checkpoints, in
    log lines and in the model's own context; debugging a plan whose tasks are named by hash is
    needlessly hard, and the index prefix keeps them unique even when two objectives slugify alike.
    """
    return Task(
        id=task_id or f"t{index}-{_slug(objective, f'task{index}')}",
        objective=objective.strip(),
        depends_on=list(depends_on),
        required_tools=list(required_tools),
        expected_artifacts=list(expected_artifacts),
        completion_criteria=list(completion_criteria),
        validators=list(validators),
    )


# A/B switch for the one hypothesis that is cheap enough to test rather than argue about:
# whether naming the remaining tasks at all is what invites the model to start solving them. The
# block is already reduced to bare objectives with an explicit instruction not to work on them, so
# the expected effect is small — but "expected small" and "measured zero" are different findings,
# and round_telemetry.py now records enough per round (reasoning volume, time to first tool, tool
# count) to tell them apart on identical prompts. Set CODEXA_HIDE_LATER=1 for arm B.
#
# Read per call, not at import: a benchmark harness flips this between runs in the same process.
def _hide_later() -> bool:
    return os.getenv("CODEXA_HIDE_LATER", "").strip().lower() in ("1", "true", "yes", "on")


def task_context_block(
    plan: ExecutionPlan, task: Task, *, max_notes: int = 6, commitment: dict | None = None
) -> str:
    """The message the model receives each round in place of "solve the whole problem".

    Structure is fixed on purpose — overall objective, what is settled, this one task, what it must
    produce, what already happened, the single outstanding action. Everything here is state and
    outcome; none of it is prior deliberation. Replaying reasoning to preserve continuity is what
    made a model re-enter the deliberation it was cut out of, so continuity is carried by facts
    instead: files written, commands run, what validation said.

    Future tasks are named and nothing more. An earlier version rendered the entire plan in full
    every round, and a model given the whole plan solves the whole plan: on one run it called
    commit_direction, acknowledged in as many words that writing the page "is task 3", and then
    designed task 3's CSS architecture, JavaScript architecture, fourteen archive records, timeline
    behaviour, FLIP implementation and mobile layout — before task 1 had returned. Listing later
    work in detail is an invitation to do it early; the plan already holds those tasks and will
    present each one when it becomes active.

    `commitment` is the job's commit_direction record — rendered here, every round, is what makes a
    chosen palette actually durable. It used to appear only in the one-shot post-cut directive
    (backend/agents/jobs.py's _execution_directive), which is invisible by the time it matters: a
    real job called get_design_guidance at round 1, wrote the file at round 6, and by then the
    guidance — including an explicit ban on the exact palette it produced — had already been
    compacted out of context. A decision recorded once and never repeated is not different, to a
    model five rounds later, from a decision never made.
    """
    completed = [t for t in plan.tasks if t.status is TaskStatus.COMPLETED]
    later = [t for t in plan.tasks if not t.is_terminal and t is not task]

    lines = [
        "[EXECUTION STATE — this is managed by Codexa, not by you.]",
        "",
    ]
    if plan.objective:
        lines.append(f"OVERALL OBJECTIVE: {plan.objective}")
    lines.append(f"PROGRESS: task {plan.index_of(task.id) + 1} of {len(plan.tasks)} "
                 f"({len(completed)} completed)")

    design = (commitment or {}).get("design") or {}
    if any((design.get("palette"), design.get("typography"), design.get("motion"),
            design.get("rejected"))):
        lines += ["", "COMMITTED DESIGN — decided once, applies to every task, do not redecide:"]
        if design.get("palette"):
            lines.append("  Palette: " + ", ".join(f"{k}={v}" for k, v in design["palette"].items()))
        if design.get("typography"):
            lines.append(
                "  Typography: " + ", ".join(f"{k}={v}" for k, v in design["typography"].items())
            )
        if design.get("motion", {}).get("easing"):
            lines.append(f"  Motion: {design['motion']['easing']}")
        if design.get("rejected"):
            lines.append("  Rejected — do not drift back to these: " + "; ".join(design["rejected"]))

    if completed:
        lines += ["", "ALREADY DONE (do not redo):"]
        lines += [f"  [x] {t.objective}" for t in completed[-4:]]

    lines += ["", "=" * 60, f"CURRENT TASK: {task.objective}", "=" * 60]
    if task.required_tools:
        lines.append(f"REQUIRED TOOLS FOR THIS TASK: {', '.join(task.required_tools)}")
    if task.expected_artifacts:
        lines.append(f"MUST EXIST WHEN DONE: {', '.join(task.expected_artifacts)}")
    if task.completion_criteria:
        lines.append("DONE MEANS:")
        lines.extend(f"  - {c}" for c in task.completion_criteria)
    if task.progress_notes:
        lines += ["", "ALREADY DONE IN THIS TASK:"]
        lines.extend(f"  - {n}" for n in task.progress_notes[-max_notes:])
    if task.validation_state is ValidationState.FAILED and task.validation_detail:
        lines += ["", f"LAST CHECK FAILED: {task.validation_detail}"]
    if task.next_action:
        lines += ["", f"OUTSTANDING ACTION: {task.next_action}"]

    if later and not _hide_later():
        lines += [
            "",
            f"LATER — {len(later)} task(s), listed only so you know they are covered:",
            "  " + "; ".join(t.objective for t in later[:6])
            + ("; ..." if len(later) > 6 else ""),
            "Do NOT design, plan or write any part of these now. Each becomes the current task in "
            "its turn, with its own full context. Work spent on them here is discarded.",
        ]

    lines += [
        "",
        "Work ONLY on the current task. Codexa advances the plan for you once this one is verified "
        "on disk, and ends the round as soon as it is — so finishing it is how you move on. Do not "
        "restate the plan. Act with tools; Codexa decides when this task is complete by checking "
        "reality, not by your description of it.",
        "",
        "ECONOMY: do not re-run the dev server, screenshots, tests or type-checks after every "
        "small edit. Make a batch of related changes, then verify once at the end of them. If this "
        "task does not list a verification tool above, it does not need one — running it anyway "
        "costs minutes and proves nothing new.",
    ]
    return "\n".join(lines)


def summarize_for_event(plan: ExecutionPlan) -> dict[str, Any]:
    """Shape the UI consumes (graph-viz reads this off the SSE stream). Deliberately excludes
    reasoning of any kind: the interface shows execution state and progress, never chain of thought."""
    current = plan.current()
    return {
        "objective": plan.objective,
        "current_task_id": current.id if current else None,
        "tasks": [
            {
                "id": t.id,
                "objective": t.objective,
                "status": t.status.value,
                "attempts": t.attempts,
                "validation_state": t.validation_state.value,
                "validation_detail": t.validation_detail,
                "expected_artifacts": t.expected_artifacts,
                "last_progress": t.progress_notes[-1] if t.progress_notes else "",
            }
            for t in plan.tasks
        ],
        "completed": len(plan.completed()),
        "total": len(plan.tasks),
        # So "are these tasks actually built from my request?" is answerable by looking, instead of
        # by comparing objectives against the template by eye.
        "source": plan.source,
        "source_detail": plan.source_detail,
    }
