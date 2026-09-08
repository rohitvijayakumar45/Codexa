"""Regression cover for the war-room audit.

Each class pins one confirmed defect found by adversarially attacking a subsystem rather than
reviewing it. Several are second-order failures of earlier fixes in this same codebase, which is the
point: a fix that closes one hole is a new assumption, and the next audit should attack it.
"""

from __future__ import annotations

import threading
import time

import pytest

from backend.agents.design_intent import derive
from backend.agents.jobs import _compact_stale_payloads, _stream_with_watchdog
from backend.agents.llm import CancellableStream
from backend.agents.plan import make_task
from backend.agents.progress import _is_agent_artefact, compare, snapshot
from backend.agents.task import TaskContract, TaskIntent, generate_contract, validate_completion
from backend.agents.tools import classify_intent, groups_providing, tools_for_groups
from backend.agents.validators import infer_validators
from backend.files.api import PROJECT_ROOT, is_platform_repo, repo_root
from fastapi import HTTPException


# ── security ──────────────────────────────────────────────────────────────────


class TestRepositoryNamesCannotEscapeTheStore:
    """`repo_root` only checked that the resolved path existed. A repository name is caller-supplied
    — from an HTTP body and from model-authored tool arguments — so `"../.."` resolved to Codexa's
    own project root while being unequal to "codexa-os", which is what the mutation guard compared.
    The guard passed and write_file, delete_file and apply_patch operated on Codexa's own source."""

    @pytest.mark.parametrize("name", ["../..", "../../..", "..", ".", "a/b", "~", "/etc"])
    def test_traversal_is_refused(self, name):
        with pytest.raises(HTTPException):
            repo_root(name)

    def test_the_platform_repo_is_identified_by_resolution_not_by_name(self):
        # The guard's real question. String comparison was the vulnerability.
        assert is_platform_repo("codexa-os") is True
        assert is_platform_repo(None) is True
        assert is_platform_repo("../..") is False  # refused, therefore not the platform

    def test_a_normal_repository_still_resolves(self):
        assert repo_root("codexa-os") == PROJECT_ROOT


class TestShellToolsCannotEditThePlatform:
    """`_MUTATING_TOOLS` enumerated file-API tools, so every tool that reaches the disk through a
    SHELL walked past it. `run_command` executes with shell=True and cwd=repo_root(repository), so
    on the platform repository it could rewrite Codexa's own source; `run_python` takes no
    repository argument at all, so the check could never apply to it however it was written."""

    @pytest.mark.parametrize("tool", ["run_command", "run_python", "run_tests", "typecheck",
                                      "lint", "build", "start_dev_server"])
    def test_the_shell_tools_are_guarded(self, tool):
        from backend.agents.tools import _MUTATING_TOOLS
        assert tool in _MUTATING_TOOLS


class TestCredentialFilesAreNeverReturnedToTheModel:
    """Reads stay open on the platform repository by design, and `.env` sits at its root — `_safe`
    correctly allows it because it IS inside the root. A single read put every provider key into the
    conversation, the event stream sent to the browser, and the checkpoint JSON on disk."""

    @pytest.mark.parametrize("path", [".env", ".env.local", "config/.env.production",
                                      "id_rsa", "server.pem", "credentials.json", ".npmrc"])
    def test_secret_files_are_refused(self, path):
        from backend.agents.tools import _is_secret_file
        assert _is_secret_file(path) is True

    @pytest.mark.parametrize("path", ["README.md", "src/env.ts", "backend/main.py",
                                      "environment.md"])
    def test_ordinary_files_are_unaffected(self, path):
        from backend.agents.tools import _is_secret_file
        assert _is_secret_file(path) is False


# ── the job must be able to do what its contract demands ──────────────────────


