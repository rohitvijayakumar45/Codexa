"""Tests for task classification, contract generation, and completion validation."""

from backend.agents.task import (
    TaskContract,
    TaskIntent,
    build_task_prompt,
    classify_intent,
    generate_contract,
    is_bare_continuation,
    last_substantive_user_message,
    resolve_contract_source,
    validate_completion,
)


# ── Intent classification ───────────────────────────────────────────────────

class TestCreateIntent:
    def test_build_html(self):
        assert classify_intent("Build a single HTML benchmark page") == TaskIntent.CREATE

    def test_create_react_component(self):
        assert classify_intent("Create a React component for the header") == TaskIntent.CREATE

    def test_make_landing_page(self):
        assert classify_intent("Make a landing page") == TaskIntent.CREATE

    def test_generate_dashboard(self):
        assert classify_intent("Generate a dashboard") == TaskIntent.CREATE

    def test_implement_api_endpoint(self):
        assert classify_intent("Implement a new API endpoint") == TaskIntent.CREATE

    def test_scaffold_project(self):
        assert classify_intent("Scaffold a new Next.js project") == TaskIntent.CREATE


class TestModifyIntent:
    def test_fix_bug(self):
        assert classify_intent("Fix the auth bug") == TaskIntent.MODIFY

    def test_update_component(self):
        assert classify_intent("Update the header component") == TaskIntent.MODIFY

    def test_refactor_service(self):
        assert classify_intent("Refactor the user service") == TaskIntent.MODIFY

    def test_improve_performance(self):
        assert classify_intent("Improve the query performance") == TaskIntent.MODIFY


class TestDeleteIntent:
    def test_delete_file(self):
        assert classify_intent("Delete the old config file") == TaskIntent.DELETE

    def test_remove_component(self):
        assert classify_intent("Remove the deprecated component") == TaskIntent.DELETE


class TestRunIntent:
    def test_run_tests(self):
        assert classify_intent("Run the tests") == TaskIntent.RUN

    def test_build_project(self):
        # "build" matches CREATE first — "build the project" = create it
        assert classify_intent("Build the project") == TaskIntent.CREATE

    def test_npm_install(self):
        assert classify_intent("npm install the dependencies") == TaskIntent.RUN


class TestSearchIntent:
    def test_web_search(self):
        assert classify_intent("Search the web for best practices") == TaskIntent.SEARCH

    def test_google(self):
        assert classify_intent("Google how to use playwright") == TaskIntent.SEARCH


class TestAnalyzeIntent:
    def test_analyze_codebase(self):
        assert classify_intent("Analyse the codebase structure") == TaskIntent.ANALYZE

    def test_what_does_function_do(self):
        assert classify_intent("What does this function do") == TaskIntent.ANALYZE

    def test_show_me_files(self):
        assert classify_intent("Show me the project files") == TaskIntent.ANALYZE


class TestExplainIntent:
    def test_explain_auth(self):
        assert classify_intent("Explain how auth works") == TaskIntent.EXPLAIN

    def test_how_does_this_work(self):
        assert classify_intent("How does the caching layer work") == TaskIntent.EXPLAIN

    def test_what_is_difference(self):
        assert classify_intent("What is the difference between X and Y") == TaskIntent.EXPLAIN


class TestConversationIntent:
    def test_hi(self):
        assert classify_intent("hi") == TaskIntent.CONVERSATION

    def test_hello(self):
        assert classify_intent("hello") == TaskIntent.CONVERSATION

    def test_thanks(self):
        assert classify_intent("thanks") == TaskIntent.CONVERSATION


# ── Contract generation ─────────────────────────────────────────────────────

class TestContractGeneration:
    def test_create_requires_write_file(self):
        contract = generate_contract("Build an HTML benchmark page")
        assert contract.intent == TaskIntent.CREATE
        assert "write_file" in contract.required_tools

    def test_create_ui_has_design_in_workflow(self):
        contract = generate_contract("Build a landing page with React")
        assert "write_file" in contract.required_tools
        assert "load design guidance" in " ".join(contract.suggested_workflow).lower()

    def test_modify_requires_edit(self):
        contract = generate_contract("Fix the auth bug")
        assert contract.intent == TaskIntent.MODIFY
        assert "edit_file" in contract.required_tools

    def test_delete_requires_delete(self):
        contract = generate_contract("Delete the old config")
        assert "delete_file" in contract.required_tools

    def test_run_requires_command(self):
        contract = generate_contract("Run the tests")
        assert "run_command" in contract.required_tools

    def test_search_requires_web_search(self):
        contract = generate_contract("Search the web for docs")
        assert "web_search" in contract.required_tools

    def test_explain_has_no_required_tools(self):
        contract = generate_contract("Explain how auth works")
        assert contract.required_tools == []

    def test_conversation_has_no_required_tools(self):
        contract = generate_contract("hi")
        assert contract.required_tools == []


