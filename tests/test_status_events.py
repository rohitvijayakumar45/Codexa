"""Tests for the "status" event stream added to backend/agents/jobs.py.

Real motivation: many models (confirmed this session, e.g. GLM) never emit reasoning_content at
all, so a job's frontend saw literally zero events between "the last tool result" and "the next
thing that happens" - looking identical to a hang. This adds an honest, human-readable status event
at the start of every round (covering that gap) and alongside each dispatched tool call (covering
"just thinking" with something more specific to what's actually happening).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.agents.jobs import Job, JobManager, _friendly_tool_status


def _fake_chunk(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, reasoning_content=None))])


class PlainReplyLLM:
    """No reasoning_content, ever - the exact shape that used to leave the round-start gap silent."""

    def stream(self, model, messages, timeout=240, **kwargs):
        yield _fake_chunk("done talking")

    def record_usage(self, *args, **kwargs):
        return {"prompt_tokens": 1, "completion_tokens": 1}

    def context_window(self, model):
        return 8000

    def tier_of(self, model):
        return None

    def models_for_tier(self, tier):
        return []


def _plain_final():
    m = MagicMock()
    m.choices = [MagicMock()]
    m.choices[0].message.content = "All done."
    m.choices[0].message.tool_calls = None
    return m


def _write_file_final():
    m = MagicMock()
    m.choices = [MagicMock()]
    tc = MagicMock()
    tc.id = "tc1"
    tc.function.name = "write_file"
    tc.function.arguments = '{"path": "app.py", "content": "print(1)"}'
    m.choices[0].message.content = ""
    m.choices[0].message.tool_calls = [tc]
    return m


class TestFriendlyToolStatus:
    def test_known_tool_with_path_includes_the_path(self):
        assert _friendly_tool_status("write_file", {"path": "app.py"}) == "Writing app.py"

    def test_known_tool_without_a_path_still_returns_something_specific(self):
        assert _friendly_tool_status("run_tests", {}) == "Running tests"

    def test_known_path_tool_falls_back_gracefully_with_no_path_given(self):
        assert _friendly_tool_status("read_file", {}) == "Reading"

    def test_unknown_public_tool_gets_a_generic_but_honest_label(self):
        assert _friendly_tool_status("some_future_tool", {}) == "Using some_future_tool"

    def test_internal_underscore_prefixed_pseudo_tools_get_the_generic_working_label(self):
        assert _friendly_tool_status("_auto_continue", {}) == "Working on the next step"


class TestRoundStartStatusEvent:
    def test_a_status_event_is_emitted_before_the_round_even_starts_streaming(self):
        manager = JobManager(llm=PlainReplyLLM(), graph=None, store=None)
        job = Job(
            id="status-round-start-job", repository="demo-repo", model="fake-model",
            messages=[{"role": "user", "content": "hi"}], message_rounds=[-100],
            contract={"intent": "CONVERSATION", "required_tools": [], "allowed_tools": [],
                      "success_criteria": [], "constraints": [], "suggested_workflow": []},
            active_tool_groups=[],
        )
        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=_plain_final()):
            manager._run(job, resuming=False)

        kinds = [list(e.keys())[0] for e in job.events]
        assert "status" in kinds
        # The status event for the round must land before the first delta - it exists specifically
        # to cover the gap before any real content arrives, not to trail behind it.
        assert kinds.index("status") < kinds.index("delta")


class TestToolCallStatusEvent:
    def test_a_status_event_accompanies_each_dispatched_tool_call(self):
        manager = JobManager(llm=PlainReplyLLM(), graph=None, store=None)
        job = Job(
            id="status-tool-call-job", repository="demo-repo", model="fake-model",
            messages=[{"role": "user", "content": "Create app.py"}], message_rounds=[-100],
            contract={"intent": "CREATE_ARTIFACT", "required_tools": ["write_file"], "allowed_tools": [],
                      "success_criteria": [], "constraints": [], "suggested_workflow": []},
            active_tool_groups=["files"],
        )
        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=_write_file_final()), \
             patch("backend.agents.jobs.execute_tool", return_value="wrote it"):
            manager._run(job, resuming=False)

        status_texts = [e["status"] for e in job.events if "status" in e]
        assert "Writing app.py" in status_texts
