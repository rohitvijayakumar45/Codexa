"""The execution controller, and the agent loop actually running under it.

The unit tests below exercise controller policy directly. The integration tests at the bottom drive
`JobManager._loop` with a scripted model and a tool executor that writes real files into a temporary
repository — so "the task completed" means a file genuinely appeared on disk and a validator
genuinely found it, not that a mock was satisfied.

That end-to-end shape is deliberate. The failure this system exists to prevent was invisible to
every unit-level guard in the loop: each one was individually correct, and a model still spent 48
minutes and 39,655 reasoning tokens producing nothing, because the thing that was broken lived in
how they composed. Tests that stop at the seams would have missed it too.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.agents.controller import (
    MAX_INTERVENTIONS_PER_TASK,
    MAX_ROUNDS_WITHOUT_PROGRESS,
    TASK_CONTEXT_MARK,
    ExecutionController,
)
from backend.agents.jobs import Job, JobManager
from backend.agents.plan import ExecutionPlan, TaskStatus, make_task
from backend.agents.progress import RepoSnapshot
from backend.agents.tools import _commit_direction


# ── harness ───────────────────────────────────────────────────────────────────


# A page substantial enough to be a real artifact. Tests here are about plan advancement, so the
# written file must clear the substance rule in backend/agents/validators.py — a stub like
# "<!doctype html><h1>real</h1>" is now correctly rejected as placeholder-shaped, which would make
# every one of these tests fail for a reason that has nothing to do with what they check.
_REAL_PAGE = (
    "<!doctype html><html><head><title>Archive</title></head><body><main>"
    + "<p>Real content.</p>" * 40
    + "</main></body></html>"
)

def _job(plan: ExecutionPlan | None = None, *, required_tools=("write_file",), groups=("code",)) -> Job:
    return Job(
        id="controller-job",
        repository="demo",
        model="fake-model",
        messages=[{"role": "user", "content": "Build a single HTML page"}],
        message_rounds=[-100],
        contract={
            "intent": "CREATE_ARTIFACT", "required_tools": list(required_tools),
            "allowed_tools": [], "success_criteria": [], "constraints": [], "suggested_workflow": [],
        },
        active_tool_groups=list(groups),
        working_repo="demo",
        contract_source="Build a single HTML page",
        plan=plan.to_dict() if plan else None,
    )


def _build_plan() -> ExecutionPlan:
    """Two tasks: one that must produce a file, one that must look at it. Small on purpose — the
    behaviour under test is advancement and gating, and a longer plan only adds rounds."""
    write = make_task(
        "Write the page", index=1,
        required_tools=["write_file"], expected_artifacts=["index.html"],
        validators=["artifacts_exist", "tools_called"],
    )
    look = make_task(
        "Look at the result", index=2, depends_on=[write.id],
        required_tools=["screenshot"], validators=["tools_called"],
    )
    return ExecutionPlan(objective="Build a single HTML page", tasks=[write, look], committed=True)


class _Controller:
    """Builds a controller over a real plan with a recording emit, for the unit tests."""

    def __init__(self, plan: ExecutionPlan, repository: str = "demo"):
        self.events: list[dict] = []
        self.job = _job(plan)
        self.plan = plan
        self.controller = ExecutionController(
            self.job, plan, repository=repository, emit=self.events.append
        )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A real temporary repository for the reality checks to run against. Nothing in this file may
    read the developer's actual repositories — a test that passes because of a file someone happened
    to have on disk is worse than no test."""
    # Patched in each module's own namespace: all three do `from backend.files.api import
    # repo_root`, so the name each one calls is its own. Missing any of them means that module
    # silently reads the developer's real repositories instead of this temporary one.
    for module in ("validators", "progress", "controller"):
        monkeypatch.setattr(f"backend.agents.{module}.repo_root", lambda _r: tmp_path)
    return tmp_path


# ── controller policy ─────────────────────────────────────────────────────────


class TestStartingATask:
    def test_beginning_a_task_records_where_its_history_starts(self, repo):
        """`job.tools_called` is cumulative for the whole job. Without an offset, asking "did THIS
        task call write_file?" is answered by a write_file from three tasks ago, and every later
        task validates itself on the strength of earlier work."""
        h = _Controller(_build_plan())
        h.job.tools_called = ["list_directory", "read_file"]
        task = h.controller.current_task()
        h.controller.begin_task(task)

        assert task.status is TaskStatus.IN_PROGRESS
        assert h.controller.tools_in_task(task) == []
        h.job.tools_called.append("write_file")
        assert h.controller.tools_in_task(task) == ["write_file"]

    def test_a_task_proposed_without_validators_gets_them(self, repo):
        # A plan whose tasks cannot be checked is a checklist the model ticks off itself.
        plan = ExecutionPlan(objective="x", tasks=[
            make_task("write it", index=1, required_tools=["write_file"],
                      expected_artifacts=["index.html"]),
        ])
        h = _Controller(plan)
        h.controller.begin_task(plan.tasks[0])
        assert plan.tasks[0].validators

    def test_beginning_an_already_started_task_is_a_no_op(self, repo):
        h = _Controller(_build_plan())
        task = h.controller.current_task()
        assert h.controller.begin_task(task) is True
        assert h.controller.begin_task(task) is False


