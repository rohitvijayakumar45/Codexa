"""A plan must be about the request it came from.

The reported failure, in the user's words: "even when I try editing a file in a repo it gives same
task list which is useless". It was accurate. `_modify_specs` took only the contract and never
looked at the request, so every MODIFY produced the same four generic objectives — "Locate the code
that has to change and read it", "Make the targeted change" — whether the ask was to fix a typo or
restructure a module. None of them named the file. A plan that is identical for every request
carries no information and costs four validated task transitions to deliver it.

Underneath that sat a second cause: the LLM proposal path, which WOULD have shaped a plan around the
request, had been failing on every job (a 25s timeout against a reasoning model that needs minutes),
so every plan in the system was the deterministic template. That made the template's genericness the
whole product rather than a fallback nobody saw.
"""

import json

from backend.agents.plan_builder import fallback_plan
from backend.agents.task import generate_contract


def plan_for(request: str):
    return fallback_plan(request, generate_contract(request))


def objectives(request: str) -> str:
    return " || ".join(t.objective for t in plan_for(request).tasks)


class TestAPlanNamesWhatItIsAbout:
    def test_a_small_edit_names_the_file_in_its_objective(self):
        # The specific complaint: the plan read the same regardless of the request.
        assert "src/components/Header.tsx" in objectives(
            "update the button colour in src/components/Header.tsx to burgundy")

    def test_the_file_becomes_a_checkable_expected_artifact(self):
        plan = plan_for("update the button colour in src/components/Header.tsx to burgundy")
        assert any("src/components/Header.tsx" in t.expected_artifacts for t in plan.tasks)

    def test_two_different_edits_do_not_produce_the_same_plan(self):
        a = objectives("fix the typo in README.md")
        b = objectives("update the button colour in src/components/Header.tsx to burgundy")
        assert a != b


class TestAPlanIsSizedToTheChange:
    def test_a_one_line_edit_gets_two_tasks(self):
        # Four validated task transitions to change one line is overhead, not rigour.
        assert len(plan_for("fix the typo in README.md").tasks) == 2

    def test_a_refactor_is_not_treated_as_a_one_line_edit(self):
        # Measured: this is thirty words, so a word count alone called it small. It touches every
        # caller. Brevity is necessary but never sufficient.
        plan = plan_for(
            "refactor the authentication module to use JWT everywhere, split the session helpers "
            "out of auth/session.py, update every caller, and keep the existing tests passing")
        assert len(plan.tasks) >= 3

    def test_naming_several_files_rules_out_the_small_shape(self):
        plan = plan_for("move the parser from lib/parse.py into core/parser.py and update main.py")
        assert len(plan.tasks) >= 3

    def test_a_ui_change_keeps_the_look_at_it_steps(self):
        # The one case where extra tasks earn their keep: nothing else verifies a visual change.
        text = objectives("change the spacing on the dashboard cards so the layout breathes more")
        assert "screenshot" in text.lower() or "rendered" in text.lower()


class TestFullStackIsNotPlannedAsAPage:
    """A full-stack brief used to fall through to the single-file CREATE template and get planned as
    "write the primary file, implement the core experience, screenshot it". Every validator then
    checked a frontend, so a run could satisfy its entire plan having written no schema, no endpoint
    and no persistence — a plan cannot catch what it never asked for."""

    HELIX = ("Build HELIX, a full-stack collaborative research application. Build the frontend, "
             "backend, database, API layer, persistence and validation. The application must have "
             "real persistence and a proper relational data model with clean API architecture.")

    def test_it_plans_a_schema_a_backend_and_persistence(self):
        text = objectives(self.HELIX).lower()
        assert "schema" in text or "data model" in text
        assert "backend" in text or "api" in text
        assert "seed" in text or "persistence" in text

    def test_it_verifies_the_stack_actually_runs(self):
        assert "run" in objectives(self.HELIX).lower()

    def test_a_declared_single_file_request_is_never_full_stack(self):
        # VELUM's brief says "archive" and AURELIA's says "portfolio"; neither is a server. An
        # explicit "single self-contained HTML file" outranks every backend-sounding noun.
        text = objectives(
            "Build a single self-contained HTML application called VELUM, an immersive digital "
            "archive for rare manuscripts. Use realistic archival content and metadata.").lower()
        assert "schema" not in text and "backend" not in text
        assert "index.html" in text


