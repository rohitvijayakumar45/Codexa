"""Phased builds, after a real one ran as a single "Build (undecomposed)" phase: the split used only
the default model (GLM via TokenRouter), which answered "Connection error", with no fallback.
Also: a phased build can now be cancelled as a whole."""

import json
from types import SimpleNamespace

from backend.agents import phased_build
from backend.agents.phased_build import PhasedBuild, PhasedBuildManager, PhaseResult, _parse_phases, decompose_into_phases

PHASES = [{"title": "Backend API", "prompt": "Build the API"}, {"title": "Frontend", "prompt": "Build the UI"}]


class _Llm:
    default_model = "tokenrouter/z-ai/glm-5.3-free"

    def __init__(self, replies):
        self.replies = replies  # model -> reply text, or an Exception to raise
        self.tried: list[str] = []

    def models_for_tier(self, tier):
        return {"light": ["gemini/gemini-3.6-flash", "groq/openai/gpt-oss-20b"], "balanced": []}.get(tier, [])

    def complete(self, messages, *, model, agent, **kw):
        self.tried.append(model)
        reply = self.replies.get(model, RuntimeError("Connection error"))
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_a_failing_model_falls_through_to_the_next():
    llm = _Llm({"gemini/gemini-3.6-flash": RuntimeError("Connection error"),
                "groq/openai/gpt-oss-20b": json.dumps(PHASES)})
    assert decompose_into_phases("big spec", llm) == PHASES
    assert llm.tried[:2] == ["gemini/gemini-3.6-flash", "groq/openai/gpt-oss-20b"]


def test_only_when_every_model_fails_is_the_build_undecomposed():
    llm = _Llm({})
    out = decompose_into_phases("big spec", llm)
    assert out == [{"title": "Build (undecomposed)", "prompt": "big spec"}]
    assert "tokenrouter/z-ai/glm-5.3-free" in llm.tried  # the job's own model is the last resort


def test_a_phase_list_wrapped_in_prose_or_fences_is_still_read():
    assert _parse_phases("Here is the plan:\n```json\n" + json.dumps(PHASES) + "\n```\nGood luck!") == PHASES
    assert _parse_phases("no list here") == []


class _Jobs:
    def __init__(self):
        self.created = 0
        self.cancelled: list[str] = []

    def create(self, **kw):
        self.created += 1
        return SimpleNamespace(id=f"job-{self.created}")

    def start(self, job, **kw):
        pass

    def get(self, job_id):
        return SimpleNamespace(status="done", tools_called=[])

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        return True


def test_a_cancelled_build_starts_no_further_phases(monkeypatch):
    monkeypatch.setattr(phased_build, "_POLL_INTERVAL_SECONDS", 0)
    jobs = _Jobs()
    manager = PhasedBuildManager(llm=SimpleNamespace(available=[], default_model="m"), job_manager=jobs)
    build = PhasedBuild(id="b1", repository="r", spec="s",
                        phases=[PhaseResult(title=p["title"], prompt=p["prompt"]) for p in PHASES])
    build.cancelled = True
    manager._run_phases(build)
    assert jobs.created == 0
    assert build.status == "cancelled"


def test_a_resumed_build_skips_done_phases_and_continues_the_existing_job(monkeypatch):
    monkeypatch.setattr(phased_build, "_POLL_INTERVAL_SECONDS", 0)
    jobs = _Jobs()
    jobs.resumed = []
    jobs.resume = lambda job_id: jobs.resumed.append(job_id)
    manager = PhasedBuildManager(llm=SimpleNamespace(available=[], default_model="m"), job_manager=jobs)
    build = PhasedBuild(id="b3", repository="r", spec="s", status="running", current_phase=1, phases=[
        PhaseResult(title="A", prompt="a", job_id="job-a", status="done"),
        PhaseResult(title="B", prompt="b", job_id="job-b", status="running"),
        PhaseResult(title="C", prompt="c"),
    ])
    manager._run_phases(build)
    assert jobs.resumed == ["job-b"]  # continued, not duplicated
    assert jobs.created == 1  # only phase C needed a new job
    assert build.status == "done" and all(p.status == "done" for p in build.phases)


def test_resume_unfinished_picks_up_running_builds_from_disk(monkeypatch, tmp_path):
    monkeypatch.setattr(phased_build, "PHASED_BUILDS_DIR", tmp_path)
    started: list[str] = []
    monkeypatch.setattr(PhasedBuildManager, "_run_phases", lambda self, b: started.append(b.id))
    manager = PhasedBuildManager(llm=SimpleNamespace(available=[], default_model="m"), job_manager=_Jobs())
    for bid, status in (("live", "running"), ("finished", "done"), ("stopped", "cancelled")):
        b = PhasedBuild(id=bid, repository="r", spec="s", status=status, phases=[PhaseResult(title="A", prompt="a")])
        (tmp_path / f"{bid}.json").write_text(json.dumps(b.to_disk()), encoding="utf-8")
    assert sorted(manager.resume_unfinished()) == ["live"]
    import time as _t
    _t.sleep(0.1)
    assert started == ["live"]


def test_cancel_stops_the_running_phase_job():
    jobs = _Jobs()
    manager = PhasedBuildManager(llm=SimpleNamespace(available=[], default_model="m"), job_manager=jobs)
    build = PhasedBuild(id="b2", repository="r", spec="s", status="running", current_phase=0,
                        phases=[PhaseResult(title="A", prompt="a", job_id="job-7", status="running")])
    manager._builds["b2"] = build
    assert manager.cancel("b2") is True
    assert jobs.cancelled == ["job-7"] and build.cancelled and build.status == "cancelled"