class TestTheContextTheModelSees:
    def test_exactly_one_execution_state_block_is_ever_live(self, repo):
        """Re-appended every round. Left to accumulate, a model would read four different "CURRENT
        TASK" declarations in its own history with no way to tell which is current — and pay for all
        of them on every round."""
        h = _Controller(_build_plan())
        messages, rounds = list(h.job.messages), list(h.job.message_rounds)
        task = h.controller.current_task()

        for r in range(4):
            h.controller.apply_task_context(messages, rounds, task, r)

        blocks = [m for m in messages if str(m.get("content", "")).startswith(TASK_CONTEXT_MARK)]
        assert len(blocks) == 1
        assert len(messages) == len(rounds), "the two lists are index-matched; drift mis-ages messages"

    def test_it_describes_the_current_task_and_moves_with_the_plan(self, repo):
        h = _Controller(_build_plan())
        messages, rounds = list(h.job.messages), list(h.job.message_rounds)
        first = h.controller.current_task()
        h.controller.apply_task_context(messages, rounds, first, 0)
        assert "Write the page" in messages[-1]["content"]

        h.plan.complete(first)
        second = h.controller.current_task()
        h.controller.apply_task_context(messages, rounds, second, 1)
        assert "Look at the result" in messages[-1]["content"]
        assert len([m for m in messages if str(m.get("content", "")).startswith(TASK_CONTEXT_MARK)]) == 1


class TestProgressIsMeasuredNotAsserted:
    def _record(self, h, *, tools, before=None, after=None, reasoning=0):
        task = h.controller.current_task()
        h.controller.begin_task(task)
        with patch.object(h.controller, "snapshot_repo", return_value=after or RepoSnapshot()):
            return task, h.controller.record_round(
                task, before=before or RepoSnapshot(),
                tools_this_round=tools, reasoning_chars=reasoning,
            )

    def test_a_round_that_wrote_a_file_resets_the_streak_and_leaves_a_note(self, repo):
        h = _Controller(_build_plan())
        after = RepoSnapshot(files={"index.html": (500, 1)}, taken_at=1.0)
        task, signal = self._record(h, tools=["write_file"], after=after)
        assert signal.made_progress
        assert task.rounds_without_progress == 0
        assert task.progress_notes

    def test_a_round_that_only_thought_advances_the_no_progress_streak(self, repo):
        h = _Controller(_build_plan())
        task, signal = self._record(h, tools=[], reasoning=39_000)
        assert signal.made_progress is False
        assert task.rounds_without_progress == 1

    def test_reasoning_is_accumulated_but_never_counts_as_progress(self, repo):
        """The correction this system makes. Generation was being read as work: 39,655 reasoning
        tokens across 48 minutes with zero files written was, to every guard that existed,
        indistinguishable from a job doing its job."""
        h = _Controller(_build_plan())
        task, _ = self._record(h, tools=[], reasoning=50_000)
        assert task.reasoning_chars == 50_000
        assert task.rounds_without_progress == 1