class TestTheSingleFileShapeIsUnchanged:
    def test_a_single_html_build_still_gets_its_build_plan(self):
        plan = plan_for("Build a single self-contained HTML page with animations and a palette")
        assert any("index.html" in t.expected_artifacts for t in plan.tasks)
        assert any("screenshot" in t.required_tools for t in plan.tasks)


class TestProportionality:
    def test_an_explanation_is_not_given_a_build_plan(self):
        assert len(plan_for("explain how python decorators work").tasks) <= 3

    def test_a_greeting_gets_no_plan_at_all(self):
        assert plan_for("hi").tasks == []


class TestTheProposalPathIsVisible:
    """The fallback must announce itself.

    The proposal path never fails a job — every error falls through to the deterministic template —
    which is correct, and which is exactly why it went unnoticed for so long. A live TIDEPOOL run
    timed out here and produced the generic build plan while the request's two named behaviours
    (filtering that reorganises the list; a detail view) became no task at all. From outside, that
    plan was indistinguishable from one the model had written for that request.
    """

    def test_a_plan_built_without_a_model_says_it_is_the_template(self):
        from backend.agents.plan_builder import build_plan

        request = "Build a single HTML page called TIDEPOOL with filtering by tide zone"
        plan = build_plan(request, generate_contract(request))
        assert plan.source == "template"
        assert plan.source_detail  # says why, not merely that

    def test_a_failing_planner_records_the_reason_it_fell_back(self):
        from backend.agents.plan_builder import build_plan

        class _Boom:
            def complete(self, *a, **k):
                raise TimeoutError("Request timed out.")

        request = "Build a single HTML page called TIDEPOOL with filtering by tide zone"
        plan = build_plan(request, generate_contract(request), llm=_Boom(), model="glm")
        assert plan.source == "template"
        assert "TimeoutError" in plan.source_detail
        assert plan.tasks  # and the job still gets a usable plan

    def test_an_accepted_proposal_is_marked_as_proposed(self):
        import json

        from backend.agents.plan_builder import build_plan

        proposal = {
            "objective": "Build TIDEPOOL",
            "tasks": [
                {"objective": "Inspect the repository", "required_tools": ["list_directory"]},
                {"objective": "Commit to one direction", "required_tools": ["commit_direction"]},
                {"objective": "Write index.html with the twelve creature records",
                 "required_tools": ["write_file"], "expected_artifacts": ["index.html"]},
                {"objective": "Filtering by tide zone reorganises the list and the count updates",
                 "required_tools": ["edit_file"], "expected_artifacts": ["index.html"]},
                {"objective": "Clicking a creature opens its detail view; closing returns",
                 "required_tools": ["edit_file"], "expected_artifacts": ["index.html"]},
            ],
        }

        class _Planner:
            def complete(self, *a, **k):
                return json.dumps(proposal)

        request = "Build a single HTML page called TIDEPOOL with filtering by tide zone"
        plan = build_plan(request, generate_contract(request), llm=_Planner(), model="glm")
        assert plan.source == "proposed"
        # And the request's own behaviours survived normalisation into the plan.
        objectives = " || ".join(t.objective for t in plan.tasks)
        assert "tide zone" in objectives
        assert "detail view" in objectives


class TestTheProposalPromptDemandsSpecifics:
    """The prompt is the only thing standing between a proposal and the template in other words."""

    def _prompt(self, request: str) -> str:
        from backend.agents.plan_builder import _proposal_prompt

        return _proposal_prompt(request, generate_contract(request), "tidepool")

    def test_it_rejects_the_generic_objectives_by_name(self):
        prompt = self._prompt("Build a page with filtering and a detail view")
        # Naming the actual failed objectives is deliberate: "be specific" is advice, and a list of
        # the exact phrases that were produced instead is a rule.
        assert "Implement the core experience end to end" in prompt
        assert "polish the UI" in prompt

    def test_it_requires_every_named_behaviour_to_become_a_task(self):
        prompt = self._prompt("Build a page with filtering and a detail view")
        assert "in the request's own words" in prompt

    def test_it_forbids_padding_the_plan_to_a_fixed_shape(self):
        prompt = self._prompt("Fix the typo in README.md")
        assert "Do not pad the plan to a shape" in prompt


