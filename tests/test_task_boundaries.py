"""A task must be able to end on the round that finished it.

The leak this closes, traced from two real runs rather than inferred:

`try_advance` refuses to complete a task with no validators — deliberately, so "nothing to verify"
cannot mean "complete the instant it starts". But the generated plan contained a task with no
required tools and therefore no validators: "Commit to one direction and state it in a few
sentences". That task could only complete through `on_completion_claim`, which runs ONLY on a round
with no tool calls. So the model had to keep generating prose in order to end the task — and it
filled that prose with the design of every later task.

Measured, same plan, same run:

    task 1 (tools_called validator)   1 round      69 reasoning chars
    task 2 (no validator)             2 rounds  2,002 / 5,806 reasoning chars

and on a third run roughly 18,000 characters, in which the model wrote that index.html "is task 3"
and then designed task 3's CSS architecture, JavaScript architecture, fourteen archive records,
timeline behaviour, FLIP implementation and mobile layout anyway.

The fix is structural, not a prompt: every generated task carries a mechanical completion criterion,
so finishing the work is what ends the round.
"""

from __future__ import annotations

import pytest

from backend.agents.plan import ExecutionPlan, TaskStatus, make_task, task_context_block
from backend.agents.plan_builder import fallback_plan
from backend.agents.task import generate_contract

BUILD = "Build a single self-contained HTML archive with scroll animations and a screenshot"
FULLSTACK = ("Build a full-stack research workspace with a backend, database, API layer and "
             "persistence, and a screenshot of the result")


def plan_for(request: str) -> ExecutionPlan:
    return fallback_plan(request, generate_contract(request))


class TestEveryTaskCanEndOnItsOwnRound:
    """The invariant. A task with no mechanical criterion cannot complete on the round that did its
    work — it has to be talked to completion, and that talk is where future tasks get designed."""

    @pytest.mark.parametrize("request_text", [BUILD, FULLSTACK])
    def test_no_generated_task_lacks_a_completion_criterion(self, request_text):
        starved = [t.objective for t in plan_for(request_text).tasks if not t.validators]
        assert starved == [], f"these tasks can only be ended by prose: {starved}"

    @pytest.mark.parametrize("request_text", [BUILD, FULLSTACK])
    def test_the_commit_task_completes_by_committing(self, request_text):
        # commit_direction succeeding IS the completion of a commit task. Making that the criterion
        # is what lets the round end the moment the decision is recorded.
        commit = next(t for t in plan_for(request_text).tasks
                      if "commit" in t.objective.lower())
        assert "commit_direction" in commit.required_tools
        assert "tools_called" in commit.validators

    def test_a_task_with_a_criterion_advances_on_its_tool_round(self, tmp_path, monkeypatch):
        from backend.agents.controller import ExecutionController
        from backend.agents.jobs import Job

        for module in ("backend.agents.validators", "backend.agents.progress",
                       "backend.agents.controller"):
            monkeypatch.setattr(f"{module}.repo_root", lambda _r, _p=tmp_path: _p)

        commit = make_task("Commit to one direction", index=1,
                           required_tools=["commit_direction"], validators=["tools_called"])
        build = make_task("Write the page", index=2, depends_on=[commit.id],
                          required_tools=["write_file"], validators=["tools_called"])
        plan = ExecutionPlan(objective="x", tasks=[commit, build])
        job = Job(id="j", repository="demo", model="m", plan=plan.to_dict())
        controller = ExecutionController(job, plan, repository="demo", emit=lambda e: None)

        controller.begin_task(commit)
        job.tools_called.append("commit_direction")

        assert controller.try_advance(commit) is True, (
            "the task must end on the round that satisfied it, not require a prose round")
        assert commit.status is TaskStatus.COMPLETED
        assert controller.current_task().objective == "Write the page"


class TestFutureWorkIsNamedNotSpecified:
    """A model given the whole plan solves the whole plan. Later tasks are listed so the model knows
    they are covered, and explicitly fenced off — not rendered in full every round."""

    def _context(self):
        plan = plan_for(BUILD)
        plan.complete(plan.tasks[0])
        task = plan.current()
        plan.begin(task)
        return plan, task, task_context_block(plan, task)

    def test_the_current_task_is_given_in_full(self):
        _plan, task, block = self._context()
        assert f"CURRENT TASK: {task.objective}" in block
        for tool in task.required_tools:
            assert tool in block

    def test_later_tasks_are_named_and_fenced_off(self):
        _plan, _task, block = self._context()
        assert "LATER" in block
        assert "Do NOT design, plan or write any part of these now" in block

    def test_later_tasks_do_not_bring_their_own_requirements(self):
        # The invitation is the detail, not the name. A later task's tools and artifacts must not
        # appear — that is a specification the model can start satisfying early.
        plan, task, block = self._context()
        later = [t for t in plan.tasks if not t.is_terminal and t is not task]
        assert later
        after = block[block.index("LATER"):]
        for t in later:
            for artifact in t.expected_artifacts:
                assert f"MUST EXIST WHEN DONE: {artifact}" not in after

    def test_completed_work_is_marked_do_not_redo(self):
        _plan, _task, block = self._context()
        assert "ALREADY DONE (do not redo)" in block

    def test_the_block_stays_small_enough_to_resend_every_round(self):
        _plan, _task, block = self._context()
        assert len(block) < 3000, f"{len(block)} chars is too much to re-send each round"

    def test_it_still_carries_no_chain_of_thought(self):
        _plan, _task, block = self._context()
        assert "reasoning" not in block.lower()


class TestAnAllFailedPlanReportsItselfHonestly:
    """is_complete() is False for a plan where nothing succeeded (correct), and is_stuck() is also
    False (nothing is left to block). Indexing `remaining[0]` in that state raised IndexError out of
    the round loop and killed the job with error_reason=None — neither auto-continued nor eligible
    for Continue, so it was unrecoverable."""

    def test_it_does_not_crash(self):
        from backend.agents.controller import ExecutionController
        from backend.agents.jobs import Job

        plan = ExecutionPlan(objective="x", tasks=[make_task("a", index=1), make_task("b", index=2)])
        for task in plan.tasks:
            plan.fail(task, "nope")
        controller = ExecutionController(Job(id="j", repository="r", model="m"), plan,
                                         repository="r", emit=lambda e: None)
        reason = controller.blocking_reason()
        assert reason and "failed" in reason