class TestSteppingIn:
    def _stuck(self, repo, streak=MAX_ROUNDS_WITHOUT_PROGRESS):
        h = _Controller(_build_plan())
        task = h.controller.current_task()
        h.controller.begin_task(task)
        task.rounds_without_progress = streak
        return h, task

    def test_a_healthy_task_is_left_alone(self, repo):
        h, task = self._stuck(repo, streak=0)
        assert h.controller.intervention_reason(task) is None

    def test_a_stalled_streak_triggers_an_intervention(self, repo):
        h, task = self._stuck(repo)
        assert h.controller.intervention_reason(task) == "no_progress"

    def test_the_forced_call_is_the_one_the_task_actually_needs(self, repo):
        """`tool_choice="required"` was tried first and measured: after a cut, the model satisfied it
        with `screenshot` against a URL serving nothing (ERR_CONNECTION_REFUSED) and
        `list_directory` on an empty repository, then went straight back to planning. Forcing *a*
        tool buys a tool call; forcing *the* tool buys the task."""
        h, task = self._stuck(repo)
        forced = h.controller.forced_tool_for(task, {"write_file", "screenshot", "list_directory"})
        assert forced == "write_file"

    def test_a_requirement_already_met_is_not_demanded_again(self, repo):
        h, task = self._stuck(repo)
        h.job.tools_called.append("write_file")
        task.required_tools = ["write_file", "screenshot"]
        assert h.controller.forced_tool_for(task, {"write_file", "screenshot"}) == "screenshot"

    def test_it_never_names_a_tool_this_job_cannot_call(self, repo):
        # Naming a tool absent from the job's active groups makes the request unsatisfiable — the
        # model would be forbidden from replying and unable to comply.
        h, task = self._stuck(repo)
        assert h.controller.forced_tool_for(task, {"read_file"}) is None

    def test_intervening_counts_an_intervention_not_a_validation_attempt(self, repo):
        # Separate budgets: a rejected completion means the model thinks it is done and is wrong; an
        # intervention means it is not finishing at all. Sharing one counter let three slow-but-
        # legitimate rounds exhaust the validation budget of a task that never claimed to be done.
        h, task = self._stuck(repo)
        h.controller.intervene(task, "no_progress", h.job.messages, h.job.message_rounds, 3,
                               {"write_file"})
        assert task.interventions == 1
        assert task.attempts == 0

    def test_the_intervention_message_names_the_forced_call(self, repo):
        h, task = self._stuck(repo)
        h.controller.intervene(task, "no_progress", h.job.messages, h.job.message_rounds, 3,
                               {"write_file"})
        assert "write_file" in h.job.messages[-1]["content"]

    def test_the_intervention_message_includes_last_check_detail(self, repo):
        """A model that wrote an incomplete file and was told 'call write_file' regenerated the
        entire document from scratch. Including the actual validation failure in the message
        gives the model enough information to fix the defect instead of starting over."""
        h, task = self._stuck(repo)
        task.validation_detail = "has no <body> — the document was never finished"
        h.controller.intervene(task, "no_progress", h.job.messages, h.job.message_rounds, 3,
                               {"write_file"})
        assert "has no <body>" in h.job.messages[-1]["content"]

    def test_the_streak_resets_so_it_does_not_fire_again_immediately(self, repo):
        h, task = self._stuck(repo)
        h.controller.intervene(task, "no_progress", h.job.messages, h.job.message_rounds, 3,
                               {"write_file"})
        assert h.controller.intervention_reason(task) is None

    def test_forcing_is_abandoned_rather_than_repeated_forever(self, repo):
        """Without a ceiling, a model that ignores or cannot satisfy the forced call has an
        unbounded loop — the same shape as the failure this replaces, just louder."""
        h, task = self._stuck(repo)
        for _ in range(MAX_INTERVENTIONS_PER_TASK):
            task.rounds_without_progress = MAX_ROUNDS_WITHOUT_PROGRESS
            h.controller.intervene(task, "no_progress", h.job.messages, h.job.message_rounds, 3,
                                   {"write_file"})
        assert task.status is TaskStatus.FAILED


class TestCompletionClaims:
    def test_saying_it_is_done_without_the_artifact_does_not_complete_it(self, repo):
        h = _Controller(_build_plan())
        task = h.controller.current_task()
        h.controller.begin_task(task)

        completed = h.controller.on_completion_claim(task, h.job.messages, h.job.message_rounds, 1)

        assert completed is False
        assert task.status is not TaskStatus.COMPLETED
        assert "index.html" in h.job.messages[-1]["content"]

    def test_the_correction_tells_the_model_what_is_actually_missing(self, repo):
        h = _Controller(_build_plan())
        task = h.controller.current_task()
        h.controller.begin_task(task)
        h.controller.on_completion_claim(task, h.job.messages, h.job.message_rounds, 1)
        correction = h.job.messages[-1]["content"]
        assert "NOT complete" in correction
        assert "tool call" in correction

    def test_a_real_artifact_on_disk_completes_it(self, repo):
        (repo / "index.html").write_text(_REAL_PAGE, encoding="utf-8")
        h = _Controller(_build_plan())
        task = h.controller.current_task()
        h.controller.begin_task(task)
        h.job.tools_called.append("write_file")

        assert h.controller.on_completion_claim(task, h.job.messages, h.job.message_rounds, 1) is True
        assert task.status is TaskStatus.COMPLETED
        assert h.controller.current_task().objective == "Look at the result"

    def test_calling_an_unrelated_tool_does_not_satisfy_the_task(self, repo):
        # Activity is not achievement: the observed escape was calling the cheapest available tools
        # to satisfy a constraint, then resuming planning.
        h = _Controller(_build_plan())
        task = h.controller.current_task()
        h.controller.begin_task(task)
        h.job.tools_called.extend(["list_directory", "screenshot"])
        assert h.controller.on_completion_claim(task, h.job.messages, h.job.message_rounds, 1) is False


