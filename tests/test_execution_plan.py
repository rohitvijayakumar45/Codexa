"""The execution plan, its derivation, and the two things that check it against reality.

What this defends
-----------------
A model asked to solve one large problem reasons about one large problem. A real build sat in a
single round for 48 minutes emitting 39,655 reasoning tokens — designing three complete, different
products and discarding two — and wrote nothing. Nothing in the loop noticed, because every guard
acted BETWEEN rounds and that round never ended.

The answer was structural: an explicit plan, exactly one active task, and a rule that the model
never decides its own work is finished. These tests pin the parts of that which are easy to
"simplify" back into the bug — most of all the three decisions that look wrong in isolation and are
not: a failed dependency still lets its dependent run, a plan of only failures is NOT complete, and
reasoning volume is not an input to whether progress happened.
"""

from __future__ import annotations

import json

import pytest

from backend.agents.plan import (
    MAX_ATTEMPTS_PER_TASK,
    MAX_PLAN_REVISIONS,
    ExecutionPlan,
    Task,
    TaskStatus,
    ValidationState,
    make_task,
    summarize_for_event,
    task_context_block,
)
from backend.agents.plan_builder import MAX_TASKS, build_plan, fallback_plan
from backend.agents.progress import RepoSnapshot, compare, is_thrashing, snapshot
from backend.agents.task import TaskIntent, generate_contract
from backend.agents.validators import infer_validators, validate_task


def _plan(*objectives: str, chain: bool = True) -> ExecutionPlan:
    tasks = []
    for i, obj in enumerate(objectives, 1):
        deps = [tasks[-1].id] if chain and tasks else []
        tasks.append(make_task(obj, index=i, depends_on=deps))
    return ExecutionPlan(objective="test plan", tasks=tasks)


# ── the state machine ─────────────────────────────────────────────────────────


class TestWhichTaskIsActive:
    def test_the_earliest_ready_pending_task_is_chosen(self):
        plan = _plan("first", "second", "third")
        assert plan.current().objective == "first"

    def test_an_already_started_task_outranks_a_pending_one(self):
        # A job resuming after a restart or a model rotation must continue the task it was on, not
        # jump ahead. The whole point of persisting the plan is that execution position survives the
        # process; picking by plan order alone would quietly skip work already underway.
        plan = _plan("first", "second")
        plan.begin(plan.tasks[1])
        assert plan.current().objective == "second"

    def test_nothing_is_active_once_every_task_is_terminal(self):
        plan = _plan("only")
        plan.complete(plan.tasks[0])
        assert plan.current() is None


class TestDependenciesExpressOrderNotImpossibility:
    """Deliberate and load-bearing: `is_ready` requires dependencies to be TERMINAL, not COMPLETED.

    The first implementation required COMPLETED, and it made every failure fatal to the entire
    remainder of the plan. Generated build plans are linear chains, so one task failing validation
    three times deadlocked all seven tasks behind it — and killed jobs that were still perfectly able
    to produce the artifact, because the very next task would have written the file itself. "Implement
    the core experience" follows "create the primary artifact" because the reverse order is silly,
    not because the second becomes unattemptable when the first goes wrong.
    """

    def test_a_failed_dependency_still_lets_its_dependent_run(self):
        plan = _plan("inspect", "build")
        plan.fail(plan.tasks[0], "could not list the directory")
        assert plan.current() is plan.tasks[1]

    def test_an_incomplete_dependency_does_block(self):
        plan = _plan("inspect", "build")
        plan.begin(plan.tasks[0])
        assert plan.current() is plan.tasks[0]  # not "build"

    def test_a_dependency_that_does_not_exist_blocks(self):
        # A malformed plan (a model inventing its own id graph is a reliable source of these) must
        # not silently run tasks whose prerequisites are unknowable.
        orphan = make_task("build", index=1, depends_on=["t99-does-not-exist"])
        plan = ExecutionPlan(objective="x", tasks=[orphan])
        assert plan.current() is None
        assert plan.is_stuck()

    def test_failing_a_task_does_not_cascade_to_its_dependents(self):
        plan = _plan("a", "b", "c")
        plan.fail(plan.tasks[0], "boom")
        assert [t.status for t in plan.tasks[1:]] == [TaskStatus.PENDING, TaskStatus.PENDING]


