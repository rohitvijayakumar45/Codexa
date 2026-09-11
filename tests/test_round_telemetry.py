"""Tests for per-round context accounting.

The point of these is that the instrument must be trustworthy before any conclusion is drawn from
it. A split that silently attributes the design brief to "system", or counts a write_file body
twice, would produce a clean-looking dataset that answers the wrong question.
"""

from __future__ import annotations

import json

import pytest

from backend.agents import round_telemetry as telemetry


def _system(text: str) -> dict:
    return {"role": "system", "content": text}


def test_split_separates_the_three_things_inside_one_system_message():
    # chat/api.py appends build_task_prompt, then jobs.py appends the design brief, all into the
    # same system message. Folding them together hides the brief, whose size is itself a suspect.
    system = "You are Codexa.\n\nTASK MODE: create\nREQUIRED TOOLS: write_file\n\nDESIGN INTENT\ncharacter: calm"
    split = telemetry.split_context([_system(system)])

    assert split.system_base > 0
    assert split.task_prompt > 0
    assert split.design_brief > 0
    # Partition, not overlap: the three pieces are the whole message and nothing more.
    assert split.total == split.system_base + split.task_prompt + split.design_brief


def test_system_message_as_content_blocks_is_still_split():
    # The frontend sends system content as [{"type": "text", "text": ..., "cache_control": ...}].
    # A previous bug in this exact shape made the design brief invisible for every UI-started job.
    blocks = [{"type": "text", "text": "You are Codexa.\n\nDESIGN INTENT\nmotion: considered",
               "cache_control": {"type": "ephemeral"}}]
    split = telemetry.split_context([{"role": "system", "content": blocks}])

    assert split.design_brief > 0
    assert split.system_base > 0


def test_tool_call_arguments_are_counted_separately_from_prose():
    # A write_file body arrives as tool_call arguments and is by far the largest thing a build puts
    # into its own transcript. Attributing it to "assistant prose" would blame the wrong bucket.
    body = "x" * 4000
    messages = [
        {"role": "assistant", "content": "Writing the page.", "tool_calls": [
            {"id": "1", "type": "function",
             "function": {"name": "write_file", "arguments": json.dumps({"content": body})}},
        ]},
    ]
    split = telemetry.split_context(messages)

    assert split.assistant_tool_args > split.assistant_text
    assert split.total == split.assistant_text + split.assistant_tool_args


def test_execution_state_block_is_not_counted_as_a_user_turn():
    # The controller re-appends this every round. Counting it as user input would make the user's
    # actual request look far larger than it is.
    messages = [
        {"role": "user", "content": "Build a field guide."},
        {"role": "user", "content": "[EXECUTION STATE — managed by Codexa]\nCURRENT TASK: write it"},
    ]
    split = telemetry.split_context(messages)

    assert split.task_context > 0
    assert split.user > 0
    assert split.total == split.user + split.task_context


def test_recovery_directive_is_its_own_bucket():
    messages = [
        {"role": "user", "content": "[SYSTEM: that round was stopped at the budget] call the tool"},
    ]
    split = telemetry.split_context(messages)

    assert split.directive > 0
    assert split.user == 0


def test_prior_task_context_is_attributed_by_round():
    # This is the measurement the whole module exists for: how much of what a task is handed was
    # produced before that task began.
    messages = [
        {"role": "user", "content": "original request"},          # round 0
        {"role": "assistant", "content": "a" * 400},              # round 1 — earlier task
        {"role": "tool", "content": "b" * 400},                   # round 1 — earlier task
        {"role": "assistant", "content": "c" * 400},              # round 5 — this task
    ]
    rounds = [0, 1, 1, 5]
    split = telemetry.split_context(messages, rounds, task_started_round=5)

    assert split.prior_task_total > 0
    assert split.current_task_total > 0
    # Three of the four messages predate round 5, so history should dominate.
    assert split.prior_task_total > split.current_task_total


def test_no_active_task_attributes_nothing_to_prior():
    messages = [{"role": "user", "content": "hello"}]
    split = telemetry.split_context(messages, [0], task_started_round=None)

    assert split.prior_task_total == 0
    assert split.current_task_total == 0


def test_system_message_is_excluded_from_task_attribution():
    # The system message is re-sent every round and belongs to no task. Charging it to "prior task
    # context" would make history look large in every job, including single-task ones.
    messages = [
        _system("You are Codexa."),
        {"role": "assistant", "content": "work"},
    ]
    split = telemetry.split_context(messages, [-100, 3], task_started_round=3)

    assert split.prior_task_total == 0


def test_write_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEXA_TELEMETRY_PATH", str(tmp_path / "rounds.jsonl"))
    record = telemetry.new_record(job_id="job-1", round_no=2, model="glm")
    record.reasoning_chars = 40_000
    record.tool_calls = ["write_file"]
    record.context = telemetry.split_context([_system("hi")]).as_dict()
    telemetry.write(record)

    rows = telemetry.load(job_id="job-1")
    assert len(rows) == 1
    assert rows[0]["reasoning_chars"] == 40_000
    assert rows[0]["tool_calls"] == ["write_file"]
    assert telemetry.load(job_id="other") == []