class TestRecovery:
    def test_a_failed_task_is_replaced_by_a_narrower_repair(self, repo):
        h = _Controller(_build_plan())
        task = h.controller.current_task()
        h.plan.fail(task, "never produced the file")
        assert h.controller.recover(task) is True

        repair = h.plan.tasks[1]
        assert repair.is_recovery is True
        assert repair.expected_artifacts == task.expected_artifacts
        assert h.controller.current_task() is repair

    def test_dependents_are_repointed_at_the_repair(self, repo):
        # Otherwise the repair sits behind a dependency that is not the one downstream tasks name,
        # and plan order silently stops meaning anything.
        h = _Controller(_build_plan())
        task, dependent = h.plan.tasks[0], h.plan.tasks[1]
        h.plan.fail(task, "boom")
        h.controller.recover(task)
        assert dependent.depends_on == [h.plan.tasks[1].id]

    def test_recovery_does_not_recurse(self, repo):
        """A real "Recover: Recover: Recover: ..." chain burned the entire revision budget
        re-attempting something the run had already demonstrated three times over that it could not
        do, and buried the original failure under four near-identical task names."""
        h = _Controller(_build_plan())
        task = h.plan.tasks[0]
        h.plan.fail(task, "boom")
        h.controller.recover(task)

        repair = next(t for t in h.plan.tasks if t.is_recovery)
        h.plan.fail(repair, "boom again")
        assert h.controller.recover(repair) is False
        assert sum(1 for t in h.plan.tasks if t.is_recovery) == 1

    def test_a_recovery_task_gets_a_reduced_intervention_budget(self, repo):
        """A recovery task gets only ONE forced-tool attempt, not three. The original task
        already exhausted its intervention budget — giving the recovery the same budget lets
        it burn through the exact same failure pattern a second time before the chain stops.
        Historical evidence (premature-completion-job, status-tool-call-job) shows every
        recovery task hitting its full intervention budget, confirming the model was not
        learning but merely exhausting the constraint."""
        h = _Controller(_build_plan())
        task = h.controller.current_task()
        task.interventions = MAX_INTERVENTIONS_PER_TASK  # original exhausted
        h.plan.fail(task, "forced forward 3 times without advancing")
        h.controller.recover(task)
        repair = next(t for t in h.plan.tasks if t.is_recovery)
        # Recovery starts at 2 (so one forced attempt remains before hitting MAX_INTERVENTIONS=3)
        assert repair.interventions == MAX_INTERVENTIONS_PER_TASK - 1

    def test_a_recovery_is_abandoned_after_one_intervention(self, repo):
        """After the pre-seeded interventions plus one more, the recovery task should fail
        and not spawn another recovery (recursion is blocked by is_recovery)."""
        h = _Controller(_build_plan())
        task = h.controller.current_task()
        task.interventions = MAX_INTERVENTIONS_PER_TASK
        h.plan.fail(task, "exhausted")
        h.controller.recover(task)
        repair = next(t for t in h.plan.tasks if t.is_recovery)
        # Simulate one intervention reaching max
        repair.interventions = MAX_INTERVENTIONS_PER_TASK
        h.plan.fail(repair, "also exhausted")
        assert h.controller.recover(repair) is False  # no recursion
        assert sum(1 for t in h.plan.tasks if t.is_recovery) == 1


class TestTheJobLevelGate:
    def test_a_plan_with_work_left_blocks_completion(self, repo):
        h = _Controller(_build_plan())
        assert h.controller.blocking_reason() is not None

    def test_a_finished_plan_does_not_block(self, repo):
        h = _Controller(_build_plan())
        for task in h.plan.tasks:
            h.plan.complete(task)
        assert h.controller.blocking_reason() is None

    def test_a_stuck_plan_is_reported_as_blocked_not_finished(self, repo):
        plan = ExecutionPlan(objective="x", tasks=[
            make_task("orphan", index=1, depends_on=["t99-missing"]),
        ])
        assert _Controller(plan).controller.blocking_reason() is not None


# ── the loop, end to end ──────────────────────────────────────────────────────


def _chunk(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
        content=text, reasoning_content=None))])


def _thinking(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
        content=None, reasoning_content=text))])


class ScriptedLLM:
    """Plays a fixed sequence of rounds. Each entry is either a list of (tool_name, args) tuples or
    a string, meaning a final plain-text reply. Once the script runs out the model replies "done"
    forever — which is the interesting case, since a model insisting it is finished is exactly what
    the plan gate has to survive."""

    def __init__(self, script: list, *, thinking_per_round: int = 0):
        self.script = list(script)
        self.round = 0
        self.tool_choices: list = []
        self.thinking_per_round = thinking_per_round

    def _entry(self):
        return self.script[self.round] if self.round < len(self.script) else "done"

    def stream(self, model, messages, timeout=240, **kwargs):
        self.tool_choices.append(kwargs.get("tool_choice"))
        if self.thinking_per_round:
            yield _thinking("z" * self.thinking_per_round)
        yield _chunk("")

    def final_message(self):
        entry = self._entry()
        self.round += 1
        msg = MagicMock()
        msg.choices = [MagicMock()]
        if isinstance(entry, str):
            msg.choices[0].message.content = entry
            msg.choices[0].message.tool_calls = None
            return msg
        msg.choices[0].message.content = ""
        msg.choices[0].message.tool_calls = [
            SimpleNamespace(
                id=f"call_{self.round}_{i}",
                function=SimpleNamespace(name=name, arguments=__import__("json").dumps(args)),
            )
            for i, (name, args) in enumerate(entry)
        ]
        return msg

    # interface the loop expects of an LLMClient
    def record_usage(self, *a, **k):
        return {"prompt_tokens": 1, "completion_tokens": 1}

    def context_window(self, model):
        return 128_000

    def tier_of(self, model):
        return None

    def models_for_tier(self, tier):
        return []