class TestWhenAPlanIsFinished:
    def test_an_empty_plan_is_never_complete(self):
        # An empty plan is the sentinel for "this turn needs no plan" (a conversational reply).
        # Reporting it complete would make every such turn look like a finished build.
        assert ExecutionPlan().is_complete() is False

    def test_outstanding_work_means_not_complete(self):
        plan = _plan("a", "b")
        plan.complete(plan.tasks[0])
        assert plan.is_complete() is False

    def test_a_plan_where_everything_failed_is_not_complete(self):
        # The silent-success bug in a new costume: every task reached a terminal state, so a naive
        # "nothing left to do" check reads as success while literally nothing was accomplished.
        plan = _plan("a", "b")
        for t in plan.tasks:
            plan.fail(t, "nope")
        assert plan.is_complete() is False

    def test_a_mix_of_completed_and_failed_is_complete(self):
        plan = _plan("a", "b")
        plan.complete(plan.tasks[0])
        plan.fail(plan.tasks[1], "gave up on the optional one")
        assert plan.is_complete() is True

    def test_stuck_is_distinct_from_finished(self):
        plan = _plan("a")
        plan.block(plan.tasks[0], "waiting on something that never arrives")
        assert plan.is_stuck() is True
        assert plan.is_complete() is False


class TestValidationIsTheOnlyRouteToCompleted:
    def test_a_passing_check_completes_the_task(self):
        plan = _plan("write it")
        assert plan.record_validation(plan.tasks[0], True, "index.html exists") is True
        assert plan.tasks[0].status is TaskStatus.COMPLETED
        assert plan.tasks[0].validation_state is ValidationState.PASSED

    def test_a_failing_check_leaves_the_task_active_and_burns_an_attempt(self):
        plan = _plan("write it")
        task = plan.tasks[0]
        assert plan.record_validation(task, False, "index.html is missing") is False
        assert task.status is not TaskStatus.COMPLETED
        assert task.attempts == 1
        assert task.validation_detail == "index.html is missing"

    def test_the_task_fails_once_its_attempts_are_spent(self):
        # The same approach failing a fourth time is not new information; the useful recovery is a
        # different task, which is what the controller does with a FAILED one.
        plan = _plan("write it")
        task = plan.tasks[0]
        for _ in range(MAX_ATTEMPTS_PER_TASK):
            plan.record_validation(task, False, "still missing")
        assert task.status is TaskStatus.FAILED

    def test_attempts_and_interventions_are_separate_budgets(self):
        """Rejected completions and forced-forward interventions are different failures with
        different right responses, and an earlier version shared one counter for both — which let
        three slow-but-legitimate rounds exhaust the validation budget of a task that had never once
        claimed to be done."""
        plan = _plan("write it")
        task = plan.tasks[0]
        task.interventions = 5
        plan.record_validation(task, False, "missing")
        assert task.attempts == 1
        assert task.interventions == 5


class TestRevisionIsBounded:
    def test_a_subtask_can_be_inserted_in_position(self):
        plan = _plan("a", "c")
        extra = make_task("b", index=99)
        assert plan.insert_after(plan.tasks[0].id, extra) is True
        assert [t.objective for t in plan.tasks] == ["a", "b", "c"]

    def test_insertion_stops_once_the_revision_budget_is_spent(self):
        # Unbounded revision is its own hang: rewriting the plan is indistinguishable from progress
        # to any round-counting guard, and it is what a model that would rather design than build
        # will do when told it may update the plan.
        plan = _plan("a")
        for i in range(MAX_PLAN_REVISIONS):
            assert plan.insert_after(plan.tasks[0].id, make_task(f"extra{i}", index=100 + i)) is True
        assert plan.insert_after(plan.tasks[0].id, make_task("one too many", index=200)) is False

    def test_a_duplicate_id_and_an_unknown_anchor_are_both_refused(self):
        plan = _plan("a")
        assert plan.insert_after(plan.tasks[0].id, plan.tasks[0]) is False
        assert plan.insert_after("t99-nope", make_task("b", index=2)) is False

    def test_dropping_a_task_records_it_rather_than_deleting_it(self):
        # Dependents must stay satisfiable, and "why did the plan skip that?" must stay answerable.
        plan = _plan("a", "b")
        assert plan.drop(plan.tasks[0].id, "already done by hand") is True
        assert plan.tasks[0].status is TaskStatus.COMPLETED
        assert "already done by hand" in plan.tasks[0].validation_detail
        assert len(plan.tasks) == 2


