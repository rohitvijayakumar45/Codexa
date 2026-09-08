"""Design expertise must reach the model, and the result must be checked against it.

The measurement that started this: across 21 real benchmark jobs and roughly a thousand tool calls,
`get_design_guidance` was called exactly ONCE. Codexa ships 202KB of design expertise and it was
effectively never in context. Four mechanisms produced that:

1. It is a PULL tool nothing obliges the model to call.
2. `build_task_prompt` — which lists the required tools — was appended to the system message by the
   HTTP layer, and only `if messages[0]["role"] == "system"`. A job started through the API with
   just a user message silently got no task prompt at all. Every overnight job was that shape, so
   none of them ever saw TASK MODE or REQUIRED TOOLS.
3. When it was loaded, the tool result was compacted away after 3 rounds — before implementation.
4. The default skill is 88KB and truncates to 30KB, two thirds discarded mid-rule.

A second finding corrected an assumption worth recording here, because it changed the fix: the
generated pages were NOT short of interaction code. One had 16 event listeners, 11 buttons, 30
transitions, focus-visible styles and a reduced-motion block; another had 45 listeners and 52% of
its bytes in JavaScript. The binding constraint was that nothing checked whether any of it RAN — the
second page renders blank because its script dies on a syntax error, and it passed two refinement
passes on "the file exists" and "a screenshot was taken", both true of a page showing nothing.
"""

from pathlib import Path

import pytest

from backend.agents.design_intent import DesignIntent, brief, derive
from backend.agents.plan import make_task
from backend.agents.task import generate_contract
from backend.agents.validators import _VALIDATORS, infer_validators, validate_task

VELUM = Path("prompts/overnight/1-velum.md")


def intent_for(request: str):
    return derive(request, generate_contract(request))


def velum_intent():
    return intent_for(VELUM.read_text(encoding="utf-8"))


class TestIntentIsOnlyDerivedForFrontendWork:
    def test_a_ui_build_gets_an_intent(self):
        assert intent_for("Build a single self-contained HTML archive with animations") is not None

    @pytest.mark.parametrize("request_text", [
        "run the tests and report the output",
        "explain how python decorators work",
    ])
    def test_a_non_ui_task_gets_none(self, request_text):
        # Attaching a design brief to "run the tests" is noise in every prompt for that whole job.
        assert intent_for(request_text) is None


class TestDifferentProductsGetDifferentExpertise:
    """A classical archive, a luxury finance app and a telemetry dashboard must not all receive the
    same guidance — which is exactly what one default skill for everything produces."""

    def test_an_archive_and_a_dashboard_do_not_get_the_same_guidance(self):
        archive = intent_for("Build a single-file HTML manuscript archive, classical serif and "
                             "editorial, with scroll animations and a filterable collection")
        dash = intent_for("Build a data-dense monitoring dashboard with telemetry tables, log "
                          "streams and a screenshot of the result")
        assert archive.character != dash.character
        assert archive.skills != dash.skills

    @pytest.mark.parametrize("request_text", [
        "Build a classical HTML archive with animation and a screenshot",
        "Build a luxury private-bank interface with charts and a screenshot",
        "Build a terminal-style log dashboard with a screenshot",
    ])
    def test_only_one_visual_style_is_ever_loaded(self, request_text):
        # Two visual styles do not average. They let the model take whichever rule is convenient at
        # each decision, which is how a design system drifts apart inside one file.
        visual = {"minimalist_editorial", "high_end_agency", "industrial_brutalist", "anti_slop"}
        intent = intent_for(request_text)
        assert len(set(intent.skills) & visual) == 1, intent.skills

    def test_the_skill_set_stays_small(self):
        assert 1 <= len(velum_intent().skills) <= 3, "more context is not automatically better"


class TestNegatedLanguageIsNotReadAsIntent:
    def test_saying_it_is_not_a_dashboard_does_not_make_it_one(self):
        # VELUM's brief contains "not a conventional website or dashboard". Keyword matching read
        # that as a data-dense signal and gave a manuscript archive a terminal reading of itself.
        intent = velum_intent()
        assert intent.character == "classical-editorial"
        assert intent.density == "airy"


