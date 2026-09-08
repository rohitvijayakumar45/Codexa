"""Tests for backend/agents/phased_build.py.

Real motivation: two full-stack builds tonight each ran as one continuous job past 100-300+ rounds
before ever reaching "done", accumulating enough conversation history along the way to correlate
with real degradation (a compaction placeholder written back as literal file content in one run;
repeated identical stall-nudges piling up right before the connection went permanently silent in
another). PhasedBuildManager splits a big spec into an ordered chain of smaller jobs, each starting
with a FRESH conversation instead of one that keeps growing forever.
"""

from unittest.mock import MagicMock, patch

from backend.agents.phased_build import PhasedBuildManager, decompose_into_phases


class FakeLLM:
    def __init__(self, decompose_response: str):
        self._decompose_response = decompose_response
        self.available = ["fake-model"]
        self.default_model = "fake-model"

    def complete(self, messages, *, agent="generate", **kwargs):
        return self._decompose_response


class TestDecomposeIntoPhases:
    def test_parses_a_clean_json_array(self):
        llm = FakeLLM('[{"title": "Backend", "prompt": "Build the API"}, {"title": "Frontend", "prompt": "Build the UI"}]')
        phases = decompose_into_phases("Build a big app", llm)
        assert phases == [
            {"title": "Backend", "prompt": "Build the API"},
            {"title": "Frontend", "prompt": "Build the UI"},
        ]

    def test_strips_markdown_code_fences(self):
        llm = FakeLLM('```json\n[{"title": "Only phase", "prompt": "Do everything"}]\n```')
        phases = decompose_into_phases("spec", llm)
        assert phases == [{"title": "Only phase", "prompt": "Do everything"}]

    def test_falls_back_to_a_single_phase_on_malformed_json(self):
        llm = FakeLLM("not json at all")
        phases = decompose_into_phases("the original spec text", llm)
        assert len(phases) == 1
        assert phases[0]["prompt"] == "the original spec text"

    def test_falls_back_when_llm_raises(self):
        class BrokenLLM(FakeLLM):
            def complete(self, *args, **kwargs):
                raise RuntimeError("provider down")

        phases = decompose_into_phases("spec text", BrokenLLM(""))
        assert len(phases) == 1
        assert phases[0]["prompt"] == "spec text"

    def test_drops_malformed_individual_entries_but_keeps_good_ones(self):
        llm = FakeLLM('[{"title": "Good", "prompt": "Do this"}, {"nope": "missing fields"}, "not even a dict"]')
        phases = decompose_into_phases("spec", llm)
        assert phases == [{"title": "Good", "prompt": "Do this"}]

    def test_caps_at_max_phases(self):
        many = [{"title": f"P{i}", "prompt": f"do {i}"} for i in range(20)]
        import json
        llm = FakeLLM(json.dumps(many))
        phases = decompose_into_phases("spec", llm)
        from backend.agents.phased_build import _MAX_PHASES
        assert len(phases) == _MAX_PHASES


class FakeJobManager:
    """Minimal stand-in: create() registers a job dict, start() marks it running, and each
    subsequent .get() call advances a scripted status sequence so _run_phases' poll loop resolves
    without real sleeping (the phased build's own poll interval is patched to 0 in these tests)."""

    def __init__(self, status_sequences):
        self._status_sequences = list(status_sequences)  # one sequence of statuses per phase, in order
        self.created = []
        self._job_id_counter = 0
        self._job_statuses = {}

    def create(self, *, repository, model, messages):
        self._job_id_counter += 1
        job_id = f"job-{self._job_id_counter}"
        job = MagicMock()
        job.id = job_id
        job.messages = messages
        self.created.append({"repository": repository, "model": model, "messages": messages})
        sequence = self._status_sequences.pop(0) if self._status_sequences else ["done"]
        self._job_statuses[job_id] = iter(sequence)
        return job

    def start(self, job, *, last_user_text):
        pass

    def get(self, job_id):
        try:
            status = next(self._job_statuses[job_id])
        except StopIteration:
            status = "done"
        result = MagicMock()
        result.status = status
        result.tools_called = ["write_file", "write_file"]
        return result


