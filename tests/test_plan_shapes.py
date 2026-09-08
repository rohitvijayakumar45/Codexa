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