# ── Task prompt building ────────────────────────────────────────────────────

class TestTaskPrompt:
    def test_create_has_workflow(self):
        contract = generate_contract("Build an HTML benchmark")
        prompt = build_task_prompt(contract)
        assert "CREATE_ARTIFACT" in prompt
        assert "write_file" in prompt
        assert "SUGGESTED WORKFLOW" in prompt

    def test_conversation_returns_empty(self):
        contract = generate_contract("hi")
        prompt = build_task_prompt(contract)
        assert prompt == ""

    def test_constraints_present(self):
        contract = generate_contract("Build a landing page")
        prompt = build_task_prompt(contract)
        assert "CONSTRAINTS" in prompt


# ── Completion validation ───────────────────────────────────────────────────

class TestCompletionValidation:
    def test_create_passes_when_write_file_called(self):
        # Deliberately non-UI (no is_ui match) - a UI CREATE task also requires screenshot, tested
        # separately below.
        contract = generate_contract("Create a Python script that parses CSV files")
        assert contract.required_tools == ["write_file"]
        passed, _ = validate_completion(contract, ["write_file"])
        assert passed is True

    def test_create_fails_without_write_file(self):
        contract = generate_contract("Build an HTML page")
        passed, msg = validate_completion(contract, ["list_directory", "read_file"])
        assert passed is False
        assert "write_file" in msg

    def test_modify_passes_with_edit_file(self):
        contract = generate_contract("Fix the bug")
        passed, _ = validate_completion(contract, ["edit_file"])
        assert passed is True

    def test_modify_passes_with_apply_patch(self):
        contract = generate_contract("Fix the bug")
        passed, _ = validate_completion(contract, ["apply_patch"])
        assert passed is True

    def test_modify_passes_with_write_file(self):
        contract = generate_contract("Fix the bug")
        passed, _ = validate_completion(contract, ["write_file"])
        assert passed is True

    def test_modify_fails_without_any_edit_tool(self):
        contract = generate_contract("Fix the bug")
        passed, msg = validate_completion(contract, ["read_file", "search_code"])
        assert passed is False

    def test_explain_always_passes(self):
        contract = generate_contract("Explain how auth works")
        passed, _ = validate_completion(contract, [])
        assert passed is True

    def test_conversation_always_passes(self):
        contract = generate_contract("hi")
        passed, _ = validate_completion(contract, [])
        assert passed is True

    def test_correction_message_is_actionable(self):
        contract = generate_contract("Build a React component")
        passed, msg = validate_completion(contract, ["list_directory"])
        assert passed is False
        assert "write_file" in msg
        assert "NOT complete" in msg

    def test_delegate_task_satisfies_write_file_requirement(self):
        # Regression: delegate_task's own worker sub-loop calls write_file internally
        # (backend/agents/tools.py: _delegate_task), invisible to the outer job's tools_called -
        # only "delegate_task" itself lands there. Without crediting it, delegating (which the
        # tool description now actively encourages) would look like the task was never done.
        contract = generate_contract("Build a single HTML benchmark")
        passed, _ = validate_completion(contract, ["tree", "delegate_task"])
        assert passed is True

    def test_delegate_task_satisfies_modify_requirement_too(self):
        contract = generate_contract("Fix the bug")
        passed, _ = validate_completion(contract, ["delegate_task"])
        assert passed is True

    def test_ui_create_task_requires_screenshot_in_addition_to_write_file(self):
        contract = generate_contract("Build a single HTML benchmark page")
        assert set(contract.required_tools) == {"write_file", "screenshot"}

    def test_ui_create_task_fails_with_write_file_but_no_screenshot(self):
        # Regression for the exact live failure: a UI build wrote real files but never looked at
        # its own output before declaring done.
        contract = generate_contract("Build a single HTML benchmark page")
        passed, msg = validate_completion(contract, ["write_file"])
        assert passed is False
        assert "screenshot" in msg

    def test_ui_create_task_passes_once_both_are_called(self):
        contract = generate_contract("Build a single HTML benchmark page")
        passed, _ = validate_completion(contract, ["write_file", "screenshot"])
        assert passed is True

    def test_ui_modify_requires_screenshot_alongside_any_edit_tool(self):
        # Exercises the fixed MODIFY early-return: calling write_file (one of the interchangeable
        # edit tools) must NOT silently satisfy screenshot too.
        contract = generate_contract("Redesign the login page layout")
        assert "screenshot" in contract.required_tools
        passed, msg = validate_completion(contract, ["write_file"])
        assert passed is False
        assert "screenshot" in msg

    def test_ui_modify_passes_with_any_edit_tool_plus_screenshot(self):
        contract = generate_contract("Redesign the login page layout")
        for edit_tool in ("edit_file", "apply_patch", "write_file"):
            passed, _ = validate_completion(contract, [edit_tool, "screenshot"])
            assert passed is True, edit_tool

    def test_non_ui_modify_still_has_no_screenshot_requirement(self):
        contract = generate_contract("Fix the off-by-one bug in the pagination logic")
        assert "screenshot" not in contract.required_tools

    def test_delegate_task_does_not_satisfy_an_unrelated_requirement(self):
        # delegate_task only covers mutating file/dir ops (see _DELEGATABLE_TOOLS) - a SEARCH
        # task's web_search requirement isn't satisfied just because some file got delegated.
        contract = generate_contract("Search the web for the latest React release notes")
        assert contract.required_tools == ["web_search"]
        passed, _ = validate_completion(contract, ["delegate_task"])
        assert passed is False