class TestAFailedProposalSaysWhichFailureItWas:
    """"Not parseable JSON" was reported for a reply that did not exist.

    Measured against a live LUMEN request: completion_tokens=3000, reasoning_tokens=3000,
    finish_reason=length, content_chars=0. The model spent every token thinking and emitted nothing,
    and the log said the JSON was unparseable — true, useless, and it pointed the investigation at
    the parser instead of at the budget. These three failures need three different fixes, so they
    need three different messages.
    """

    REQUEST = "Build a single HTML page called LUMEN, a personal journal and life dashboard"

    def _plan_with(self, reply):
        from backend.agents.plan_builder import build_plan

        class _Planner:
            def complete(self, *a, **k):
                return reply

        return build_plan(self.REQUEST, generate_contract(self.REQUEST),
                          llm=_Planner(), model="glm")

    def test_an_empty_reply_is_reported_as_an_exhausted_budget(self):
        plan = self._plan_with("")
        assert plan.source == "template"
        assert "token budget thinking" in plan.source_detail
        assert "max_tokens=" in plan.source_detail

    def test_a_whitespace_only_reply_counts_as_empty(self):
        # A reasoning model that emits a stray newline before being cut off is the same failure.
        assert "token budget thinking" in self._plan_with("\n  \n").source_detail

    def test_prose_instead_of_json_quotes_what_came_back(self):
        plan = self._plan_with("Sure! Here is how I would approach building LUMEN. First, ...")
        assert "was not JSON" in plan.source_detail
        assert "Sure! Here is how" in plan.source_detail

    def test_a_provider_failure_is_not_confused_with_a_bad_reply(self):
        from backend.agents.plan_builder import build_plan

        class _Down:
            def complete(self, *a, **k):
                raise TimeoutError("Request timed out.")

        plan = build_plan(self.REQUEST, generate_contract(self.REQUEST), llm=_Down(), model="glm")
        assert "TimeoutError" in plan.source_detail
        assert "token budget" not in plan.source_detail

    def test_the_budget_is_sized_for_reasoning_not_for_the_json(self):
        from backend.agents.plan_builder import _PROPOSAL_MAX_TOKENS

        # The measured failure consumed 3,000 tokens of pure reasoning without finishing. A ceiling
        # anywhere near that is a ceiling that silently disables the planner on a real request.
        assert _PROPOSAL_MAX_TOKENS >= 8000

    def test_every_failure_still_returns_a_usable_plan(self):
        # The one invariant that must not break: planning runs before any work, so a planner that
        # can fail a job is worse than no planner.
        for reply in ("", "not json", '{"tasks": []}'):
            plan = self._plan_with(reply)
            assert plan.tasks, reply


class TestPlanningRunsOnAFastModel:
    """The planner must not be the job's reasoning model.

    Measured on the job model, same request, three configurations:

        max_tokens=3,000   reasoning=3,000,  content=0        cut off, plan lost
        max_tokens=16,000  reasoning=13,651, content=10,090   valid, ~4-5 minutes
        max_tokens=32,000  timed out at 180s                  plan lost again

    Room to think is also time spent thinking, so the two knobs cannot be satisfied at once. A model
    that needs 13,651 tokens of deliberation to write nine one-line objectives cannot sit on the
    critical path before any work begins.
    """

    class _Client:
        def __init__(self, tiers):
            self.tiers = tiers
            self.used = None

        def models_for_tier(self, tier):
            return list(self.tiers.get(tier, []))

        def complete(self, messages, *, model=None, **k):
            self.used = model
            return '{"objective": "x", "tasks": []}'

    def test_it_prefers_a_light_model_over_the_job_model(self):
        from backend.agents.plan_builder import _planning_model

        client = self._Client({"light": ["gemini/gemini-3.7-flash"], "balanced": ["other"]})
        assert _planning_model(client, "tokenrouter/z-ai/glm-5.3-free") == "gemini/gemini-3.7-flash"

    def test_it_falls_back_to_balanced_when_no_light_model_is_configured(self):
        from backend.agents.plan_builder import _planning_model

        client = self._Client({"light": [], "balanced": ["groq/qwen/qwen3.6-27b"]})
        assert _planning_model(client, "glm") == "groq/qwen/qwen3.6-27b"

    def test_a_single_provider_setup_still_gets_a_proposal(self):
        # Losing the feature entirely on a machine with one API key would be a worse outcome than a
        # slow plan, so the job's own model remains the last resort.
        from backend.agents.plan_builder import _planning_model

        assert _planning_model(self._Client({}), "glm") == "glm"

    def test_an_explicit_override_wins(self, monkeypatch):
        from backend.agents.plan_builder import _planning_model

        monkeypatch.setenv("CODEXA_PLAN_MODEL", "my/model")
        client = self._Client({"light": ["gemini/gemini-3.7-flash"]})
        assert _planning_model(client, "glm") == "my/model"

    def test_a_client_without_tiers_does_not_break_planning(self):
        from backend.agents.plan_builder import _planning_model

        class _Bare:
            def models_for_tier(self, tier):
                raise AttributeError("no tiers here")

        assert _planning_model(_Bare(), "glm") == "glm"

    def test_the_proposal_call_actually_uses_the_planning_model(self):
        from backend.agents.plan_builder import build_plan

        client = self._Client({"light": ["gemini/gemini-3.7-flash"]})
        request = "Build a page called LUMEN with a journal and a dashboard"
        build_plan(request, generate_contract(request), llm=client, model="glm")
        assert client.used == "gemini/gemini-3.7-flash"