@pytest.fixture
def loop(repo, monkeypatch):
    """Runs `_loop` for real against a temporary repository, with a tool executor that genuinely
    writes files. Everything the plan checks — artifact existence, tool history, progress — is then
    measured from real state rather than from a mock's memory."""

    def run(script, *, plan=None, thinking_per_round=0, contract_tools=("write_file",),
            commitment=None):
        llm = ScriptedLLM(script, thinking_per_round=thinking_per_round)
        job = _job(plan if plan is not None else _build_plan(),
                   required_tools=contract_tools, groups=("code", "browser", "repo"))
        if commitment is not None:
            # Simulates a job resuming mid-plan, past its own direction-commit task — needed to
            # test the authoring-specific "needs_structure" branch, which only fires once the
            # project direction is already settled.
            job.commitment = commitment

        def fake_execute(name, args, working_repo, **kwargs):
            context = kwargs.get("context")
            if name == "write_file":
                target = repo / args.get("path", "out.txt")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(args.get("content", ""), encoding="utf-8")
                return f"Wrote {args.get('path')}"
            if name == "run_command" and context is not None:
                context["exit_code"] = args.get("exit_code", 0)
                return "ran"
            if name == "commit_direction":
                # The real thing, not a fake string — tests that verify structure_task_id gets
                # stamped, or that a design commitment survives into the next round's context,
                # depend on this actually building the record jobs.py itself would build.
                return _commit_direction(
                    args.get("direction", ""), args.get("decisions"),
                    args.get("primary_artifact", ""), args.get("next_action", ""),
                    args.get("palette"), args.get("typography"), args.get("motion"),
                    args.get("rejected"), args.get("structure"),
                    context=context, prior_commitment=kwargs.get("prior_commitment"),
                )
            return f"{name} ok"

        manager = JobManager(llm=llm, graph=None, store=None)
        with patch("backend.agents.jobs.execute_tool", side_effect=fake_execute), \
             patch("backend.agents.jobs.litellm.stream_chunk_builder",
                   side_effect=lambda chunks, messages: llm.final_message()), \
             patch("backend.agents.jobs.reindex_repository"), \
             patch("backend.agents.jobs.extract_claims", return_value=[]):
            manager._loop(job, resuming=False)
        return job, llm

    return run


class TestTheLoopUnderAPlan:
    def test_a_model_that_does_the_work_finishes_the_job(self, loop, repo):
        job, _ = loop([
            [("write_file", {"path": "index.html", "content": _REAL_PAGE})],
            "Task one done.",
            [("screenshot", {"url": "http://localhost:8000"})],
            "All finished.",
        ])
        assert job.status == "done", job.events[-1]
        assert (repo / "index.html").read_text(encoding="utf-8").startswith("<!doctype html")
        assert all(t["status"] == "COMPLETED" for t in job.plan["tasks"])

    def test_a_model_that_only_says_done_never_finishes(self, loop, repo):
        """The silent-success failure, and the single most important behaviour here: a job reported
        `done` at round 6 having written zero files, because the model said so and nothing checked."""
        job, _ = loop(["Done!", "It is complete.", "I have finished the task."])
        assert job.status != "done"
        assert not (repo / "index.html").exists()
        assert job.plan["tasks"][0]["status"] != "COMPLETED"

    def test_the_plan_advances_one_task_at_a_time(self, loop, repo):
        job, _ = loop([
            [("write_file", {"path": "index.html", "content": _REAL_PAGE})],
            "Written.",
            [("screenshot", {"url": "x"})],
            "Looked at it.",
        ])
        statuses = [t["status"] for t in job.plan["tasks"]]
        assert statuses == ["COMPLETED", "COMPLETED"]

    def test_finishing_one_task_does_not_finish_the_job(self, loop, repo):
        # The round after a completed task looks exactly like a final answer. Treating it as one is
        # how a two-task build shipped with half of it done.
        job, _ = loop([
            [("write_file", {"path": "index.html", "content": _REAL_PAGE})],
            "I have written the page, so I am done.",
        ])
        assert job.status != "done"
        assert job.plan["tasks"][0]["status"] == "COMPLETED"
        assert job.plan["tasks"][1]["status"] != "COMPLETED"

    def test_an_empty_file_does_not_satisfy_the_task(self, loop, repo):
        # What an interrupted or refused write leaves behind. Accepting it would let a task validate
        # on the existence of its own failure.
        job, _ = loop([
            [("write_file", {"path": "index.html", "content": ""})],
            "Done.", "Really done.", "Done!",
        ])
        assert job.plan["tasks"][0]["status"] != "COMPLETED"

    def test_execution_state_reaches_the_model_and_the_ui(self, loop, repo):
        job, _ = loop([[("write_file", {"path": "index.html", "content": _REAL_PAGE})], "done"])
        assert any("plan" in e for e in job.events), "the UI never saw a plan"
        snapshot = next(e["plan"] for e in job.events if "plan" in e)
        assert snapshot["total"] == 2
        assert "reasoning" not in str(snapshot)

    def test_the_task_state_is_checkpointed_for_resume(self, loop, repo):
        job, _ = loop([[("write_file", {"path": "index.html", "content": _REAL_PAGE})], "done"])
        assert job.plan is not None
        restored = ExecutionPlan.from_dict(job.plan)
        assert restored.tasks[0].status is TaskStatus.COMPLETED
        assert restored.tasks[0].progress_notes