# ── Bare-continuation detection and contract inheritance ────────────────────
#
# Regression coverage for a live bug: a stalled/incomplete CREATE task, nudged along by the user
# typing "continue"/"hi"/a typo of either, silently lost its required_tools because
# generate_contract runs fresh per chat send and classifies a bare nudge as CONVERSATION on its
# own — letting the model narrate a fabricated "I created the file" with nothing left to check it
# against. See backend/agents/task.py: is_bare_continuation, last_substantive_user_message,
# resolve_contract_source, and their call sites in backend/chat/api.py and backend/agents/jobs.py.

class TestIsBareContinuation:
    def test_continue_is_bare(self):
        assert is_bare_continuation("continue") is True

    def test_typo_of_continue_is_bare(self):
        assert is_bare_continuation("continye") is True  # the actual typo from the live bug report

    def test_bare_greeting_is_bare(self):
        assert is_bare_continuation("hi") is True

    def test_substantive_message_is_never_bare_even_if_short(self):
        assert is_bare_continuation("Fix the bug") is False

    def test_long_message_that_still_classifies_as_conversation_is_not_bare(self):
        # Long free-form chat is real conversational content, not a content-free nudge - only
        # SHORT + CONVERSATION-classified counts as a bare continuation.
        long_chat = "I appreciate the help, thanks a lot for walking me through all of that"
        assert classify_intent(long_chat) == TaskIntent.CONVERSATION
        assert is_bare_continuation(long_chat) is False


class TestLastSubstantiveUserMessage:
    def test_finds_the_real_task_behind_a_single_nudge(self):
        messages = [
            {"role": "user", "content": "Create a new project called pulse-dashboard"},
            {"role": "assistant", "content": "Sure, starting now."},
            {"role": "user", "content": "continue"},
        ]
        # Caller passes history with the current turn already excluded; "continue" itself is bare,
        # so the last SUBSTANTIVE message is the original CREATE request.
        assert last_substantive_user_message(messages[:-1]) == "Create a new project called pulse-dashboard"

    def test_skips_any_number_of_stacked_nudges(self):
        messages = [
            {"role": "user", "content": "Create a new project called pulse-dashboard"},
            {"role": "user", "content": "continye"},
            {"role": "user", "content": "hi"},
            {"role": "user", "content": "hi"},
            {"role": "user", "content": "continue"},
        ]
        assert last_substantive_user_message(messages[:-1]) == "Create a new project called pulse-dashboard"

    def test_no_prior_substantive_message_returns_none(self):
        assert last_substantive_user_message([{"role": "user", "content": "hi"}]) is None

    def test_empty_history_returns_none(self):
        assert last_substantive_user_message([]) is None

    def test_non_user_messages_are_ignored(self):
        messages = [
            {"role": "assistant", "content": "Create a new project called pulse-dashboard"},
            {"role": "user", "content": "continue"},
        ]
        assert last_substantive_user_message(messages) is None  # only the assistant one is substantive-looking


class TestResolveContractSource:
    def test_bare_nudge_inherits_the_prior_tasks_contract(self):
        prior_messages = [{"role": "user", "content": "Create a new project called pulse-dashboard"}]

        source = resolve_contract_source("continue", prior_messages)

        assert source == "Create a new project called pulse-dashboard"
        assert generate_contract(source).required_tools == ["write_file"]

    def test_substantive_message_is_used_as_is(self):
        assert resolve_contract_source("Fix the bug", []) == "Fix the bug"

    def test_bare_nudge_with_no_prior_task_falls_back_to_itself(self):
        assert resolve_contract_source("hi", []) == "hi"

    def test_end_to_end_regression_for_the_live_bug_report(self):
        # Reproduces the exact shape of the reported conversation: a CREATE request, several bare
        # nudges, then the turn that must still enforce write_file rather than silently accepting
        # a narrated-but-never-written completion.
        prior_messages = [
            {"role": "user", "content": 'Create a new project called "pulse-dashboard" - a single self-contained HTML file'},
            {"role": "assistant", "content": "I'll build the pulse-dashboard now."},
            {"role": "user", "content": "continye"},
            {"role": "assistant", "content": "Proceeding with setup."},
            {"role": "user", "content": "continue"},
        ]

        contract = generate_contract(resolve_contract_source("continue", prior_messages))

        assert contract.intent == TaskIntent.CREATE
        assert contract.required_tools == ["write_file"]
        passed, _ = validate_completion(contract, [])  # no tool ever actually called this turn
        assert passed is False