_VALID_PROPOSAL = json.dumps({
    "objective": "Build LUMEN",
    "tasks": [
        {"objective": "Inspect the repository", "required_tools": ["list_directory"]},
        {"objective": "Commit to one direction", "required_tools": ["commit_direction"]},
        {"objective": "Write index.html with the journal and dashboard",
         "required_tools": ["write_file"], "expected_artifacts": ["index.html"]},
        {"objective": "Make search and filtering actually work",
         "required_tools": ["edit_file"], "expected_artifacts": ["index.html"]},
        {"objective": "Run it and look at the rendered output", "required_tools": ["screenshot"]},
    ],
})


class TestPlanningSurvivesAProviderBeingDown:
    """One busy provider must not send every job back to the template.

    The first live attempt at fast planning picked gemini-3.7-flash and got a 503 "high demand" in
    6.8 seconds. With a single candidate that is the whole feature gone for as long as the provider
    is busy — and free, shared endpoints are busy often.
    """

    REQUEST = "Build a page called LUMEN with a journal and a dashboard"

    def _build(self, client):
        from backend.agents.plan_builder import build_plan

        return build_plan(self.REQUEST, generate_contract(self.REQUEST), llm=client, model="glm")

    def test_it_moves_on_to_the_next_model_after_a_503(self):
        class _Flaky:
            def __init__(self):
                self.tried = []

            def models_for_tier(self, tier):
                return {"light": ["busy/flash"], "balanced": ["spare/model"]}.get(tier, [])

            def complete(self, messages, *, model=None, **k):
                self.tried.append(model)
                if model == "busy/flash":
                    raise RuntimeError("503 high demand")
                return _VALID_PROPOSAL

        client = _Flaky()
        plan = self._build(client)
        assert client.tried[:2] == ["busy/flash", "spare/model"]
        assert plan.source == "proposed"

    def test_an_empty_reply_also_moves_on_rather_than_giving_up(self):
        # A model that spends its whole budget thinking has failed just as completely as one that
        # raised; the difference is invisible from the caller's side and must not be treated as
        # "this is the answer".
        class _Silent:
            def __init__(self):
                self.tried = []

            def models_for_tier(self, tier):
                return {"light": ["quiet/model"], "balanced": ["spare/model"]}.get(tier, [])

            def complete(self, messages, *, model=None, **k):
                self.tried.append(model)
                return "" if model == "quiet/model" else '{"objective": "x", "tasks": []}'

        client = _Silent()
        self._build(client)
        assert "spare/model" in client.tried

    def test_the_job_model_is_the_last_resort_not_the_first(self):
        from backend.agents.plan_builder import _planning_models

        class _Client:
            def models_for_tier(self, tier):
                return {"light": ["a"], "balanced": ["b"]}.get(tier, [])

        order = _planning_models(_Client(), "glm")
        assert order[0] != "glm"
        assert order[-1] == "glm"

    def test_the_ring_is_short_enough_not_to_stall_a_job(self):
        from backend.agents.plan_builder import _MAX_PLANNING_ATTEMPTS, _planning_models

        class _Many:
            def models_for_tier(self, tier):
                return [f"{tier}-{i}" for i in range(10)]

        # Every attempt is latency before any work starts, and the fallback is a good plan.
        assert len(_planning_models(_Many(), "glm")) <= _MAX_PLANNING_ATTEMPTS + 1

    def test_when_everything_is_down_the_job_still_gets_a_plan(self):
        class _AllDown:
            def models_for_tier(self, tier):
                return ["a"] if tier == "light" else []

            def complete(self, *a, **k):
                raise RuntimeError("everything is on fire")

        plan = self._build(_AllDown())
        assert plan.source == "template"
        assert plan.tasks
        assert "_ProposalRejected: _ProposalRejected" not in plan.source_detail