class TestAJobIsGivenTheToolsItsContractRequires:
    """`classify_intent` and `generate_contract` derive from the same text with different regexes,
    and disagreed. "build an html game of snake" matched `runtime` but not `code` (the `code`
    alternative is `build.?a\\b`, which "build an" fails), so write_file, edit_file, create_files
    and delegate_build were absent for the entire job — while the contract still demanded
    write_file. The model was told to call a tool it had never been offered."""

    @pytest.mark.parametrize("request_text", [
        "build an html game of snake",
        "build me a website",
        "make an interactive periodic table",
    ])
    def test_a_build_request_can_actually_write_files(self, request_text):
        contract = generate_contract(request_text)
        groups = set(classify_intent(request_text)) | groups_providing(contract.required_tools)
        names = {t["function"]["name"] for t in tools_for_groups(sorted(groups))}
        assert "write_file" in names, f"contract requires {contract.required_tools}, tools lack them"

    def test_every_required_tool_is_always_reachable(self):
        # The invariant, stated directly: a job's tools must be a superset of its requirements.
        for request_text in ("build an html game of snake", "fix the typo in README.md",
                             "run the tests", "delete the old config"):
            contract = generate_contract(request_text)
            groups = set(classify_intent(request_text)) | groups_providing(contract.required_tools)
            names = {t["function"]["name"] for t in tools_for_groups(sorted(groups))}
            assert set(contract.required_tools) <= names, request_text

    def test_a_ui_job_can_reach_the_skills_its_brief_names(self):
        # The resident design brief instructs the model to call get_design_guidance for specific
        # skills. For most real briefs the `design` group was never selected, so the tool the brief
        # named did not exist.
        request_text = ("Build a premium landing page for a specialty coffee roaster with scroll "
                        "animations and a screenshot")
        contract = generate_contract(request_text)
        assert derive(request_text, contract) is not None
        groups = set(classify_intent(request_text)) | groups_providing(contract.required_tools)
        groups |= groups_providing(["get_design_guidance", "screenshot", "start_dev_server"])
        names = {t["function"]["name"] for t in tools_for_groups(sorted(groups))}
        assert "get_design_guidance" in names


class TestDelegationSatisfiesTheContract:
    """validators.py allowed both delegating tools; task.py allowed only `delegate_task`. A job that
    built everything through `delegate_build` — the path the tool description recommends for
    substantial files — was told "you must call write_file" with the files already on disk."""

    @pytest.mark.parametrize("delegator", ["delegate_task", "delegate_build"])
    def test_either_delegator_counts_as_the_write(self, delegator):
        contract = TaskContract(intent=TaskIntent.CREATE, required_tools=["write_file"])
        passed, _ = validate_completion(contract, [delegator])
        assert passed


# ── progress must not be forgeable ────────────────────────────────────────────