class TestPhasedBuildManager:
    def test_start_returns_immediately_with_the_full_decomposed_plan_visible(self):
        llm = FakeLLM('[{"title": "Backend", "prompt": "p1"}, {"title": "Frontend", "prompt": "p2"}]')
        job_manager = FakeJobManager([["done"], ["done"]])
        manager = PhasedBuildManager(llm=llm, job_manager=job_manager)

        with patch("backend.agents.phased_build._POLL_INTERVAL_SECONDS", 0):
            build = manager.start("big spec", "demo-repo")

        # The plan is visible on the returned object immediately, before any phase has even
        # started running - this is the "transparency" requirement: the user sees the whole
        # breakdown up front, not just after the fact.
        assert len(build.phases) == 2
        assert build.phases[0].title == "Backend"
        assert build.phases[1].title == "Frontend"

    def test_all_phases_succeed_runs_them_in_order_and_marks_build_done(self):
        llm = FakeLLM('[{"title": "Backend", "prompt": "p1"}, {"title": "Frontend", "prompt": "p2"}]')
        job_manager = FakeJobManager([["running", "done"], ["running", "done"]])
        manager = PhasedBuildManager(llm=llm, job_manager=job_manager)

        with patch("backend.agents.phased_build._POLL_INTERVAL_SECONDS", 0), \
             patch("backend.agents.phased_build.threading.Thread") as mock_thread_cls:
            mock_thread_cls.return_value = MagicMock()  # start()'s own thread spawn is a no-op here
            build = manager.start("spec", "demo-repo")
            manager._run_phases(build)  # run synchronously for a deterministic test

        assert build.status == "done"
        assert [p.status for p in build.phases] == ["done", "done"]
        assert len(job_manager.created) == 2

    def test_a_phase_that_errors_stops_the_whole_build_without_starting_the_next_phase(self):
        llm = FakeLLM('[{"title": "Backend", "prompt": "p1"}, {"title": "Frontend", "prompt": "p2"}]')
        job_manager = FakeJobManager([["error"], ["done"]])
        manager = PhasedBuildManager(llm=llm, job_manager=job_manager)

        with patch("backend.agents.phased_build._POLL_INTERVAL_SECONDS", 0), \
             patch("backend.agents.phased_build.threading.Thread") as mock_thread_cls:
            mock_thread_cls.return_value = MagicMock()
            build = manager.start("spec", "demo-repo")
            manager._run_phases(build)

        assert build.status == "error"
        assert build.phases[0].status == "error"
        assert build.phases[1].status == "pending"  # never started - not built on a broken phase
        assert len(job_manager.created) == 1  # phase 2's job was never even created

    def test_second_phase_prompt_tells_the_agent_to_inspect_the_existing_repo(self):
        llm = FakeLLM('[{"title": "Backend", "prompt": "Build the API"}, {"title": "Frontend", "prompt": "Build the UI"}]')
        job_manager = FakeJobManager([["done"], ["done"]])
        manager = PhasedBuildManager(llm=llm, job_manager=job_manager)

        with patch("backend.agents.phased_build._POLL_INTERVAL_SECONDS", 0), \
             patch("backend.agents.phased_build.threading.Thread") as mock_thread_cls:
            mock_thread_cls.return_value = MagicMock()
            build = manager.start("spec", "demo-repo")
            manager._run_phases(build)

        second_phase_messages = job_manager.created[1]["messages"]
        user_message = next(m["content"] for m in second_phase_messages if m["role"] == "user")
        assert "inspect" in user_message.lower()
        assert "Build the UI" in user_message

    def test_get_returns_a_started_build_by_id(self):
        llm = FakeLLM('[{"title": "Only", "prompt": "p1"}]')
        job_manager = FakeJobManager([["done"]])
        manager = PhasedBuildManager(llm=llm, job_manager=job_manager)

        with patch("backend.agents.phased_build._POLL_INTERVAL_SECONDS", 0):
            build = manager.start("spec", "demo-repo")

        assert manager.get(build.id) is build

    def test_get_returns_none_for_an_unknown_id(self):
        manager = PhasedBuildManager(llm=FakeLLM(""), job_manager=FakeJobManager([]))
        assert manager.get("does-not-exist") is None
