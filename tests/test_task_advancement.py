"""A task ends when its checks pass, not when the model happens to stop calling tools.

Completion used to be evaluated in exactly one place: a round that returned NO tool calls, read as
a claim of "I am finished". That quietly made the model the trigger for its own task boundaries. A
task whose validators had already passed stayed IN_PROGRESS for as long as the model kept calling
tools — and a model with no remaining useful action does not fall silent, it invents one.

Measured on a live run. Task one was "inspect the repository and establish the conventions"; its
check was "list_directory was called"; that passed on round one. Fifteen rounds later it was still
the active task, with nine list_directory calls out of nineteen tools, a screenshot of a repository
that contained no page, and a controller intervention — every bit of it work the model manufactured
because nothing had told it the task was over.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.agents.controller import ExecutionController
from backend.agents.jobs import Job
from backend.agents.plan import ExecutionPlan, TaskStatus, make_task


def _plan() -> ExecutionPlan:
    inspect = make_task("Inspect the repository", index=1,
                        required_tools=["list_directory"], validators=["tools_called"])
    write = make_task("Write the page", index=2, depends_on=[inspect.id],
                      required_tools=["write_file"], expected_artifacts=["index.html"],
                      validators=["artifacts_exist", "tools_called"])
    return ExecutionPlan(objective="Build it", tasks=[inspect, write], committed=True)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    for module in ("backend.agents.validators", "backend.agents.progress",
                   "backend.agents.controller"):
        monkeypatch.setattr(f"{module}.repo_root", lambda _r, _p=tmp_path: _p)
    plan = _plan()
    job = Job(id="advance-job", repository="demo", model="m",
              messages=[], message_rounds=[], contract={"intent": "CREATE_ARTIFACT"},
              active_tool_groups=["code"], working_repo="demo", plan=plan.to_dict())
    events: list[dict] = []
    controller = ExecutionController(job, plan, repository="demo", emit=events.append)
    return controller, job, plan, events, tmp_path


class TestATaskEndsWhenItsChecksPass:
    def test_a_satisfied_task_advances_without_the_model_saying_anything(self, harness):
        controller, job, plan, _events, _tmp = harness
        task = controller.current_task()
        controller.begin_task(task)
        job.tools_called.append("list_directory")   # the check is now satisfied

        assert controller.try_advance(task) is True
        assert task.status is TaskStatus.COMPLETED
        assert controller.current_task().objective == "Write the page"

    def test_an_unsatisfied_task_is_left_alone(self, harness):
        controller, _job, _plan, _events, _tmp = harness
        task = controller.current_task()
        controller.begin_task(task)
        # No list_directory yet.
        assert controller.try_advance(task) is False
        assert task.status is TaskStatus.IN_PROGRESS

    def test_a_task_that_has_done_nothing_yet_never_auto_completes(self, harness):
        # "Nothing to verify" must not become "complete the instant it starts".
        controller, job, plan, _events, _tmp = harness
        bare = make_task("Decide a direction", index=9)  # no validators at all
        plan.tasks.insert(0, bare)
        controller.begin_task(bare)
        assert controller.try_advance(bare) is False

    def test_the_advance_is_reported_as_automatic(self, harness):
        controller, job, _plan, events, _tmp = harness
        task = controller.current_task()
        controller.begin_task(task)
        job.tools_called.append("list_directory")
        controller.try_advance(task)

        validations = [e["tool_call"]["args"] for e in events
                       if e.get("tool_call", {}).get("name") == "_task_validation"]
        assert validations and validations[-1]["advanced"] == "automatically"

    def test_an_artifact_task_advances_only_once_the_file_is_real(self, harness):
        controller, job, plan, _events, tmp = harness
        plan.complete(plan.tasks[0])
        write = controller.current_task()
        controller.begin_task(write)
        job.tools_called.append("write_file")

        # A placeholder must not advance it — artifacts_exist applies its substance rule.
        (tmp / "index.html").write_text("PLACEHOLDER", encoding="utf-8")
        assert controller.try_advance(write) is False

        (tmp / "index.html").write_text(
            "<!doctype html><html><head><title>t</title></head><body><main>"
            + "<p>Real content.</p>" * 30 + "</main></body></html>", encoding="utf-8")
        assert controller.try_advance(write) is True

    def test_a_completed_task_is_not_advanced_twice(self, harness):
        controller, job, _plan, _events, _tmp = harness
        task = controller.current_task()
        controller.begin_task(task)
        job.tools_called.append("list_directory")
        assert controller.try_advance(task) is True
        assert controller.try_advance(task) is False


class TestTheLoopAdvancesAfterAToolRound:
    def test_a_tool_calling_round_can_finish_its_task(self, harness, monkeypatch):
        """The specific regression: the loop only asked about completion on a round with NO tool
        calls, so a model that kept acting could never finish anything."""
        controller, job, plan, _events, _tmp = harness
        task = controller.current_task()
        controller.begin_task(task)
        job.tools_called.append("list_directory")

        # Simulate what the loop does after executing a round's tool calls.
        with patch.object(controller, "snapshot_repo", side_effect=controller.snapshot_repo):
            controller.try_advance(task)

        assert task.status is TaskStatus.COMPLETED, (
            "a task must be able to complete on a round where tools were called")