class TestTheLoopForcesTheRightCall:
    def test_a_stalled_task_gets_its_own_required_tool_forced(self, loop, repo):
        """The escalation ladder's last rung. Prompting failed (23,692 more characters of planning
        and no call); `required` was gamed with the two cheapest tools available. Naming the task's
        outstanding tool leaves no cheaper legal move."""
        _, llm = loop(["thinking about it", "still thinking", "nearly there", "hmm", "one moment"])
        forced = [c for c in llm.tool_choices if isinstance(c, dict)]
        assert forced, f"nothing was ever forced: {llm.tool_choices}"
        assert forced[0] == {"type": "function", "function": {"name": "write_file"}}

    def test_the_first_round_is_never_forced(self, loop, repo):
        # Forcing from the outset would stop a task that legitimately needs to look before it writes.
        _, llm = loop([[("write_file", {"path": "index.html", "content": _REAL_PAGE})], "done"])
        assert llm.tool_choices[0] == "auto"

    def test_forcing_releases_so_the_job_can_still_answer(self, loop, repo):
        # A final response is by definition not a tool call; leaving forcing on permanently means
        # the job can never end.
        job, llm = loop([
            "thinking", "thinking", "thinking",
            [("write_file", {"path": "index.html", "content": _REAL_PAGE})],
            "done", [("screenshot", {"url": "x"})], "done",
        ])
        assert "auto" in llm.tool_choices[3:], llm.tool_choices


class TestAuthoringGetsAStructurePlanBeforeTheWrite:
    """The decision/action split for authoring, one level below commit_direction itself.

    Measured cause: an authoring round given no plan reasons through the WHOLE artifact — every
    section, every interaction — before writing a single character, and that reasoning routinely
    outruns the budget before the tool call ever lands. One real job cut on the same authoring task
    twice in a row for exactly this reason (~80,000 characters combined, both discarded) and only
    wrote the file once forced on the third attempt. The existing commit_direction mechanism
    already proves the fix at the project level (decide -> durable state -> act); these tests prove
    it now also applies one task later, to the artifact itself.
    """

    def test_a_cut_on_an_uncommitted_authoring_task_asks_for_the_plan_not_the_write(self, loop, repo):
        # Project direction is already settled (pre-seeded, as if an earlier task committed it) but
        # this specific artifact has no structure plan yet — the branch under test.
        _, llm = loop(
            ["thinking"] * 6, thinking_per_round=45_000,
            commitment={"direction": "A single-page archive."},
        )
        forced = [c for c in llm.tool_choices if isinstance(c, dict)]
        assert forced, f"nothing was ever forced: {llm.tool_choices}"
        assert forced[0] == {"type": "function", "function": {"name": "commit_direction"}}

    def test_once_this_artifacts_structure_is_committed_the_cut_forces_the_write_instead(self, loop, repo):
        # Same task, same starting point, except structure_task_id already names THIS task's id —
        # simulating that an earlier round already committed the plan. The next cut must go
        # straight to the artifact tool, not ask for another plan.
        _, llm = loop(
            ["thinking"] * 6, thinking_per_round=45_000,
            commitment={
                "direction": "A single-page archive.",
                "design": {"structure": ["hero", "archive grid"], "structure_task_id": "t1-write-the-page"},
            },
        )
        forced = [c for c in llm.tool_choices if isinstance(c, dict)]
        assert forced, f"nothing was ever forced: {llm.tool_choices}"
        assert forced[0] == {"type": "function", "function": {"name": "write_file"}}

    def test_a_non_authoring_task_is_never_asked_for_structure(self, loop, repo):
        # "Look at the result" (task 2) has no expected_artifacts — it must never be routed into
        # the structure branch, which exists only for tasks that produce a file.
        plan = _build_plan()
        plan.complete(plan.tasks[0])  # advance past the authoring task
        _, llm = loop(
            ["thinking"] * 6, thinking_per_round=45_000, plan=plan,
            commitment={"direction": "A single-page archive."},
        )
        forced = [c for c in llm.tool_choices if isinstance(c, dict)]
        assert forced, f"nothing was ever forced: {llm.tool_choices}"
        assert forced[0] != {"type": "function", "function": {"name": "commit_direction"}}

    def test_the_structure_lands_on_the_job_and_stamps_the_task_id(self, loop, repo):
        # End to end through the real (unfaked) commit_direction, and through the real jobs.py
        # code that reads its result and stamps structure_task_id. The task must actually complete
        # after committing — a script that keeps re-committing past this task's own lifetime would
        # correctly (and separately-tested-above) re-stamp the id to whatever task is active by
        # then, which is not what this test is checking.
        job, _ = loop(
            [
                [("commit_direction", {"direction": "A single-page archive.",
                                       "structure": ["hero", "archive grid"]})],
                [("write_file", {"path": "index.html", "content": _REAL_PAGE})],
                "done", [("screenshot", {"url": "x"})], "done",
            ],
            commitment={"direction": "A single-page archive."},
        )
        design = (job.commitment or {}).get("design") or {}
        assert design.get("structure") == ["hero", "archive grid"]
        assert design.get("structure_task_id") == "t1-write-the-page"
        assert job.plan["tasks"][0]["status"] == "COMPLETED"