class TestTheCheckpointRoundTrip:
    def test_every_field_survives(self):
        plan = _plan("a", "b")
        task = plan.tasks[0]
        plan.begin(task)
        task.interventions = 2
        task.attempts = 1
        task.is_recovery = True
        task.note("wrote index.html")
        task.reasoning_chars = 1234
        plan.revisions = 3

        restored = ExecutionPlan.from_dict(json.loads(json.dumps(plan.to_dict())))
        rt = restored.tasks[0]
        assert rt.status is TaskStatus.IN_PROGRESS
        assert (rt.interventions, rt.attempts, rt.is_recovery) == (2, 1, True)
        assert rt.progress_notes == ["wrote index.html"]
        assert rt.reasoning_chars == 1234
        assert restored.revisions == 3
        assert [t.id for t in restored.tasks] == [t.id for t in plan.tasks]

    def test_a_checkpoint_written_by_an_older_build_still_loads(self):
        # Jobs are resumed from checkpoints on disk that predate any field added later. Raising here
        # would make an in-flight job unresumable after a deploy — precisely the situation the
        # checkpoint exists to survive.
        old = {"objective": "x", "tasks": [
            {"id": "t1-a", "objective": "a", "status": "PENDING", "unknown_future_field": 1},
        ]}
        restored = ExecutionPlan.from_dict(old)
        assert restored.tasks[0].objective == "a"
        assert restored.tasks[0].interventions == 0

    def test_from_dict_returns_none_for_no_plan(self):
        assert ExecutionPlan.from_dict(None) is None


class TestNotesAreBounded:
    def test_the_note_list_does_not_grow_without_limit(self):
        # Notes are re-sent to the model every round of the task; an unbounded list recreates, in
        # miniature, exactly the transcript growth this design exists to avoid.
        task = make_task("a", index=1)
        for i in range(50):
            task.note(f"note {i}")
        assert len(task.progress_notes) <= 12
        assert task.progress_notes[-1] == "note 49"

    def test_blank_notes_are_ignored(self):
        task = make_task("a", index=1)
        task.note("   ")
        assert task.progress_notes == []


# ── what the model is actually told ───────────────────────────────────────────


class TestTheTaskContextBlock:
    def _block(self) -> str:
        plan = _plan("inspect", "write index.html")
        task = plan.tasks[1]
        task.required_tools = ["write_file"]
        task.expected_artifacts = ["index.html"]
        task.completion_criteria = ["the file renders"]
        task.note("read the design guidance")
        plan.complete(plan.tasks[0])
        plan.begin(task)
        return task_context_block(plan, task)

    def test_it_names_the_one_current_task_and_its_requirements(self):
        block = self._block()
        assert "write index.html" in block
        assert "write_file" in block
        assert "index.html" in block
        assert "the file renders" in block

    def test_it_carries_outcomes_forward_rather_than_deliberation(self):
        # Continuity is preserved with facts — files written, checks run — not by replaying prior
        # reasoning. Re-feeding the reasoning is what invited a model to resume the very
        # deliberation it had just been cut out of.
        assert "read the design guidance" in self._block()

    def test_it_forbids_working_ahead(self):
        assert "ONLY on the current task" in self._block()

    def test_it_contains_no_chain_of_thought_field(self):
        # The product rule: execution state and progress are surfaced, reasoning is not.
        block = self._block().lower()
        assert "reasoning" not in block
        assert "chain of thought" not in block


class TestTheUiSnapshot:
    def test_it_matches_the_shape_the_frontend_consumes(self):
        plan = _plan("a", "b")
        plan.complete(plan.tasks[0])
        event = summarize_for_event(plan)
        assert set(event) == {"objective", "current_task_id", "tasks", "completed", "total"}
        assert (event["completed"], event["total"]) == (1, 2)
        assert event["current_task_id"] == plan.tasks[1].id
        assert set(event["tasks"][0]) == {
            "id", "objective", "status", "attempts", "validation_state",
            "validation_detail", "expected_artifacts", "last_progress",
        }

    def test_it_leaks_no_reasoning(self):
        plan = _plan("a")
        plan.tasks[0].reasoning_chars = 99999
        assert "reasoning" not in json.dumps(summarize_for_event(plan))


# ── deriving a plan ───────────────────────────────────────────────────────────


