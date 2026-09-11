"""Tests for the paragraph separator between rounds' visible text in backend/agents/jobs.py.

Real motivation: every round of an agent job streams its narration into the same assistant message
on the client ("I'll inspect the repository structure." and then, several tool calls later, "Now
I'll write the file."). Nothing separated them, so the chat rendered them fused together as
"structure.Now I'll write the file" — a long job became one unreadable wall of run-on sentences.
The loop now emits a "\n\n" delta when a round's first visible text follows an earlier round's.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.agents.jobs import Job, JobManager


def _chunk(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, reasoning_content=None))])


class NarratingLLM:
    """Streams the same line of narration every round, the way real models narrate each step."""

    def stream(self, model, messages, timeout=240, **kwargs):
        yield _chunk("done talking")

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
    m.choices[0].message.content = "done talking"
    m.choices[0].message.tool_calls = None
    return m


def _write_file_final():
    m = MagicMock()
    m.choices = [MagicMock()]
    tc = MagicMock()
    tc.id = "tc1"
    tc.function.name = "write_file"
    tc.function.arguments = '{"path": "app.py", "content": "print(1)"}'
    m.choices[0].message.content = "done talking"
    m.choices[0].message.tool_calls = [tc]
    return m


def _deltas(job: Job) -> list[str]:
    return [e["delta"] for e in job.events if "delta" in e]


class TestRoundSeparator:
    def test_a_second_round_starts_a_new_paragraph_instead_of_fusing(self):
        manager = JobManager(llm=NarratingLLM(), graph=None, store=None)
        job = Job(
            id="round-separator-job", repository="demo-repo", model="fake-model",
            messages=[{"role": "user", "content": "Create app.py"}], message_rounds=[-100],
            contract={"intent": "CREATE_ARTIFACT", "required_tools": ["write_file"], "allowed_tools": [],
                      "success_criteria": [], "constraints": [], "suggested_workflow": []},
            active_tool_groups=["files"],
        )
        finals = iter([_write_file_final()])

        def build(*_a, **_k):
            # First round writes the file; every later round is a plain reply.
            return next(finals, None) or _plain_final()

        with patch("backend.agents.jobs.litellm.stream_chunk_builder", side_effect=build), \
             patch("backend.agents.jobs.execute_tool", return_value="wrote it"):
            manager._run(job, resuming=False)

        deltas = _deltas(job)
        assert deltas.count("done talking") >= 2, deltas
        # The job's opening text is never preceded by a separator — there is nothing to separate
        # it from.
        assert deltas[0] == "done talking"
        # Every later round's text is.
        text = "".join(deltas)
        assert "done talking\n\ndone talking" in text
        assert "done talkingdone talking" not in text

    def test_a_single_round_job_emits_no_separator(self):
        manager = JobManager(llm=NarratingLLM(), graph=None, store=None)
        job = Job(
            id="round-separator-single", repository="demo-repo", model="fake-model",
            messages=[{"role": "user", "content": "hi"}], message_rounds=[-100],
            contract={"intent": "CONVERSATION", "required_tools": [], "allowed_tools": [],
                      "success_criteria": [], "constraints": [], "suggested_workflow": []},
            active_tool_groups=[],
        )
        with patch("backend.agents.jobs.litellm.stream_chunk_builder", return_value=_plain_final()):
            manager._run(job, resuming=False)

        assert "\n\n" not in _deltas(job)