class TestTerminationIsGuaranteed:
    def test_a_model_that_never_complies_still_stops(self, loop, repo):
        """Against a permanently unproductive model the job must end on its own. An uncapped loop
        here would burn provider quota until a human noticed — which is how a 48-minute round became
        a 48-minute round."""
        job, llm = loop(["no", "nope", "still no"] * 40)
        assert job.status in ("error", "done")
        assert llm.round < 200

    def test_endless_reasoning_inside_a_task_is_cut_and_recorded(self, loop, repo):
        # The per-round cut turns an invisible hang into a bounded event; the controller is what
        # notices the task is not advancing across those rounds.
        job, _ = loop(["thinking"] * 12, thinking_per_round=45_000)
        assert job.status in ("error", "done")
        assert any("_task_intervention" in str(e) for e in job.events)

    def test_a_cancelled_job_stops_promptly(self, repo, monkeypatch):
        llm = ScriptedLLM([[("write_file", {"path": "index.html", "content": "x"})]] * 20)
        job = _job(_build_plan())
        job.cancelled = True
        manager = JobManager(llm=llm, graph=None, store=None)
        with patch("backend.agents.jobs.execute_tool", return_value="ok"), \
             patch("backend.agents.jobs.litellm.stream_chunk_builder",
                   side_effect=lambda chunks, messages: llm.final_message()):
            manager._loop(job, resuming=False)
        assert job.status == "done"
        assert llm.round == 0, "no round should run after cancellation"


class TestResumingKeepsTheExecutionPosition:
    def test_a_resumed_job_continues_the_same_task(self, loop, repo):
        """The point of persisting the plan: a restart, a model rotation, or a Continue click must
        not hand a fresh model the whole problem and hope it re-derives where the last one got to."""
        plan = _build_plan()
        plan.complete(plan.tasks[0])
        job, _ = loop([[("screenshot", {"url": "x"})], "done"], plan=plan)
        assert job.plan["tasks"][0]["status"] == "COMPLETED"
        assert job.plan["tasks"][1]["status"] == "COMPLETED"

    def test_a_plan_is_not_rebuilt_over_an_existing_one(self, loop, repo):
        plan = _build_plan()
        plan.tasks[0].objective = "A very specific objective that only this plan has"
        job, _ = loop(["done"], plan=plan)
        assert job.plan["tasks"][0]["objective"] == "A very specific objective that only this plan has"


class TestConversationalTurnsAreUntouched:
    def test_an_empty_plan_leaves_the_original_loop_behaviour_intact(self, loop, repo):
        # A question is not a build. Putting a task checklist in front of someone who asked one is
        # the same category error as the 48-minute round, pointed the other way.
        job, _ = loop(["Here is your answer."],
                      plan=ExecutionPlan(), contract_tools=())
        assert job.status == "done"
        assert not any("plan" in e for e in job.events)