class TestInteractionDepthIsDecidedUpFront:
    def test_a_product_brief_is_not_read_as_a_page(self):
        assert velum_intent().interaction_depth == "product"

    def test_depth_drives_the_constraints(self):
        joined = " ".join(velum_intent().principles).lower()
        assert "landing page" in joined or "signature interaction" in joined
        assert "focus-visible" in joined


class TestTheBriefIsResident:
    """The full skill files are tens of thousands of characters and are compacted away after three
    rounds — before any implementation happens. The brief has to be small enough to simply stay."""

    def test_it_is_small_enough_to_resend_every_round(self):
        text = brief(velum_intent())
        assert 0 < len(text) < 4000, f"{len(text)} chars is too big to keep resident"

    def test_it_names_the_skills_to_load_rather_than_leaving_it_to_chance(self):
        assert "get_design_guidance" in brief(velum_intent())

    def test_no_intent_produces_no_brief(self):
        assert brief(None) == ""


class TestTheTaskPromptNoLongerDependsOnTheCaller:
    def test_a_job_started_without_a_system_message_still_gets_one(self):
        # The exact shape every overnight benchmark job had, and the reason none of them ever saw
        # TASK MODE, REQUIRED TOOLS or any design guidance at all.
        import unittest.mock as mock

        from backend.agents.jobs import JobManager

        class _LLM:
            usage = None

            def record_usage(self, *a, **k):
                return {"prompt_tokens": 0, "completion_tokens": 0}

            def context_window(self, model):
                return 8000

            def tier_of(self, model):
                return None

            def models_for_tier(self, tier):
                return []

        manager = JobManager(llm=_LLM(), graph=None, store=None)
        request = "Build a single self-contained HTML archive with scroll animations"
        job = manager.create(repository="demo", model="m",
                             messages=[{"role": "user", "content": request}])

        with mock.patch("backend.agents.jobs.threading.Thread"), \
             mock.patch("backend.agents.jobs.predict_token_budget"):
            manager.start(job, last_user_text=request)

        assert job.messages[0]["role"] == "system"
        assert "TASK MODE" in job.messages[0]["content"]
        assert "DESIGN INTENT" in job.messages[0]["content"]
        # These two lists are index-matched; compaction reads round numbers positionally.
        assert len(job.messages) == len(job.message_rounds)


class TestRenderingIsPartOfCompletion:
    """The check that was actually missing. Both prior artifacts had plenty of interaction code and
    one of them renders blank."""

    def _task(self):
        return make_task("Final validation", index=1, expected_artifacts=["index.html"],
                         required_tools=["screenshot"], validators=["renders_cleanly"])

    @staticmethod
    def _point_at(tmp_path, monkeypatch):
        # BOTH namespaces. The validator resolves the artifact through validators.repo_root, then
        # hands the file:// URI to tools._screenshot_structured, which resolves the repository
        # again through its OWN repo_root to decide where to save the PNG. Patching only the first
        # left the second raising 404, which the validator correctly reports as "not checked" — so
        # the test skipped and the check was never actually exercised.
        for module in ("backend.agents.validators", "backend.agents.tools"):
            monkeypatch.setattr(f"{module}.repo_root", lambda _r, _p=tmp_path: _p)

    def test_a_page_whose_script_dies_fails(self, tmp_path, monkeypatch):
        self._point_at(tmp_path, monkeypatch)
        (tmp_path / "index.html").write_text(
            "<!doctype html><html><head><title>t</title></head><body>"
            "<div id='app'></div><script>const a = ,;</script></body></html>",
            encoding="utf-8")
        result = validate_task(self._task(), repository="demo",
                               tools_called_in_task=["screenshot"])
        if "not checked" in result.detail:
            pytest.skip("no browser available in this environment")
        assert not result.passed
        assert "render" in result.detail.lower() or "console" in result.detail.lower()

    def test_a_real_page_passes(self, tmp_path, monkeypatch):
        self._point_at(tmp_path, monkeypatch)
        (tmp_path / "index.html").write_text(
            "<!doctype html><html><head><title>t</title></head><body><main>"
            + "<p>Real archival content.</p>" * 30
            + "<button type='button'>Open</button></main></body></html>",
            encoding="utf-8")
        result = validate_task(self._task(), repository="demo",
                               tools_called_in_task=["screenshot"])
        if "not checked" in result.detail:
            pytest.skip("no browser available in this environment")
        assert result.passed, result.detail

    def test_it_is_inferred_for_the_task_that_looks_at_the_result(self):
        task = make_task("Run it and look", index=1, expected_artifacts=["index.html"],
                         required_tools=["screenshot"])
        assert "renders_cleanly" in infer_validators(task)

    def test_it_is_not_inferred_for_a_non_renderable_artifact(self):
        task = make_task("Write the schema", index=1, expected_artifacts=["schema.sql"],
                         required_tools=["screenshot"])
        assert "renders_cleanly" not in infer_validators(task)