def test_write_never_raises_on_a_bad_path(monkeypatch):
    # Instrumentation that can kill a job is worse than none. A path that cannot be created must be
    # swallowed, not propagated into the execution loop.
    monkeypatch.setattr(telemetry, "_path", lambda: (_ for _ in ()).throw(OSError("no disk")))
    telemetry.write(telemetry.new_record(job_id="j", round_no=0, model="m"))


def test_load_skips_malformed_lines(tmp_path, monkeypatch):
    path = tmp_path / "rounds.jsonl"
    path.write_text('{"job_id": "a"}\nnot json at all\n{"job_id": "b"}\n', encoding="utf-8")
    monkeypatch.setenv("CODEXA_TELEMETRY_PATH", str(path))

    assert len(telemetry.load()) == 2


def test_summarize_groups_by_task_in_first_seen_order():
    rows = [
        {"task_id": "t1", "task_objective": "commit direction", "reasoning_chars": 40_000,
         "tool_calls": [], "context": {"total": 8_000, "prior_task_total": 0, "design_brief": 2_600},
         "outcome": "cut", "generation_ms": 500},
        {"task_id": "t1", "task_objective": "commit direction", "reasoning_chars": 1_000,
         "tool_calls": ["commit_direction"], "context": {"total": 9_000, "prior_task_total": 500},
         "outcome": "ok", "generation_ms": 900},
        {"task_id": "t2", "task_objective": "write the page", "reasoning_chars": 2_000,
         "tool_calls": ["write_file"], "context": {"total": 30_000, "prior_task_total": 20_000},
         "outcome": "ok", "generation_ms": 1_200},
    ]
    summary = telemetry.summarize(rows)
    tasks = summary["tasks"]

    assert [t["task_id"] for t in tasks] == ["t1", "t2"]
    assert tasks[0]["rounds"] == 2
    assert tasks[0]["reasoning_chars"] == 41_000
    assert tasks[0]["cuts"] == 1
    assert tasks[0]["design_brief_tokens"] == 2_600
    assert tasks[1]["prior_task_tokens"] == 20_000


def test_disabled_by_env_writes_nothing(tmp_path, monkeypatch):
    path = tmp_path / "rounds.jsonl"
    monkeypatch.setenv("CODEXA_TELEMETRY_PATH", str(path))
    monkeypatch.setattr(telemetry, "_ENABLED", False)
    telemetry.write(telemetry.new_record(job_id="j", round_no=0, model="m"))

    assert not path.exists()


def test_counting_is_cached_so_a_stable_prefix_is_not_recounted(monkeypatch):
    # Long jobs re-send an identical prefix dozens of times. Without the cache the instrument's own
    # cost would scale with the thing it measures.
    telemetry._cache.clear()
    text = "the design brief " * 200
    first = telemetry.count_tokens(text)
    calls = {"n": 0}

    def _boom(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("should not be reached")

    monkeypatch.setattr("litellm.token_counter", _boom)
    assert telemetry.count_tokens(text) == first
    assert calls["n"] == 0


def test_token_count_falls_back_when_the_tokenizer_fails(monkeypatch):
    telemetry._cache.clear()
    monkeypatch.setattr("litellm.token_counter", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))

    assert telemetry.count_tokens("hello world") > 0


class _Timer:
    pass


def test_round_timer_reports_none_before_marks():
    timer = telemetry.RoundTimer()

    assert timer.first_token_ms is None
    assert timer.generation_ms is None
    assert timer.total_ms >= 0

    timer.mark_first_token()
    first = timer.first_token_ms
    timer.mark_first_token()          # only the first arrival counts
    assert timer.first_token_ms == first


@pytest.mark.parametrize("hidden,expected", [("1", False), ("", True), ("0", True)])
def test_hide_later_flag_controls_the_later_block(monkeypatch, hidden, expected):
    from backend.agents.plan import ExecutionPlan, make_task, task_context_block

    monkeypatch.setenv("CODEXA_HIDE_LATER", hidden)
    plan = ExecutionPlan(objective="Build a field guide", tasks=[
        make_task(objective="Commit to a direction", index=0),
        make_task(objective="Write index.html", index=1),
        make_task(objective="Build the motion system", index=2),
    ])
    block = task_context_block(plan, plan.tasks[0])

    assert ("LATER" in block) is expected
    # Either way the current task and the objective survive — the flag hides the future, not the
    # present.
    assert "Commit to a direction" in block
    assert "Build a field guide" in block


def test_suite_never_writes_to_the_real_telemetry_log():
    # Guard for the conftest isolation, not for the module. A full run once put 2,283 synthetic
    # rounds — 424 of them deliberate budget cuts — into the developer's real log, which is the one
    # file whose whole purpose is to describe real jobs.
    resolved = str(telemetry._path()).replace("\\", "/")
    assert not resolved.endswith(".codexa/round_telemetry.jsonl"), resolved