class TestAPartialFileIsFinishedNotRewritten:
    """Observed on a real run: two full `write_file` calls to the same path inside one task. The
    model wrote a partial index.html, the substance check correctly rejected it as unfinished, and
    the forced call told it to write the file — so it regenerated the entire document from scratch,
    spending a second full generation reproducing work already sitting on disk.

    Forcing the right tool is not only about which tool advances the task; it is about which one
    does so without discarding what already exists.
    """

    def _task_and_controller(self, repo):
        plan = _build_plan()
        h = _Controller(plan)
        task = h.controller.current_task()
        h.controller.begin_task(task)
        h.job.tools_called.append("write_file")  # the requirement is already satisfied
        return h, task

    def test_a_missing_artifact_still_forces_a_write(self, repo):
        h, task = self._task_and_controller(repo)
        assert h.controller.forced_tool_for(task, {"write_file", "edit_file"}) == "write_file"

    def test_an_existing_but_unfinished_artifact_forces_an_edit(self, repo):
        # Head-only markup: real content, genuinely not a page yet. Rewriting it wholesale is the
        # expensive wrong answer.
        (repo / "index.html").write_text(
            "<!doctype html><html><head><style>" + "body{margin:0}" * 100 + "</style></head>",
            encoding="utf-8",
        )
        h, task = self._task_and_controller(repo)
        assert h.controller.forced_tool_for(task, {"write_file", "edit_file"}) == "edit_file"

    def test_it_falls_back_to_writing_when_editing_is_unavailable(self, repo):
        (repo / "index.html").write_text("<!doctype html><html><head></head>" + "x" * 500,
                                         encoding="utf-8")
        h, task = self._task_and_controller(repo)
        assert h.controller.forced_tool_for(task, {"write_file"}) == "write_file"

    def test_the_message_tells_it_not_to_rewrite_the_whole_file(self, repo):
        (repo / "index.html").write_text(
            "<!doctype html><html><head><style>" + "body{margin:0}" * 100 + "</style></head>",
            encoding="utf-8",
        )
        h, task = self._task_and_controller(repo)
        task.rounds_without_progress = MAX_ROUNDS_WITHOUT_PROGRESS
        h.controller.intervene(task, "no_progress", h.job.messages, h.job.message_rounds, 3,
                               {"write_file", "edit_file"})
        message = h.job.messages[-1]["content"]
        assert "edit_file" in message
        assert "Do NOT rewrite the whole file" in message

    def test_a_tiny_leftover_file_does_not_count_as_partially_written(self, repo):
        # An 11-byte "PLACEHOLDER" is not work to preserve — that must still force a real write.
        (repo / "index.html").write_text("PLACEHOLDER", encoding="utf-8")
        h, task = self._task_and_controller(repo)
        assert h.controller.forced_tool_for(task, {"write_file", "edit_file"}) == "write_file"


class TestRoundTelemetryIsActuallyWired:
    """The instrument is only worth anything if the loop reaches it on every exit a round has.

    Unit tests for the split live in tests/test_round_telemetry.py; these prove the wiring, which is
    the part that silently rots. A telemetry call sitting on the happy path only would leave the cut
    and stall rounds — the exact rounds the measurement exists to explain — as blank space in the
    dataset, and nothing would fail.
    """

    def test_every_round_of_a_normal_job_is_recorded(self, loop, tmp_path, monkeypatch):
        from backend.agents import round_telemetry as telemetry

        log = tmp_path / "rounds.jsonl"
        monkeypatch.setenv("CODEXA_TELEMETRY_PATH", str(log))
        job, _ = loop([
            [("write_file", {"path": "index.html", "content": _REAL_PAGE})],
            "Task one done.",
            [("screenshot", {"url": "http://localhost:8000"})],
            "All finished.",
        ])

        rows = telemetry.load(log, job_id=job.id)
        assert len(rows) >= 4, rows
        # Each row must carry the two halves of the comparison: what went in, what came out.
        assert all(row["context"]["total"] > 0 for row in rows)
        assert any(row["tool_calls"] for row in rows)
        # And it must be attributable to a task, or the per-task table is empty.
        assert any(row["task_id"] for row in rows)

    def test_a_round_cut_at_the_budget_is_recorded_as_a_cut(self, loop, tmp_path, monkeypatch):
        from backend.agents import jobs, round_telemetry as telemetry

        log = tmp_path / "rounds.jsonl"
        monkeypatch.setenv("CODEXA_TELEMETRY_PATH", str(log))
        monkeypatch.setattr(jobs, "_PLANNING_CHARS", 200)
        monkeypatch.setattr(jobs, "_AUTHORING_CHARS", 200)
        monkeypatch.setattr(jobs, "_EXECUTION_CHARS", 200)
        job, _ = loop([
            [("write_file", {"path": "index.html", "content": _REAL_PAGE})],
            "Task one done.",
            [("screenshot", {"url": "http://localhost:8000"})],
            "All finished.",
        ], thinking_per_round=500)

        rows = telemetry.load(log, job_id=job.id)
        cuts = [row for row in rows if row["outcome"] == "cut"]
        assert cuts, [row["outcome"] for row in rows]
        # A cut round is the one whose reasoning volume matters most; it must not be recorded as 0.
        assert all(row["reasoning_chars"] > 0 for row in cuts)

    def test_the_context_split_sees_the_execution_state_block(self, loop, tmp_path, monkeypatch):
        # The controller re-appends this every round. If the split misses it, the block's cost is
        # invisible and would be misattributed to the user's own request.
        from backend.agents import round_telemetry as telemetry

        log = tmp_path / "rounds.jsonl"
        monkeypatch.setenv("CODEXA_TELEMETRY_PATH", str(log))
        job, _ = loop([
            [("write_file", {"path": "index.html", "content": _REAL_PAGE})],
            "Task one done.",
            [("screenshot", {"url": "http://localhost:8000"})],
            "All finished.",
        ])

        rows = telemetry.load(log, job_id=job.id)
        assert any(row["context"]["task_context"] > 0 for row in rows)
