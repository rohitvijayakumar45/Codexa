"""A question must not be planned as an exploration.

Measured on httpx with GLM: "What does the send method on the httpx Client class do, and which
internal functions does it call?" was classified ANALYZE, sent to the plan proposer, and came back as
six tasks — search, read all of _client.py (five 400-line windows), locate, read again, "extract the
calls with Python AST" through a tool the model does not have, then write analysis.txt into the
repository. The graph context had already named send's callees and lookup_symbol answered each in one
call. The deterministic ANALYZE shape was no better: it required list_directory, search_code AND
read_file, and a task's required tools must all be called.
"""

from backend.agents.plan_builder import build_plan, fallback_plan
from backend.agents.task import TaskIntent, generate_contract

QUESTION = "What does the send method on the httpx Client class do, and which internal functions does it call?"


class _ExplorationPlanner:
    """Proposes the plan that was observed live. Records whether it was asked at all."""

    def __init__(self):
        self.called = False

    def complete(self, *a, **k):
        import json

        self.called = True
        return json.dumps({"objective": "Analyse send", "tasks": [
            {"objective": "Search for the Client class", "required_tools": ["search_code"]},
            {"objective": "Read the file containing Client", "required_tools": ["read_file"]},
            {"objective": "Extract calls with Python AST", "required_tools": ["run_python"]},
            {"objective": "Write the summary to analysis.txt", "required_tools": ["write_file"],
             "expected_artifacts": ["analysis.txt"]},
        ]})


def test_the_question_is_classified_as_analysis():
    assert generate_contract(QUESTION).intent is TaskIntent.ANALYZE


def test_a_question_is_one_task_with_no_mandatory_exploration():
    plan = fallback_plan(QUESTION, generate_contract(QUESTION))
    assert len(plan.tasks) == 1
    assert plan.tasks[0].required_tools == []
    assert plan.tasks[0].expected_artifacts == []


def test_a_question_never_asks_a_model_for_a_plan():
    planner = _ExplorationPlanner()
    plan = build_plan(QUESTION, generate_contract(QUESTION), llm=planner, model="glm")
    assert planner.called is False
    assert len(plan.tasks) == 1
    assert "no proposal" in plan.source_detail


def test_an_explanation_is_planned_the_same_way():
    request = "Explain how the retry logic works"
    planner = _ExplorationPlanner()
    plan = build_plan(request, generate_contract(request), llm=planner, model="glm")
    assert planner.called is False
    assert all(not t.required_tools and not t.expected_artifacts for t in plan.tasks)


def test_a_build_request_still_gets_a_proposal():
    request = "Build a single HTML page called TIDEPOOL with filtering by tide zone"
    planner = _ExplorationPlanner()
    build_plan(request, generate_contract(request), llm=planner, model="glm")
    assert planner.called is True