class TestTheDeterministicPlan:
    def test_a_single_html_build_gets_a_build_shaped_plan(self):
        request = "Build a polished single HTML page with animations and a command palette"
        plan = fallback_plan(request, generate_contract(request))
        assert 3 <= len(plan.tasks) <= MAX_TASKS
        assert any("index.html" in t.expected_artifacts for t in plan.tasks)
        assert any("screenshot" in t.required_tools for t in plan.tasks)
        assert any("write_file" in t.required_tools for t in plan.tasks)

    def test_an_explanation_does_not_get_a_build_plan(self):
        # Proportionality. An 8-task build checklist in front of someone who asked a question is the
        # same category error as the 48-minute round, pointed the other way.
        request = "explain how python decorators work"
        plan = fallback_plan(request, generate_contract(request))
        assert len(plan.tasks) <= 3
        assert not any(t.expected_artifacts for t in plan.tasks)

    def test_a_greeting_produces_no_plan_at_all(self):
        plan = fallback_plan("hi", generate_contract("hi"))
        assert plan.tasks == []

    def test_every_generated_task_can_actually_be_checked(self):
        # A plan whose tasks carry no validators is a checklist the model ticks off itself, which is
        # exactly what this system replaces.
        request = "Build a dashboard page"
        plan = fallback_plan(request, generate_contract(request))
        known = {"artifacts_exist", "tools_called", "command_succeeded", "no_build_errors",
                 "screenshot_taken", "files_changed", "design_evidence", "renders_cleanly"}
        for task in plan.tasks:
            assert set(task.validators) <= known, task.validators
        assert any(t.validators for t in plan.tasks)


class _FakeLLM:
    """Stands in for the proposal call. `raw` is returned verbatim, or raised if it is an exception."""

    def __init__(self, raw):
        self.raw = raw
        self.calls = 0

    def complete(self, messages, **kwargs):
        self.calls += 1
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw


def _proposal(tasks) -> str:
    return json.dumps({"objective": "Build the thing", "tasks": tasks})


_BUILD_REQUEST = "Build a polished single HTML page"


def _built(raw) -> ExecutionPlan:
    return build_plan(_BUILD_REQUEST, generate_contract(_BUILD_REQUEST),
                      llm=_FakeLLM(raw), model="fake-model", repository="demo")


class TestTheProposalPath:
    _FOUR = [
        {"objective": "Inspect the repo", "required_tools": ["list_directory"],
         "expected_artifacts": [], "completion_criteria": [], "depends_on_previous": False},
        {"objective": "Write index.html", "required_tools": ["write_file"],
         "expected_artifacts": ["index.html"], "completion_criteria": [], "depends_on_previous": True},
        {"objective": "Look at it", "required_tools": ["screenshot"],
         "expected_artifacts": [], "completion_criteria": [], "depends_on_previous": True},
        {"objective": "Refine", "required_tools": ["edit_file"],
         "expected_artifacts": ["index.html"], "completion_criteria": [], "depends_on_previous": True},
    ]

    def test_a_clean_proposal_is_used(self):
        plan = _built(_proposal(self._FOUR))
        assert [t.objective for t in plan.tasks][:2] == ["Inspect the repo", "Write index.html"]

    def test_json_fenced_in_a_code_block_parses(self):
        plan = _built(f"```json\n{_proposal(self._FOUR)}\n```")
        assert len(plan.tasks) == 4

    def test_prose_around_the_json_parses(self):
        plan = _built(f"Here is my plan!\n{_proposal(self._FOUR)}\nHope that helps.")
        assert len(plan.tasks) == 4

    def test_depends_on_previous_becomes_a_real_id_chain(self):
        # A model inventing its own id graph is a reliable source of unsatisfiable dependencies, and
        # therefore of a permanently stuck plan. It states adjacency; Codexa assigns the ids.
        plan = _built(_proposal(self._FOUR))
        assert plan.tasks[0].depends_on == []
        assert plan.tasks[1].depends_on == [plan.tasks[0].id]
        for task in plan.tasks:
            for dep in task.depends_on:
                assert plan.get(dep) is not None

    def test_an_invented_tool_name_is_dropped(self):
        # A plan requiring a tool that does not exist can never be satisfied — the task would fail
        # validation forever through no fault of the model.
        tasks = [dict(t) for t in self._FOUR]
        tasks[1]["required_tools"] = ["write_file", "teleport_file"]
        plan = _built(_proposal(tasks))
        assert "teleport_file" not in plan.tasks[1].required_tools
        assert "write_file" in plan.tasks[1].required_tools

    def test_artifact_paths_are_normalised_and_escapes_rejected(self):
        tasks = [dict(t) for t in self._FOUR]
        tasks[1]["expected_artifacts"] = ["/index.html", "../../etc/passwd"]
        plan = _built(_proposal(tasks))
        assert plan.tasks[1].expected_artifacts == ["index.html"]

    def test_an_oversized_proposal_is_clamped(self):
        many = [dict(self._FOUR[1], objective=f"step {i}") for i in range(40)]
        assert len(_built(_proposal(many)).tasks) == MAX_TASKS

    def test_a_one_task_build_proposal_is_rejected(self):
        # One task is "solve the entire problem" wearing a plan's clothes, and reproduces the
        # 48-minute round exactly.
        plan = _built(_proposal([self._FOUR[1]]))
        assert len(plan.tasks) > 1


