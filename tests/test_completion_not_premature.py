"""Regression test for a real bug found during tonight's audit: backend/agents/jobs.py's _loop
used to stop enforcing validate_completion/claim-verification once `_round >= 8`, silently
accepting the model's answer as "done" even with an unsatisfied contract (e.g. required_tools never
called) — "the model returns HTML source in chat" without ever calling write_file, exactly the
premature-completion failure mode this session's audit was asked to rule out. That escape hatch
existed to avoid forcing retries right before the old hard round cap; it's obsolete (and actively
harmful) now that round exhaustion auto-continues itself instead of being a dead end.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.agents.jobs import Job, JobManager, _MAX_AUTO_CONTINUES, _MAX_ROUNDS


def _fake_chunk(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, reasoning_content=None))])


class NeverCallsToolLLM:
    """Every round: a plain text reply, no tool_calls, ever — simulating a model that just narrates
    ("Here's the HTML...") instead of actually calling write_file, no matter how many rounds it gets."""

    def stream(self, model, messages, timeout=240, **kwargs):
        yield _fake_chunk("Here is the implementation...")

    def record_usage(self, *args, **kwargs):
        return {"prompt_tokens": 1, "completion_tokens": 1}

    def context_window(self, model):
        return 8000

    def tier_of(self, model):
        return None

    def models_for_tier(self, tier):
        return []


def _never_calling_final():
    m = MagicMock()
    m.choices = [MagicMock()]
    m.choices[0].message.content = "Here is the complete HTML for your benchmark page."
    m.choices[0].message.tool_calls = None
    return m


def test_unsatisfied_contract_never_falsely_completes_near_the_old_round_cap():
    manager = JobManager(llm=NeverCallsToolLLM(), graph=None, store=None)
    job = Job(
        id="premature-completion-job",
        repository="demo-repo",
        model="fake-model",
        messages=[{"role": "user", "content": "Create a single HTML benchmark file"}],
        message_rounds=[-100],
        contract={
            "intent": "CREATE_ARTIFACT", "required_tools": ["write_file"], "allowed_tools": [],
            "success_criteria": [], "constraints": [], "suggested_workflow": [],
        },
        active_tool_groups=[],
    )

    with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=_never_calling_final()):
        manager._run(job, resuming=False)

    # It must NEVER report "done" while write_file was never called - not even once, at any round -
    # regardless of how the job ultimately terminates (auto-continued into a bounded error is fine;
    # a false "done" is the actual bug).
    assert job.status != "done"
    assert "write_file" not in job.tools_called
    # Enforcement must fire on the rounds that actually ran, and must never lapse into acceptance.
    validation_events = [
        e for e in job.events
        if e.get("tool_call", {}).get("name") == "_task_validation"
    ]
    assert validation_events, "enforcement never ran at all"
    # Not "no task ever passed": a plan legitimately contains tasks with nothing mechanical to check
    # (deciding a direction), and those pass on a plain reply by design. The claim under test is
    # narrower and is the one that was actually broken — a task that must leave a file behind can
    # never be accepted while no file was written.
    assert all(
        e["tool_call"]["args"].get("status") != "passed"
        for e in validation_events
        if "artifacts_exist" in e["tool_call"]["args"].get("checked", [])
    ), "a task requiring an artifact was accepted despite write_file never being called"

    # It also stops well short of the full budget now, and says why.
    #
    # This assertion replaces an older one requiring exactly _MAX_ROUNDS * (_MAX_AUTO_CONTINUES + 1)
    # validations — i.e. that the job grind through all 210 rounds before giving up. That was the
    # right guarantee when nothing could tell "still making progress" from "failing identically
    # forever", so the only safe move was to keep enforcing until the budget ran out. The execution
    # plan (backend/agents/plan.py) can now tell the difference: each task is attempted a bounded
    # number of times, checked against the repository, and abandoned once forcing it has visibly
    # stopped working. A model that will never call write_file is identified in tens of rounds
    # rather than hundreds, which is the same amount of enforcement and a great deal less of the
    # user's wall-clock time and provider quota spent proving a foregone conclusion.
    assert len(validation_events) < _MAX_ROUNDS * (_MAX_AUTO_CONTINUES + 1)
    assert job.error_reason in ("tasks_failed", "plan_blocked", "max_rounds")
    assert any("incomplete task" in str(e.get("error", "")) for e in job.events) or \
        job.error_reason == "max_rounds"