class TestEveryProposedPlanCommitsBeforeItBuilds:
    """The anti-divergence step is not optional just because the model forgot it.

    Across three consecutive live trials of the same request, two proposals included a commitment
    task and the third did not — twelve tasks that went from "inspect the project structure"
    straight to "write index.html". That task is the measured fix for the failure this plan system
    exists to prevent: a model given a large open request designs three complete products and
    discards two. A proposal that omits it looks more specific and is quietly less safe.
    """

    def _proposed(self, tasks):
        import json as _json

        from backend.agents.plan_builder import build_plan

        class _Planner:
            def complete(self, *a, **k):
                return _json.dumps({"objective": "Build LUMEN", "tasks": tasks})

        request = "Build a page called LUMEN with a journal and a dashboard"
        return build_plan(request, generate_contract(request), llm=_Planner(), model="glm")

    WITHOUT = [
        {"objective": "Inspect the project structure", "required_tools": ["list_directory"]},
        {"objective": "Write index.html with the home view",
         "required_tools": ["write_file"], "expected_artifacts": ["index.html"]},
        {"objective": "Add search and filtering",
         "required_tools": ["edit_file"], "expected_artifacts": ["index.html"]},
        {"objective": "Add the motion system",
         "required_tools": ["edit_file"], "expected_artifacts": ["index.html"]},
        {"objective": "Run it and screenshot it", "required_tools": ["screenshot"]},
    ]

    def test_a_missing_commitment_task_is_inserted(self):
        plan = self._proposed(self.WITHOUT)
        assert plan.source == "proposed"
        assert any("commit_direction" in t.required_tools for t in plan.tasks)

    def test_it_lands_before_the_first_task_that_writes_anything(self):
        plan = self._proposed(self.WITHOUT)
        commit_at = next(i for i, t in enumerate(plan.tasks) if "commit_direction" in t.required_tools)
        first_artifact = next(i for i, t in enumerate(plan.tasks) if t.expected_artifacts)
        assert commit_at < first_artifact

    def test_a_proposal_that_already_commits_is_left_alone(self):
        with_commit = [
            {"objective": "Inspect the project", "required_tools": ["list_directory"]},
            {"objective": "Decide the visual direction", "required_tools": ["commit_direction"]},
        ] + self.WITHOUT[1:]
        plan = self._proposed(with_commit)
        commits = [t for t in plan.tasks if "commit_direction" in t.required_tools]
        assert len(commits) == 1
        assert commits[0].objective == "Decide the visual direction"

    def test_a_plan_naming_no_artifacts_still_gets_one_early(self):
        no_artifacts = [
            {"objective": "Inspect the project", "required_tools": ["list_directory"]},
            {"objective": "Build the thing", "required_tools": ["write_file"]},
            {"objective": "Check it", "required_tools": ["screenshot"]},
            {"objective": "Fix what is broken", "required_tools": ["edit_file"]},
            {"objective": "Look again", "required_tools": ["screenshot"]},
        ]
        plan = self._proposed(no_artifacts)
        at = next(i for i, t in enumerate(plan.tasks) if "commit_direction" in t.required_tools)
        assert at == 1  # after the look, before the work

    def test_the_dependency_chain_survives_the_insertion(self):
        # depends_on ids are generated from real task ids; inserting a task after they were built
        # would leave a chain pointing at the wrong neighbour, and plan.is_ready treats an unknown
        # dependency as never satisfied — a permanently stuck plan.
        plan = self._proposed(self.WITHOUT)
        ids = {t.id for t in plan.tasks}
        for task in plan.tasks:
            for dep in task.depends_on:
                assert dep in ids, f"{task.objective} depends on a task that does not exist"

    def test_a_question_is_not_given_a_commitment_task(self):
        import json as _json

        from backend.agents.plan_builder import build_plan

        class _Planner:
            def complete(self, *a, **k):
                return _json.dumps({"objective": "Answer", "tasks": [
                    {"objective": "Read the file", "required_tools": ["read_file"]},
                    {"objective": "Answer the question in chat", "required_tools": []},
                ]})

        request = "what does the plan builder do?"
        plan = build_plan(request, generate_contract(request), llm=_Planner(), model="glm")
        assert not any("commit_direction" in t.required_tools for t in plan.tasks)