class TestPlanningCanNeverFailAJob:
    """Every one of these must fall back to the deterministic plan. Planning is a convenience; a job
    that dies because its planner had a bad day is strictly worse than one that runs on a plan
    written by hand."""

    @pytest.mark.parametrize("raw", [
        RuntimeError("provider exploded"),
        None,
        "",
        "I'd rather not produce JSON, sorry.",
        '{"objective": "x", "tasks": [',
        json.dumps({"objective": "x", "tasks": []}),
        json.dumps({"nope": True}),
        12345,
    ], ids=["raises", "none", "empty", "prose", "truncated-json", "no-tasks", "wrong-shape", "not-a-string"])
    def test_it_falls_back_instead_of_propagating(self, raw):
        plan = _built(raw)
        assert plan.tasks, "must fall back to the deterministic plan, not return nothing"
        assert any("index.html" in t.expected_artifacts for t in plan.tasks)

    def test_no_llm_at_all_is_fine(self):
        plan = build_plan(_BUILD_REQUEST, generate_contract(_BUILD_REQUEST))
        assert plan.tasks

    def test_the_proposal_is_asked_for_exactly_once(self):
        # Planning repeatedly is itself a way to spend a run without building anything.
        llm = _FakeLLM(_proposal(TestTheProposalPath._FOUR))
        build_plan(_BUILD_REQUEST, generate_contract(_BUILD_REQUEST),
                   llm=llm, model="fake-model", repository="demo")
        assert llm.calls == 1