class TestDesignEvidenceChecksCapabilityNotTaste:
    """This asks whether the artifact CAN do what its intent called for. It cannot tell a beautiful
    hover state from an ugly one and does not try — but it can tell a product from a brochure, which
    is the distinction that was being lost."""

    RICH_PAGE = """
        <html><head><style>
          .x:hover{opacity:.8} .x:focus-visible{outline:2px solid} .x:active{transform:none}
          [disabled]{opacity:.4} .loading{opacity:.5}
          @keyframes fade{from{opacity:0}to{opacity:1}}
          .y{transition: opacity .2s}
          @media (max-width: 640px){.y{display:block}}
          @media (prefers-reduced-motion: reduce){*{animation:none}}
        </style></head><body>
          <button class="x" aria-label="Open">Open</button><input aria-label="Search">
          <script>
            document.querySelector('button').addEventListener('click', function () {});
            new IntersectionObserver(function () {});
          </script>
        </body></html>"""

    def _check(self, tmp_path, monkeypatch, body):
        monkeypatch.setattr("backend.agents.validators.repo_root", lambda _r: tmp_path)
        (tmp_path / "index.html").write_text(body, encoding="utf-8")
        task = make_task("Implement interactions", index=1, expected_artifacts=["index.html"],
                         validators=["design_evidence"])
        intent = DesignIntent(
            character="classical-editorial", interaction_depth="product", motion="considered",
            density="airy", responsive=True,
            quality_checks=["interaction", "states", "motion", "responsive", "accessibility"])
        return validate_task(task, repository="demo", tools_called_in_task=[],
                             design=intent.to_dict())

    def test_a_static_brochure_fails(self, tmp_path, monkeypatch):
        result = self._check(tmp_path, monkeypatch,
                             "<html><body><h1>Archive</h1><p>Some prose.</p></body></html>")
        assert not result.passed
        assert "capability check, not a style opinion" in result.detail

    def test_a_page_with_real_behaviour_passes(self, tmp_path, monkeypatch):
        result = self._check(tmp_path, monkeypatch, self.RICH_PAGE)
        assert result.passed, result.detail

    def test_no_intent_means_no_opinion(self, tmp_path, monkeypatch):
        # A validator that invents a design opinion for a task that never had one would fail work
        # nobody asked to be designed.
        monkeypatch.setattr("backend.agents.validators.repo_root", lambda _r: tmp_path)
        (tmp_path / "index.html").write_text("<html><body>x</body></html>", encoding="utf-8")
        task = make_task("t", index=1, expected_artifacts=["index.html"],
                         validators=["design_evidence"])
        result = validate_task(task, repository="demo", tools_called_in_task=[])
        assert result.passed
        assert "no design intent" in result.detail


class TestEveryInferredNameIsReal:
    def test_inference_never_invents_a_validator(self):
        task = make_task("t", index=1, expected_artifacts=["a.html"],
                         required_tools=["screenshot", "write_file"])
        assert set(infer_validators(task)) <= set(_VALIDATORS)