class TestEarliestMatchWinsOverFixedPriority:
    """Regression coverage for a real, observed bug: a long CREATE-prefixed spec prompt containing
    the word "explain" thousands of characters later (inside "Do NOT simply explain the
    architecture, implement it") classified as EXPLAIN_CONCEPT — required_tools=[] — because the
    old classify_intent scanned patterns in a FIXED priority order and stopped at the first one that
    matched ANYWHERE in the text, regardless of position. With nothing required, the job accepted
    the model's first plain-text reply as "done" no matter how little of the actual build had
    happened — the task just stopped, silently, with no error."""

    def test_create_at_position_zero_beats_explain_mentioned_much_later(self):
        message = (
            "Build a breathtaking, production-quality full-stack web application called ORBIT.\n"
            + ("Implement the full Kanban board with drag and drop. " * 50)
            + "IMPLEMENTATION RULE: Do NOT simply explain the architecture, actually implement it."
        )
        assert classify_intent(message) == TaskIntent.CREATE

    def test_explain_at_position_zero_still_wins_when_it_leads(self):
        # The fix must not simply flip the old priority order - it picks whichever comes FIRST.
        message = "Explain how the caching layer works, then build a small demo of it."
        assert classify_intent(message) == TaskIntent.EXPLAIN

    def test_how_does_x_work_ties_explain_and_analyze_at_the_same_position(self):
        # "how does" matches both EXPLAIN's and ANALYZE's alternatives at the same start index -
        # the tie-break must still prefer EXPLAIN, exactly like the old fixed priority order did.
        assert classify_intent("How does the retry logic work?") == TaskIntent.EXPLAIN


class TestALineLeadingImperativeBeatsAHeadingNoun:
    """A real, costly failure: a build request whose markdown title happened to end in the word
    "Benchmark" classified as ANALYZE, because "benchmark" is a legitimate analysis verb
    ("benchmark this function") and it sat 11 characters before the "Build an ..." opening the very
    next line. ANALYZE carries required_tools=[], so validate_completion had nothing to enforce and
    the job reported DONE after 48 minutes with zero files written.

    Position alone cannot separate these; a verb that OPENS a line is someone stating what they
    want, while the same word inside a heading is usually incidental.
    """

    def test_a_title_ending_in_benchmark_does_not_hijack_a_build_request(self):
        message = (
            "# ATLAS — Single-HTML Frontend Benchmark\n\n"
            "Build an exceptionally polished, production-quality single-page application "
            "called ATLAS as one self-contained HTML file."
        )
        assert classify_intent(message) == TaskIntent.CREATE

    def test_that_request_gets_a_contract_that_actually_requires_files(self):
        # The whole point of the classification: a build with no required tools cannot be
        # validated, so the job can "succeed" having produced nothing at all.
        message = (
            "# ATLAS — Single-HTML Frontend Benchmark\n\n"
            "Build a polished single-page application as one self-contained HTML file."
        )
        contract = generate_contract(message)
        assert "write_file" in contract.required_tools

    def test_other_analysis_nouns_in_a_heading_do_not_hijack_either(self):
        for noun in ("Review", "Audit", "Profile", "Comparison of Approaches"):
            message = f"# Project {noun}\n\nCreate a new dashboard page with three charts."
            assert classify_intent(message) == TaskIntent.CREATE, noun

    def test_a_genuine_analysis_request_is_still_analysis(self):
        assert classify_intent("Benchmark the render loop and report the timings") == TaskIntent.ANALYZE
        assert classify_intent("Review this module for correctness") == TaskIntent.ANALYZE

    def test_a_heading_that_genuinely_asks_for_analysis_still_wins(self):
        # Line-leading is the signal, not "headings never count" — an ANALYZE verb that OPENS the
        # document should still take precedence over a build verb further down.
        message = "Analyze the current architecture\n\nThen build a diagram of what you find."
        assert classify_intent(message) == TaskIntent.ANALYZE

    def test_earliest_still_breaks_ties_within_the_same_line_position(self):
        # Both candidates line-leading: the earlier one wins, preserving the previous fix.
        assert classify_intent("Build a parser\nExplain how it works") == TaskIntent.CREATE