# ── checking against reality ──────────────────────────────────────────────────


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Point both reality-checking modules at a real temporary directory.

    Patched in each module's own namespace because both do `from backend.files.api import
    repo_root`, so the name they call is their own. Nothing here may touch the developer's actual
    repositories — a validator test that passes because of a file someone happened to have on disk
    is worse than no test.
    """
    monkeypatch.setattr("backend.agents.validators.repo_root", lambda _r: tmp_path)
    monkeypatch.setattr("backend.agents.progress.repo_root", lambda _r: tmp_path)
    return tmp_path


def _task(**kw) -> Task:
    task = make_task(kw.pop("objective", "do the thing"), index=1)
    for key, value in kw.items():
        setattr(task, key, value)
    return task


class TestArtifactsAreCheckedOnDisk:
    def test_an_existing_substantive_file_passes(self, repo):
        # Deliberately a plausible page rather than a 28-byte stub. The stub this used to write is
        # now correctly rejected — see TestAPlaceholderIsNotAnArtifact for why a file that small
        # cannot be an artifact.
        (repo / "index.html").write_text(
            "<!doctype html><html><head><title>Archive</title></head><body>"
            + "<p>Real content.</p>" * 40 + "</body></html>",
            encoding="utf-8",
        )
        result = validate_task(
            _task(expected_artifacts=["index.html"], validators=["artifacts_exist"]),
            repository="demo", tools_called_in_task=[],
        )
        assert result.passed, result.detail

    def test_a_missing_file_fails_and_says_which(self, repo):
        result = validate_task(
            _task(expected_artifacts=["index.html"], validators=["artifacts_exist"]),
            repository="demo", tools_called_in_task=[],
        )
        assert not result.passed
        assert "index.html" in result.detail

    def test_an_empty_file_does_not_count_as_built(self, repo):
        # A zero-byte index.html is what a failed or interrupted write leaves behind. Accepting it
        # would let a task validate on the existence of its own failure.
        (repo / "index.html").write_text("", encoding="utf-8")
        result = validate_task(
            _task(expected_artifacts=["index.html"], validators=["artifacts_exist"]),
            repository="demo", tools_called_in_task=[],
        )
        assert not result.passed

    def test_a_glob_passes_when_something_matches(self, repo):
        (repo / "src").mkdir()
        (repo / "src" / "App.tsx").write_text("export default 1", encoding="utf-8")
        result = validate_task(
            _task(expected_artifacts=["src/**/*.tsx"], validators=["artifacts_exist"]),
            repository="demo", tools_called_in_task=[],
        )
        assert result.passed, result.detail

    def test_a_path_escaping_the_repository_is_refused(self, repo):
        # expected_artifacts can come from a model-proposed plan; a task must not be able to
        # validate itself against a file outside the repository it is working in.
        result = validate_task(
            _task(expected_artifacts=["../outside.txt"], validators=["artifacts_exist"]),
            repository="demo", tools_called_in_task=[],
        )
        assert not result.passed


class TestTheOtherValidators:
    def test_required_tools_must_actually_have_been_called(self, repo):
        task = _task(required_tools=["write_file"], validators=["tools_called"])
        assert not validate_task(task, repository="demo", tools_called_in_task=["read_file"]).passed
        assert validate_task(task, repository="demo", tools_called_in_task=["write_file"]).passed

    @pytest.mark.parametrize("delegator", ["delegate_task", "delegate_build"])
    def test_delegation_satisfies_the_writes_it_hides(self, repo, delegator):
        # A delegated worker executes write_file in its own sub-loop; only the single delegate call
        # ever reaches the parent's list. Without this allowance, delegating — which the tooling
        # actively encourages for exactly these multi-file builds — would look identical to never
        # having written anything.
        task = _task(required_tools=["write_file"], validators=["tools_called"])
        assert validate_task(task, repository="demo", tools_called_in_task=[delegator]).passed

    def test_command_success_reads_the_most_recent_exit_code(self, repo):
        task = _task(validators=["command_succeeded"])
        assert validate_task(task, repository="demo", tools_called_in_task=[], exit_codes=[1, 0]).passed
        assert not validate_task(task, repository="demo", tools_called_in_task=[], exit_codes=[0, 1]).passed
        assert not validate_task(task, repository="demo", tools_called_in_task=[], exit_codes=[]).passed

    def test_screenshot_must_have_been_taken(self, repo):
        task = _task(validators=["screenshot_taken"])
        assert not validate_task(task, repository="demo", tools_called_in_task=["write_file"]).passed
        assert validate_task(task, repository="demo", tools_called_in_task=["screenshot"]).passed


class TestValidationFailsSafely:
    def test_a_task_with_nothing_to_check_passes_but_says_so(self, repo):
        # Legitimate for a genuinely non-artifact task ("commit to a direction"). It must never read
        # back as a verified pass, or the distinction stops meaning anything.
        result = validate_task(_task(validators=[]), repository="demo", tools_called_in_task=[])
        assert result.passed
        assert "no mechanical check" in result.detail.lower()

    def test_an_unknown_validator_fails_closed(self, repo):
        result = validate_task(
            _task(validators=["definitely_not_a_validator"]),
            repository="demo", tools_called_in_task=[],
        )
        assert not result.passed
        assert "definitely_not_a_validator" in result.detail

    def test_a_validator_that_raises_is_reported_not_propagated(self, repo, monkeypatch):
        # Validation runs inside the job thread. An exception escaping here would take down a job
        # over a diagnostic — worse than any wrong verdict it could return.
        def boom(_ctx):
            raise RuntimeError("disk on fire")

        monkeypatch.setitem(
            __import__("backend.agents.validators", fromlist=["_VALIDATORS"])._VALIDATORS,
            "artifacts_exist", boom,
        )
        result = validate_task(
            _task(expected_artifacts=["x.html"], validators=["artifacts_exist"]),
            repository="demo", tools_called_in_task=[],
        )
        assert not result.passed
        assert "disk on fire" in result.detail

    def test_all_listed_validators_must_pass_not_merely_one(self, repo):
        (repo / "index.html").write_text("real", encoding="utf-8")
        result = validate_task(
            _task(expected_artifacts=["index.html"], required_tools=["screenshot"],
                  validators=["artifacts_exist", "tools_called"]),
            repository="demo", tools_called_in_task=["write_file"],
        )
        assert not result.passed


class TestInferringValidators:
    def test_artifacts_and_tools_produce_their_checks(self):
        task = _task(expected_artifacts=["index.html"], required_tools=["write_file"])
        assert set(infer_validators(task)) >= {"artifacts_exist", "tools_called"}

    def test_a_task_with_nothing_declared_gets_nothing(self):
        assert infer_validators(_task()) == []

    def test_it_never_invents_a_validator_name(self):
        known = {"artifacts_exist", "tools_called", "command_succeeded", "no_build_errors",
                 "screenshot_taken", "files_changed", "design_evidence", "renders_cleanly"}
        task = _task(expected_artifacts=["a.html"], required_tools=["screenshot", "write_file"])
        assert set(infer_validators(task)) <= known


# ── progress, as distinct from activity ───────────────────────────────────────


def _snap(**files) -> RepoSnapshot:
    return RepoSnapshot(files={name: (len(body), i) for i, (name, body) in enumerate(files.items())},
                        taken_at=0.0)


class TestWhatCountsAsProgress:
    def test_a_created_file_counts(self):
        signal = compare(_snap(), _snap(**{"index.html": "hi"}), tools_ran=["write_file"])
        assert signal.made_progress
        assert signal.created == ["index.html"]

    def test_a_modified_file_counts(self):
        before = RepoSnapshot(files={"a.py": (10, 1)}, taken_at=0.0)
        after = RepoSnapshot(files={"a.py": (99, 2)}, taken_at=1.0)
        signal = compare(before, after, tools_ran=["edit_file"])
        assert signal.made_progress
        assert signal.modified == ["a.py"]

    def test_a_deleted_file_counts(self):
        signal = compare(_snap(**{"old.py": "x"}), _snap(), tools_ran=["delete_file"])
        assert signal.made_progress
        assert signal.deleted == ["old.py"]

    def test_an_informative_tool_counts_even_with_no_disk_change(self):
        # Taking a screenshot and reading a file are what legitimate work looks like too; a round
        # spent looking at the result of the last one is not a stalled round.
        assert compare(_snap(), _snap(), tools_ran=["screenshot"]).made_progress

    def test_a_round_that_ran_no_tools_is_not_progress_however_much_it_generated(self):
        """The asymmetry this whole system corrects. Generation was being read as work: a model that
        produced 39,655 reasoning tokens across 48 minutes while writing zero files was, to every
        guard that existed, indistinguishable from one doing its job.

        Note there is deliberately no reasoning parameter on `compare` at all — the volume a round
        generated cannot influence this verdict even by accident."""
        assert compare(_snap(), _snap(), tools_ran=[]).made_progress is False

    def test_the_description_is_short_enough_to_show_a_user(self):
        signal = compare(_snap(), _snap(**{"index.html": "x" * 500}), tools_ran=["write_file"])
        assert 0 < len(signal.describe()) < 160


class TestThrashingDetection:
    """`made_progress` cannot catch this and structurally never could. After a cut round was retried
    with tool_choice="required", the model called `screenshot` against a URL serving nothing and
    `list_directory` on an empty repository, then resumed planning. Every one of those rounds passes
    an activity check. The tell is the shape across rounds, not any single round."""

    def _quiet(self, *tools) -> object:
        return compare(_snap(), _snap(), tools_ran=list(tools))

    def test_a_repeated_quiet_vocabulary_is_thrashing(self):
        window = [self._quiet("screenshot", "list_directory")] * 3
        assert is_thrashing(window) is True

    def test_a_new_tool_appearing_is_not_thrashing(self):
        window = [self._quiet("screenshot"), self._quiet("screenshot"), self._quiet("write_file")]
        assert is_thrashing(window) is False

    def test_a_file_change_anywhere_in_the_window_is_not_thrashing(self):
        window = [
            self._quiet("screenshot"),
            compare(_snap(), _snap(**{"index.html": "x"}), tools_ran=["write_file"]),
            self._quiet("screenshot"),
        ]
        assert is_thrashing(window) is False

    def test_it_needs_a_full_window_before_firing(self):
        # Two identical quiet rounds are ordinary (read a file, then read another). Three with
        # nothing new is a pattern.
        assert is_thrashing([self._quiet("screenshot")] * 2) is False


class TestSnapshotting:
    def test_it_never_raises_on_a_repository_that_is_not_loaded(self):
        # Every caller is inside a running job thread. A diagnostic that can kill the job it is
        # diagnosing is worse than no diagnostic.
        assert snapshot("this-repository-does-not-exist").is_empty

    def test_it_sees_real_files_and_skips_the_noisy_directories(self, repo):
        (repo / "index.html").write_text("hello", encoding="utf-8")
        for junk in (".git", "node_modules", "__pycache__"):
            (repo / junk).mkdir()
            (repo / junk / "noise.txt").write_text("ignore me", encoding="utf-8")

        files = snapshot("demo").files
        assert "index.html" in files
        assert not any(d in path for path in files for d in (".git", "node_modules", "__pycache__"))

    def test_paths_are_posix_style_regardless_of_platform(self, repo):
        # Windows is the development platform; os.walk yields backslashes there. Snapshot keys are
        # compared against model-supplied artifact paths, which are always forward-slashed.
        (repo / "src").mkdir()
        (repo / "src" / "app.py").write_text("x", encoding="utf-8")
        assert "src/app.py" in snapshot("demo").files


class TestAPlaceholderIsNotAnArtifact:
    """A real run wrote a genuine 26,343-byte index.html, thrashed for three rounds, then overwrote
    it with the literal 11-byte text "PLACEHOLDER" — and the task passed validation, because the
    only question being asked was "is the file non-empty".

    That is the failure this whole system exists to prevent, reproduced by the system itself: a
    check a token gesture can satisfy is the model's own "Done." with an extra step. These pin the
    substance rule. They must not be relaxed into a size check — the point is that specific shapes
    of non-work are recognised, not that small files are banned.
    """

    def _check(self, repo, name="index.html"):
        return validate_task(
            _task(expected_artifacts=[name], validators=["artifacts_exist"]),
            repository="demo", tools_called_in_task=[],
        )

    def test_a_file_containing_only_the_word_placeholder_fails(self, repo):
        (repo / "index.html").write_text("PLACEHOLDER", encoding="utf-8")
        result = self._check(repo)
        assert not result.passed
        assert "placeholder" in result.detail.lower()

    @pytest.mark.parametrize("body", ["TODO", "tbd", "Coming soon", "WIP", "<!-- TODO -->", "..."])
    def test_other_stand_ins_for_work_fail_too(self, repo, body):
        (repo / "index.html").write_text(body, encoding="utf-8")
        assert not self._check(repo).passed

    def test_head_only_markup_fails_because_the_page_was_never_written(self, repo):
        # The shape a model produces when it writes its stylesheet, runs out of room, and intends to
        # "fill in the rest next round". Large, plausible-looking, and not a page.
        (repo / "index.html").write_text(
            "<!DOCTYPE html><html><head><title>Archive</title><style>"
            + "body{margin:0}" * 900 + "</style></head>",
            encoding="utf-8",
        )
        result = self._check(repo)
        assert not result.passed
        assert "body" in result.detail.lower()

    def test_a_real_page_still_passes(self, repo):
        (repo / "index.html").write_text(
            "<!DOCTYPE html><html><head><title>Archive</title></head>"
            "<body><main><h1>The Meridian Shelf</h1>" + "<p>Real content.</p>" * 40
            + "</main></body></html>",
            encoding="utf-8",
        )
        assert self._check(repo).passed

    def test_the_word_placeholder_inside_a_real_page_is_fine(self, repo):
        # `<input placeholder="...">` and a `.placeholder` CSS class are completely ordinary. The
        # rule matches the WHOLE file, never a substring — a substring match would fail real pages.
        (repo / "index.html").write_text(
            "<!DOCTYPE html><html><head></head><body>"
            '<input placeholder="Search the archive">' + "<p>Real.</p>" * 40
            + "</body></html>",
            encoding="utf-8",
        )
        assert self._check(repo).passed

    def test_a_small_non_markup_file_is_not_punished_for_being_small(self, repo):
        # A one-line config is a legitimate artifact. Size alone earns a closer look, not rejection.
        (repo / "app.config").write_text("mode=production\n", encoding="utf-8")
        assert self._check(repo, "app.config").passed
