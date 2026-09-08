"""The execution controller: policy that connects the plan (backend/agents/plan.py) to the agent loop.

`plan.py` is a pure state machine — it knows what a task is and which transitions are legal, but it
never looks at a disk, a model, or a clock budget. `jobs.py` is the loop — it streams rounds and
executes tool calls. This module is the layer between them, and it is where every judgement that
needs BOTH lives:

  - which task the model should be told about, and how that context replaces the old
    "here is the entire problem, go" framing
  - whether the last round actually moved anything, as opposed to merely generating
  - what to do when it didn't: nudge, force a specific tool, abandon the task, or repair it
  - whether a claimed completion survives contact with the filesystem

Deliberately separate from jobs.py rather than inlined into it. `_loop` was already the single most
consequential function in the codebase and every one of the reliability mechanisms in it — the round
budget, stall recovery, the reasoning budget, compaction, auto-continue — was added by growing it.
Putting task policy there too would make all of it untestable together. Here it can be exercised
against a fake job with no provider, no threads, and no network.

The ownership rule this module enforces, stated once: **the model never decides that work is
finished.** It can say so; that only starts a check. What completes a task is a file on disk, an
exit code, a screenshot that was actually taken. Everything below follows from that.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Callable, Deque, Sequence

from backend.agents.plan import (
    ExecutionPlan,
    Task,
    TaskStatus,
    ValidationState,
    make_task,
    summarize_for_event,
    task_context_block,
)
from backend.agents.progress import ProgressSignal, RepoSnapshot, compare, is_thrashing, snapshot
from backend.agents.validators import infer_validators, validate_task
from backend.files.api import repo_root

logger = logging.getLogger(__name__)

# The first line of plan.task_context_block's output. Used to find and remove a previously injected
# execution-state message so exactly one is ever live in the transcript: these blocks are replaced
# on every task change, and a run of eight stale ones describing tasks that finished long ago is
# both pure token cost and actively misleading — a model reading its own history would see four
# different "CURRENT TASK" declarations and no way to tell which is current.
TASK_CONTEXT_MARK = "[EXECUTION STATE"

# Consecutive rounds inside one task that changed nothing on disk and ran nothing informative before
# the controller stops asking nicely. Three rather than one because legitimate work looks like this
# occasionally — reading three files in a row to decide where an edit goes produces no repository
# change and is exactly right. It is the *streak* that is pathological, not any single round.
MAX_ROUNDS_WITHOUT_PROGRESS = 3

# A single task's ceiling. The global round budget (jobs.py `_MAX_ROUNDS`, extended by auto-continue)
# bounds the whole job, but a job-level bound cannot tell "task 4 of 8 is taking a while" from
# "task 4 has eaten the entire run". Twelve rounds is generous for one task — writing a large file
# and refining it three times fits comfortably — and a task that has not finished in twelve is not
# going to finish in thirty by repetition.
MAX_ROUNDS_PER_TASK = 12

# Reasoning characters one task may spend across ALL its rounds. jobs.py already caps a single round
# at 40,000, which converts an endless round into a recoverable event; this is the complement, and it
# exists because that per-round cap has an obvious hole: a model can sit just under it every round
# forever. Measured on a real run — after a round was cut at 40,047 characters, the very next round
# spent another 23,692 characters and still called nothing. Three rounds' worth is the ceiling for
# one task's entire deliberation.
MAX_REASONING_CHARS_PER_TASK = 120_000

# How many times the controller forces one task forward before abandoning it. Separate budget from
# plan.MAX_ATTEMPTS_PER_TASK (which counts rejected completion claims) — see Task.interventions for
# why they must not share a counter. Small for the same reason: a task that has ignored three forced
# tool calls is not going to comply on the fourth, and the useful move is a different task.
MAX_INTERVENTIONS_PER_TASK = 3

# Validators that cost real wall-clock: a browser launch, a type-check subprocess. Safe to run when
# a completion is being claimed; far too expensive to poll after every tool round.
_EXPENSIVE_VALIDATORS = frozenset({"renders_cleanly", "no_build_errors"})

# Read-only tools whose answer does not change by asking again. Forcing one of these a second time
# inside the same task cannot advance it — the repository listing that came back empty comes back
# empty. Excluded from re-forcing after they have run once in a task.
_NON_ADVANCING_WHEN_REPEATED = frozenset({
    "list_directory", "tree", "git_status", "get_project_metadata", "detect_conventions",
    "get_design_guidance", "search_code",
})


class InterventionReason(str):
    """Why the controller is stepping in. Carried into events and logs so an unproductive stretch is
    diagnosable after the fact rather than appearing as an unexplained tool-choice change."""

    NO_PROGRESS = "no_progress"
    THRASHING = "thrashing"
    REASONING_EXHAUSTED = "reasoning_exhausted"
    TOO_MANY_ROUNDS = "too_many_rounds"


class ExecutionController:
    """Owns plan advancement for one job. Constructed fresh per `_loop` entry; all durable state
    lives on the job (and therefore in its checkpoint), never in this object — a controller rebuilt
    after a restart or a model rotation resumes at exactly the same task with the same history."""

    def __init__(
        self,
        job: Any,
        plan: ExecutionPlan,
        *,
        repository: str,
        emit: Callable[[dict], None],
    ) -> None:
        self.job = job
        self.plan = plan
        self.repository = repository
        self._emit = emit
        # Not persisted on purpose: thrashing is a statement about the last few rounds, and a job
        # resuming after a restart genuinely has no recent rounds to judge. Starting that window
        # empty means a resumed job gets a clean slate rather than inheriting a suspicion it can no
        # longer verify.
        self._recent: Deque[ProgressSignal] = deque(maxlen=6)

    # --- persistence ---------------------------------------------------------
    def sync(self, *, emit_event: bool = True) -> None:
        """Write the plan back onto the job (so the next checkpoint carries it) and optionally push
        a snapshot to the UI. Called after every transition rather than once per round — the plan is
        the job's execution position, and a checkpoint that disagrees with it would resume the wrong
        task."""
        self.job.plan = self.plan.to_dict()
        if emit_event:
            self._emit({"plan": summarize_for_event(self.plan)})

    # --- task selection ------------------------------------------------------
    def current_task(self) -> Task | None:
        return self.plan.current()

    def begin_task(self, task: Task) -> bool:
        """Move a task to IN_PROGRESS and record where in the job's tool/exit-code history it began.

        Those offsets are the whole reason a per-task validator can exist: `job.tools_called` is
        cumulative for the job, so asking "did THIS task call write_file" without them would be
        answered by a write_file from three tasks ago, and every later task would validate itself on
        the strength of earlier work. Returns True if this call actually started the task.
        """
        if task.status is TaskStatus.IN_PROGRESS:
            return False
        self.plan.begin(task)
        self.job.task_tool_offsets.setdefault(task.id, len(self.job.tools_called))
        self.job.task_exit_offsets.setdefault(task.id, len(self.job.exit_code_log))
        # A finished task's quiet rounds must not be evidence against the task that follows it.
        self._recent.clear()
        if not task.validators:
            # A model-proposed task usually arrives without validators; a plan whose tasks cannot be
            # checked is a checklist, which is exactly what this system is not.
            task.validators = infer_validators(task)
        logger.info("job %s: starting task %s (%s)", self.job.id, task.id, task.objective)
        self.sync()
        return True

    def tools_in_task(self, task: Task) -> list[str]:
        return self.job.tools_called[self.job.task_tool_offsets.get(task.id, 0):]

    def exit_codes_in_task(self, task: Task) -> list[int]:
        return self.job.exit_code_log[self.job.task_exit_offsets.get(task.id, 0):]

    # --- context -------------------------------------------------------------
    def apply_task_context(
        self, messages: list[dict], message_rounds: list[int], task: Task, current_round: int
    ) -> None:
        """Ensure exactly one live execution-state block, describing the current task, sitting at the
        end of the transcript.

        Removing the previous block rather than appending alongside it is the point. The two lists
        are index-matched (compaction reads round numbers positionally), so both are edited together
        — a drift here would silently mis-age unrelated messages. Safe to delete at this position
        because these blocks are only ever inserted at a round boundary, never between an assistant
        tool_calls message and its results.
        """
        for i in range(len(messages) - 1, -1, -1):
            content = messages[i].get("content")
            if (
                messages[i].get("role") == "user"
                and isinstance(content, str)
                and content.startswith(TASK_CONTEXT_MARK)
            ):
                del messages[i]
                del message_rounds[i]
        messages.append({"role": "user", "content": task_context_block(self.plan, task)})
        message_rounds.append(current_round)

    # --- progress ------------------------------------------------------------
    def snapshot_repo(self) -> RepoSnapshot:
        return snapshot(self.repository)

    def record_round(
        self,
        task: Task,
        *,
        before: RepoSnapshot,
        tools_this_round: Sequence[str],
        reasoning_chars: int,
    ) -> ProgressSignal:
        """Fold one round's outcome into the task's state and return what actually changed.

        `reasoning_chars` is accumulated but is deliberately NOT an input to whether progress
        occurred. That asymmetry is the correction this whole system makes: generation was being
        read as work, and a model that generated 39,655 reasoning tokens across 48 minutes while
        writing zero files was indistinguishable, to every guard that existed, from one doing its
        job.
        """
        signal = compare(before, self.snapshot_repo(), tools_ran=tools_this_round)
        self._recent.append(signal)
        task.rounds_spent += 1
        task.reasoning_chars += reasoning_chars
        if signal.made_progress:
            task.rounds_without_progress = 0
            task.note(signal.describe())
        else:
            task.rounds_without_progress += 1
        return signal

    def intervention_reason(self, task: Task) -> str | None:
        """Whether this task has stopped advancing, and which flavour of stuck it is. None means
        carry on — the common case, and it must stay cheap."""
        if task.rounds_without_progress >= MAX_ROUNDS_WITHOUT_PROGRESS:
            return InterventionReason.NO_PROGRESS
        if is_thrashing(list(self._recent)):
            return InterventionReason.THRASHING
        if task.reasoning_chars > MAX_REASONING_CHARS_PER_TASK:
            return InterventionReason.REASONING_EXHAUSTED
        if task.rounds_spent >= MAX_ROUNDS_PER_TASK:
            return InterventionReason.TOO_MANY_ROUNDS
        return None

    def forced_tool_for(self, task: Task, available_tool_names: set[str]) -> str | None:
        """The one tool call that would actually advance this task, or None if nothing specific
        applies.

        Naming a tool rather than demanding "call something" is not a refinement, it is the whole
        mechanism. `tool_choice="required"` was tried first and measured: after a round was cut, the
        model satisfied it with `screenshot` against a URL serving nothing (ERR_CONNECTION_REFUSED)
        and `list_directory` on an empty repository, then went straight back to planning. Forcing
        *a* tool only buys a tool call; forcing *the* tool buys the task.

        Preference order is by what is outstanding, not by what is listed first: a required tool the
        task has not yet called beats one it has, and a missing expected artifact means write_file
        regardless of what else the task nominally requires.
        """
        called = set(self.tools_in_task(task))
        for name in task.required_tools:
            if name not in called and name in available_tool_names:
                return name

        # Nothing outstanding by name. Before falling through, refuse to demand a tool this task has
        # ALREADY run without advancing — repeating it is not progress, it is the thrash itself.
        #
        # Observed exactly: a task whose required tool was list_directory, on an EMPTY repository.
        # The listing returned nothing both times, so the task could never satisfy itself, and the
        # intervention forced the same call three times, failed the task, created a recovery task,
        # and forced it three more times. Eleven list_directory calls, two failed tasks, nothing
        # learned after the first one. A tool that has already answered has nothing left to say.
        exhausted = {t for t in called if t in _NON_ADVANCING_WHEN_REPEATED}
        # Every named tool has been called at least once, yet the task is not finished and nothing is
        # moving. If an artifact is still missing or unusable, the outstanding action is unambiguous
        # — but WHICH action depends on whether anything is there yet.
        if task.expected_artifacts:
            result = validate_task(
                task,
                repository=self.repository,
                tools_called_in_task=self.tools_in_task(task),
                exit_codes=self.exit_codes_in_task(task),
                design=getattr(self.job, "design", None),
            )
            if not result.passed and "artifacts_exist" in result.checked:
                # A file that exists but is incomplete must be FINISHED, not written again. Forcing
                # write_file here was observed producing two full write_file calls to the same path
                # inside one task: the model wrote a partial file, the substance check correctly
                # rejected it, and the forced call made it regenerate the entire document from
                # scratch — tens of thousands of tokens spent reproducing work already on disk.
                # edit_file changes what is there and cannot discard the rest of it.
                if self._artifact_partially_written(task) and "edit_file" in available_tool_names:
                    return "edit_file"
                if "write_file" in available_tool_names:
                    return "write_file"
        # Last resort: a required tool that is still worth calling. Anything read-only that already
        # answered in this task is skipped — see _NON_ADVANCING_WHEN_REPEATED. If that leaves
        # nothing, prefer the action that actually produces something over another look around.
        remaining = [n for n in task.required_tools
                     if n in available_tool_names and n not in exhausted]
        if remaining:
            return remaining[0]
        for fallback in ("write_file", "edit_file"):
            if fallback in available_tool_names and task.expected_artifacts:
                return fallback
        return None

    def _artifact_partially_written(self, task: Task) -> bool:
        """True when at least one expected artifact is already on disk with real content in it.

        The distinction that decides between "write it" and "finish it". Checked against the
        filesystem rather than against whether write_file appears in the task's history, because a
        write that was refused (see the destructive-overwrite guard in tools.py) also appears there.
        """
        try:
            root = repo_root(self.repository)
        except Exception:  # noqa: BLE001 - repository not loaded; treat as nothing written
            return False
        for pattern in task.expected_artifacts:
            if ".." in pattern.replace("\\", "/").split("/"):
                continue
            try:
                target = root / pattern
                if target.is_file() and target.stat().st_size > 200:
                    return True
            except OSError:
                continue
        return False

    def intervene(
        self,
        task: Task,
        reason: str,
        messages: list[dict],
        message_rounds: list[int],
        current_round: int,
        available_tool_names: set[str],
    ) -> str | None:
        """Step in on an unproductive task. Returns the tool name to force next round, if any.

        Counts an INTERVENTION, not a validation attempt. The two are separate budgets because they
        are separate failures: a rejected completion means the model thinks it is done and is wrong;
        an intervention means it is not finishing at all. Sharing one counter (as an earlier version
        did) let three slow-but-legitimate rounds exhaust the validation budget of a task that had
        never once claimed to be finished. Once the intervention budget is spent the task is
        abandoned rather than forced a fourth time, and `recover` gets a chance at a narrower one.
        """
        task.interventions += 1
        forced = self.forced_tool_for(task, available_tool_names)
        task.next_action = (
            f"call {forced} now — this task has not advanced in "
            f"{task.rounds_without_progress} rounds"
            if forced
            else "produce the artifact this task requires, or state plainly why it cannot be produced"
        )
        logger.warning(
            "job %s: intervening on task %s (reason=%s intervention=%s/%s forcing=%s)",
            self.job.id, task.id, reason, task.interventions, MAX_INTERVENTIONS_PER_TASK, forced,
        )
        self._emit({"tool_call": {"name": "_task_intervention", "args": {
            "task": task.objective, "reason": reason, "attempt": task.interventions,
            "forcing": forced or "",
        }}})
        self._emit({"status": f"Not advancing — {task.next_action}"})
        messages.append({"role": "user", "content": _intervention_message(task, reason, forced)})
        message_rounds.append(current_round)
        # Reset the streak: the intervention IS the response to it, and leaving it high would fire
        # again on the very next round regardless of whether the forced call worked.
        task.rounds_without_progress = 0
        task.reasoning_chars = 0
        task.rounds_spent = 0
        # `intervention_reason` also consults is_thrashing(self._recent), and that window still held
        # the same quiet rounds this intervention was the response to — so if the forced tool was
        # read-only and already in the window's vocabulary, thrashing stayed true and fired again on
        # the very next round, failing a task in three consecutive rounds. The intervention IS the
        # response to that history; clearing it is what makes the next round a fresh judgement.
        self._recent.clear()
        if task.interventions >= MAX_INTERVENTIONS_PER_TASK:
            # Forcing has stopped working. Abandoning the task here — rather than forcing a fourth,
            # fifth, hundredth time — is what guarantees the job terminates: without it, a model
            # that ignores or cannot satisfy the forced call has an unbounded loop, which is the
            # same shape as the failure this whole system replaces, just louder.
            self.plan.fail(task, f"forced forward {task.interventions} times without advancing")
            self.recover(task)
            self.sync()
            return None
        self.sync()
        return forced

    # --- completion ----------------------------------------------------------
    def validate_current(self, task: Task, *, before: RepoSnapshot | None = None) -> Any:
        return validate_task(
            task,
            repository=self.repository,
            tools_called_in_task=self.tools_in_task(task),
            exit_codes=self.exit_codes_in_task(task),
            snapshot_before=before,
            # The design intent decided for this job, so a frontend task can be checked against
            # what it was supposed to BE and not only against what exists.
            design=getattr(self.job, "design", None),
        )

    def try_advance(self, task: Task) -> bool:
        """Complete a task the moment its checks actually pass, without waiting to be told.

        Completion used to be evaluated in one place only: a round where the model returned NO tool
        calls, read as a claim of "finished". That quietly made the model the trigger. A task whose
        validators had already passed stayed IN_PROGRESS for as long as the model kept calling
        tools — and a model with no remaining useful action does not fall silent, it invents one.

        Observed exactly that: task one was "inspect the repository and establish the conventions",
        its check was "list_directory was called", and that passed on round one. Fifteen rounds
        later it was still the active task, with nine list_directory calls out of nineteen tools,
        a screenshot of a repository containing no page, and an intervention — all of it work the
        model manufactured because nothing had told it the task was over.

        Codexa owns when a task is complete. Owning that means noticing, not waiting to be asked.

        Only ever advances a task that has genuinely made progress and genuinely passes; a task with
        no mechanical check is left alone, because "nothing to verify" must not become "complete the
        instant it starts".
        """
        if task.status is not TaskStatus.IN_PROGRESS or not task.validators:
            return False
        if not task.progress_notes and not self.tools_in_task(task):
            return False
        # Cheap checks only. This runs after EVERY tool round, and the full set includes
        # `renders_cleanly` (launches Chromium, loads the page, scrolls it, waits for motion to
        # settle) and `no_build_errors` (spawns `npx tsc --noEmit`, up to 30s). A twelve-round task
        # was paying twelve browser launches, most of them against a half-written file — slow, and
        # actively wrong, because a render that legitimately fails mid-build would fail the check on
        # work still in progress.
        #
        # An expensive check belongs where a completion is actually being CLAIMED, not on a
        # speculative poll. So advancement here requires the cheap checks to pass; anything with an
        # expensive validator is left for on_completion_claim to settle.
        if set(task.validators) & _EXPENSIVE_VALIDATORS:
            return False
        result = self.validate_current(task)
        if not result.passed:
            return False
        self.plan.record_validation(task, True, result.detail)
        logger.info("job %s: task %s satisfied its checks — advancing without waiting for a claim",
                    self.job.id, task.id)
        self._emit({"tool_call": {"name": "_task_validation", "args": {
            "task": task.objective, "status": "passed", "detail": result.detail,
            "checked": result.checked, "advanced": "automatically",
        }}})
        self._emit({"status": f"Done: {task.objective}"})
        self.sync()
        return True

    def on_completion_claim(
        self,
        task: Task,
        messages: list[dict],
        message_rounds: list[int],
        current_round: int,
    ) -> bool:
        """The model produced a round with no tool calls while a task is active — i.e. it believes
        this task is done. Check reality and decide.

        Returns True if the task is now COMPLETED (the caller advances), False if it stays active
        (the caller has been handed a correction message and should run another round).
        """
        result = self.validate_current(task)
        completed = self.plan.record_validation(task, result.passed, result.detail)
        self._emit({"tool_call": {"name": "_task_validation", "args": {
            "task": task.objective,
            "status": "passed" if result.passed else "failed",
            "detail": result.detail,
            "checked": result.checked,
        }}})
        if completed:
            logger.info("job %s: task %s completed (%s)", self.job.id, task.id, result.detail)
            self._emit({"status": f"Verified: {task.objective}"})
            self.sync()
            return True
        if task.status is TaskStatus.FAILED:
            logger.warning("job %s: task %s failed — %s", self.job.id, task.id, task.failure_reason)
            self.recover(task)
            self.sync()
            return False
        messages.append({"role": "user", "content": (
            f"[SYSTEM: this task is NOT complete. Codexa checked and found: {result.detail}\n\n"
            f"Task: {task.objective}\n"
            "Saying it is done does not complete it — the check above runs against the repository "
            "itself. Do not explain, apologise, or restate the plan. Make the outstanding thing "
            "true with a tool call.]"
        )})
        message_rounds.append(current_round)
        self.sync()
        return False

    def recover(self, task: Task) -> bool:
        """Replace a failed task with a narrower repair task, and re-point its dependents at the
        replacement.

        Without the re-pointing this would be useless: `plan.fail` blocks everything downstream of a
        failed task, so a repair inserted after it would sit behind a dependency that can never be
        satisfied and the plan would be permanently stuck.

        Recovery does not recurse. A repair that itself fails is not repaired again — that produced
        a real "Recover: Recover: Recover: ..." chain that burned the entire revision budget
        re-attempting something the run had already demonstrated three times over that it could not
        do, and buried the actual first failure under four layers of near-identical task names. One
        repair per task is the whole allowance; after that the task stays failed and the plan says
        so plainly.
        """
        if task.is_recovery:
            logger.info("job %s: task %s is already a recovery — not recovering again", self.job.id, task.id)
            return False
        repair_objective = f"Recover: {task.objective}"
        if any(t.objective == repair_objective for t in self.plan.tasks):
            # One failure can reach `recover` twice in a single round — once from `intervene`
            # exhausting the intervention budget, once from `on_completion_claim` seeing the task it
            # just failed. That inserted two identical repair tasks and spent two of the five plan
            # revisions on one failure, leaving nothing for a genuine second problem.
            return False
        if not self.plan.can_revise():
            logger.warning("job %s: no revision budget left to recover task %s", self.job.id, task.id)
            return False
        repair = make_task(
            f"Recover: {task.objective}",
            index=len(self.plan.tasks) + 1,
            required_tools=task.required_tools,
            expected_artifacts=task.expected_artifacts,
            completion_criteria=task.completion_criteria,
            validators=task.validators,
        )
        repair.is_recovery = True
        repair.note(f"previous attempt failed: {task.failure_reason or task.validation_detail}")
        if not self.plan.insert_after(task.id, repair):
            return False
        for other in self.plan.tasks:
            if task.id in other.depends_on:
                other.depends_on = [repair.id if d == task.id else d for d in other.depends_on]
                self.plan.unblock(other)
        self._emit({"tool_call": {"name": "_task_recovery", "args": {
            "failed": task.objective, "recovery": repair.objective,
        }}})
        logger.info("job %s: inserted recovery task %s", self.job.id, repair.id)
        return True

    # --- job-level -----------------------------------------------------------
    def blocking_reason(self) -> str | None:
        """Why the job must not report success yet. None means the plan is genuinely finished.

        This is the gate that replaces "the model stopped calling tools, so it must be done". A job
        whose plan still has outstanding work has not finished, no matter how confident the final
        message sounds.
        """
        if not self.plan.tasks:
            return None
        if self.plan.is_stuck():
            outstanding = ", ".join(t.objective for t in self.plan.remaining())
            return f"blocked with work outstanding: {outstanding}"
        if not self.plan.is_complete():
            remaining = self.plan.remaining()
            return f"{len(remaining)} task(s) still outstanding: {remaining[0].objective}"
        return None

    def failed_tasks(self) -> list[Task]:
        """Tasks the plan gave up on. Non-empty means the run finished with known holes in it.

        Reported rather than absorbed. `is_complete()` is satisfied by "every task terminal and at
        least one succeeded", which is the right rule for advancing the plan and the wrong one for
        announcing success: a UI build whose screenshot task failed three times has produced a file
        nobody ever looked at, and calling that done is the same class of claim as the model saying
        "Done." with an empty repository. The job surfaces these instead, and Continue retries them.
        """
        return [t for t in self.plan.tasks if t.status is TaskStatus.FAILED]


def _intervention_message(task: Task, reason: str, forced: str | None) -> str:
    """The text sent alongside a forced tool call.

    The forcing is what works; this explains it, so the model's next round is aimed rather than
    merely legal. Measured lesson behind the tone: a polite "your next message must call a tool" was
    followed by 23,692 more characters of planning and no call. Explanations do not constrain — they
    only stop the constraint from looking arbitrary once it is applied.
    """
    why = {
        InterventionReason.NO_PROGRESS: (
            "several rounds passed with nothing created or changed in the repository"
        ),
        InterventionReason.THRASHING: (
            "the same few tools were called repeatedly without changing anything"
        ),
        InterventionReason.REASONING_EXHAUSTED: (
            "this task has spent its entire planning budget without producing its artifact"
        ),
        InterventionReason.TOO_MANY_ROUNDS: "this task has run far longer than it should",
    }.get(reason, "this task stopped advancing")
    lines = [
        f"[SYSTEM: Codexa stopped this task — {why}.",
        "",
        f"Task: {task.objective}",
    ]
    if task.expected_artifacts:
        lines.append(f"Must exist when done: {', '.join(task.expected_artifacts)}")
    if forced == "edit_file":
        # The artifact already exists with real content. Saying "write the first version now" here
        # was actively harmful: it produced two full write_file calls to the same path in one task,
        # the second regenerating from scratch a document already sitting on disk.
        lines.append("")
        lines.append(
            "The file already exists and has real content in it — it is just not finished. Your "
            "next message must be an edit_file call that completes it in place. Do NOT rewrite the "
            "whole file with write_file: that throws away what is already there and regenerates it "
            "for nothing. Read it first if you need to see where it stops."
        )
    elif forced:
        lines.append("")
        lines.append(
            f"Your next message must be a {forced} call and nothing else. Planning for this task is "
            "over. If you were deciding between approaches, take the first one and write it. Write "
            "the COMPLETE file in that one call — not a partial version you intend to finish in a "
            "later call, which costs a full second generation of everything you already wrote."
        )
    lines.append("]")
    return "\n".join(lines)