class TestCodexasOwnArtefactsAreNotProgress:
    """`screenshot` writes `.codexa-screenshot.png` into the repository root. The snapshot skipped
    dot-DIRECTORIES only, so every screenshot round created or modified a file and reported real
    progress with nothing built — and `is_thrashing`, whose docstring names the screenshot loop as
    the exact escape it exists to catch, could never fire, because the screenshot tool supplied the
    disk change the check was looking for."""

    def test_the_screenshot_artefact_is_ignored(self):
        assert _is_agent_artefact(".codexa-screenshot.png") is True
        assert _is_agent_artefact(".codexa-repo.json") is True

    def test_real_files_are_still_counted(self):
        assert _is_agent_artefact("index.html") is False
        assert _is_agent_artefact("src/app.tsx") is False

    def test_a_screenshot_only_round_reports_no_disk_progress(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.agents.progress.repo_root", lambda _r: tmp_path)
        before = snapshot("demo")
        (tmp_path / ".codexa-screenshot.png").write_bytes(b"x" * 5000)
        after = snapshot("demo")
        signal = compare(before, after, tools_ran=["screenshot"])
        assert signal.created == [] and signal.modified == []


# ── crashes that were unrecoverable ───────────────────────────────────────────


class TestMalformedToolArgumentsDoNotKillTheJob:
    """A model can emit arguments that are valid JSON but not an object. `json.loads` SUCCEEDS, then
    `args.get(...)` raised AttributeError out of compaction — which runs outside any try in the round
    loop — killing the job with error_reason=None, so it was neither auto-continued nor eligible for
    Continue. The bad message stayed in history, so every resume re-crashed on it."""

    @pytest.mark.parametrize("arguments", ['"just a string"', "[1,2,3]", "42", "null", "true"])
    def test_compaction_survives_non_object_arguments(self, arguments):
        messages = [{"role": "assistant", "tool_calls": [
            {"function": {"name": "write_file", "arguments": arguments}}]}]
        _compact_stale_payloads(messages, [0], 10)  # must not raise


# ── cancellation must reach the provider ──────────────────────────────────────


class TestCancellationActuallyStopsTheProvider:
    """The consumer ran `source.close()`, but `source` is a generator and the producer thread is
    inside it — Python raises `ValueError: generator already executing`, which a best-effort
    `except Exception` swallowed. Every cut left the producer blocked on a live HTTP response with
    the provider still generating and still billing. Orphaned generation was the normal case."""

    class _Provider:
        def __init__(self):
            self.closed = False
            self.yielded = 0

        def __iter__(self):
            while not self.closed:
                self.yielded += 1
                time.sleep(0.01)
                yield "chunk"

        def close(self):
            self.closed = True

    def _stream(self):
        live: dict = {"stream": None}
        provider = self._Provider()

        def gen():
            live["stream"] = provider
            for chunk in provider:
                yield chunk

        return CancellableStream(gen(), live), provider

    def test_closing_reaches_the_provider_not_the_generator(self):
        stream, provider = self._stream()
        next(iter(stream))
        stream.close()
        assert provider.closed is True

    def test_generation_actually_stops(self):
        stream, provider = self._stream()
        consumer = _stream_with_watchdog(stream)
        next(consumer)
        consumer.close()

        deadline = time.time() + 3
        while time.time() < deadline and not provider.closed:
            time.sleep(0.02)
        assert provider.closed, "the provider kept generating after the round was cut"
        at_close = provider.yielded
        time.sleep(0.3)
        assert provider.yielded == at_close, "chunks were still arriving after close"

    def test_no_producer_thread_is_left_behind(self):
        before = threading.active_count()
        stream, _provider = self._stream()
        consumer = _stream_with_watchdog(stream)
        next(consumer)
        consumer.close()
        deadline = time.time() + 3
        while time.time() < deadline and threading.active_count() > before:
            time.sleep(0.05)
        assert threading.active_count() <= before

    def test_closing_twice_is_safe(self):
        stream, _provider = self._stream()
        next(iter(stream))
        stream.close()
        stream.close()


# ── the design gate must not be dead code ─────────────────────────────────────


class TestTheDesignGateIsReachable:
    """`design_evidence` was fully plumbed — `_Ctx.design`, the controller's `design=` argument —
    and referenced by nothing outside its own registry and two unit tests, because plan_builder
    overwrites every task's validators with `infer_validators`, which never returned it. The whole
    design-completion dimension was dead code that looked wired end to end."""

    def test_a_renderable_artifact_task_gets_the_design_check(self):
        task = make_task("write it", index=1, expected_artifacts=["index.html"],
                         required_tools=["write_file", "screenshot"])
        assert "design_evidence" in infer_validators(task)

    def test_a_non_renderable_task_does_not(self):
        task = make_task("write the schema", index=1, expected_artifacts=["schema.sql"],
                         required_tools=["write_file"])
        assert "design_evidence" not in infer_validators(task)


class TestNegationDoesNotEatTheInstruction:
    """"not X but Y" is the commonest way a brief states what it wants. The stripper consumed 80
    characters after any negation word and stopped only at a full stop, so it ate the Y: "Build not
    a landing page but a luxurious editorial archive" reduced to "Build", and a classical archive
    classified as generic contemporary with the wrong skills."""

    def test_the_affirmative_half_survives(self):
        brief = ("Build not a landing page but a luxurious editorial archive of rare manuscripts "
                 "with scroll animation and a screenshot")
        intent = derive(brief, generate_contract(brief))
        assert intent.character == "classical-editorial"

    def test_a_plain_negation_is_still_stripped(self):
        # The original regression: "not a conventional website or dashboard" must not read as
        # data-dense.
        brief = ("Build a manuscript archive, not a conventional website or dashboard, with "
                 "scroll animation and a screenshot")
        intent = derive(brief, generate_contract(brief))
        assert intent.character == "classical-editorial"
        assert intent.density == "airy"

    def test_an_affirmative_dashboard_is_still_data_dense(self):
        brief = "Build a data-dense telemetry dashboard with log tables and a screenshot"
        intent = derive(brief, generate_contract(brief))
        assert intent.character == "data-dense"
