"""Tests for dynamic tool grouping — intent classification and tool selection."""

from backend.agents.tools import (
    TOOL_SCHEMAS,
    classify_intent,
    tool_groups,
    tools_for_groups,
)

# ── Tool group coverage ──────────────────────────────────────────────────────

ALL_TOOL_NAMES = {t["function"]["name"] for t in TOOL_SCHEMAS}


def test_all_groups_are_subsets_of_tool_schemas():
    """Every tool referenced by a group must exist in TOOL_SCHEMAS."""
    for group_name, group_tools in tool_groups.items():
        for tool_name in group_tools:
            assert tool_name in ALL_TOOL_NAMES, (
                f"Group '{group_name}' references unknown tool '{tool_name}'"
            )


def test_all_tools_covered_by_at_least_one_group():
    """No tool should be orphaned — every tool must appear in at least one group."""
    covered = set()
    for group_tools in tool_groups.values():
        covered.update(group_tools)
    orphaned = ALL_TOOL_NAMES - covered
    assert not orphaned, f"Tools not in any group: {orphaned}"


def test_repo_group_included_for_code_questions():
    """Repo group included for code-related questions, but not greetings or pure external searches."""
    messages = [
        "create a React component",
        "run the tests",
        "take a screenshot",
        "commit my changes",
        "what does this function do",
    ]
    for msg in messages:
        groups = classify_intent(msg)
        assert "repo" in groups, f"'repo' missing for '{msg}': {groups}"


def test_external_search_skips_repo():
    """Pure external searches don't need repo context."""
    groups = classify_intent("search the web for best practices")
    assert groups == ["external"]


# ── Intent classification ───────────────────────────────────────────────────

class TestCodeGroup:
    def test_create(self):
        groups = classify_intent("create a React component")
        assert "code" in groups

    def test_edit(self):
        groups = classify_intent("edit the login form")
        assert "code" in groups

    def test_fix(self):
        groups = classify_intent("fix the auth bug")
        assert "code" in groups

    def test_refactor(self):
        groups = classify_intent("refactor the user service")
        assert "code" in groups

    def test_scaffold(self):
        groups = classify_intent("scaffold the entire project")
        assert "code" in groups

    def test_write(self):
        groups = classify_intent("write a new utility function")
        assert "code" in groups


class TestRuntimeGroup:
    def test_run_tests(self):
        groups = classify_intent("run the tests")
        assert "runtime" in groups

    def test_typecheck(self):
        groups = classify_intent("check for type errors")
        assert "runtime" in groups

    def test_lint(self):
        groups = classify_intent("lint the codebase")
        assert "runtime" in groups

    def test_build(self):
        groups = classify_intent("build the project")
        assert "runtime" in groups

    def test_npm(self):
        groups = classify_intent("install dependencies with npm")
        assert "runtime" in groups


class TestBrowserGroup:
    def test_screenshot(self):
        groups = classify_intent("take a screenshot of the homepage")
        assert "browser" in groups

    def test_visual_quality(self):
        groups = classify_intent("make this look more premium")
        assert "browser" in groups

    def test_inspect_page(self):
        groups = classify_intent("inspect the page for accessibility")
        assert "browser" in groups


class TestGitGroup:
    def test_commit(self):
        groups = classify_intent("commit my changes")
        assert "git" in groups

    def test_diff(self):
        groups = classify_intent("git diff")
        assert "git" in groups

    def test_branch(self):
        groups = classify_intent("create a new branch")
        assert "git" in groups

    def test_status(self):
        groups = classify_intent("what's the git status")
        assert "git" in groups


class TestExternalGroup:
    def test_web_search(self):
        groups = classify_intent("search the web for best practices")
        assert "external" in groups

    def test_google(self):
        groups = classify_intent("google how to use playwright")
        assert "external" in groups


class TestRepoGroup:
    def test_pure_question(self):
        groups = classify_intent("what does this function do")
        assert groups == ["repo"]

    def test_explain(self):
        groups = classify_intent("explain how auth works")
        assert groups == ["repo"]

    def test_greeting_returns_no_tools(self):
        """Greetings should return no tools at all, not even repo."""
        for greeting in ["hi", "hello", "hey", "thanks", "ok", "got it"]:
            groups = classify_intent(greeting)
            assert groups == [], f"'{greeting}' should return no tools, got {groups}"

    def test_describe(self):
        groups = classify_intent("describe the project structure")
        assert groups == ["repo"]


# ── Tool selection ───────────────────────────────────────────────────────────

def test_tools_for_single_group():
    tools = tools_for_groups(["git"])
    names = {t["function"]["name"] for t in tools}
    assert "git_status" in names
    assert "git_diff" in names
    assert "write_file" not in names


def test_tools_for_multiple_groups():
    tools = tools_for_groups(["code", "runtime"])
    names = {t["function"]["name"] for t in tools}
    assert "write_file" in names
    assert "run_tests" in names
    assert "git_status" not in names


def test_tools_for_empty_group():
    tools = tools_for_groups([])
    assert tools == []


def test_repo_always_has_read_tools():
    tools = tools_for_groups(["repo"])
    names = {t["function"]["name"] for t in tools}
    assert "read_file" in names
    assert "search_code" in names
    assert "tree" in names
    assert "list_symbols" in names


def test_code_group_has_editing_tools():
    tools = tools_for_groups(["code"])
    names = {t["function"]["name"] for t in tools}
    assert "write_file" in names
    assert "edit_file" in names
    assert "apply_patch" in names
    assert "create_files" in names


def test_runtime_group_has_validation():
    tools = tools_for_groups(["runtime"])
    names = {t["function"]["name"] for t in tools}
    assert "run_tests" in names
    assert "typecheck" in names
    assert "lint" in names
    assert "build" in names


def test_browser_group_has_visual_tools():
    tools = tools_for_groups(["browser"])
    names = {t["function"]["name"] for t in tools}
    assert "screenshot" in names
    assert "inspect_element" in names
    assert "inspect_page" in names
    assert "browser_click" in names


# ── Dynamic grouping reduces tool count ──────────────────────────────────────

def test_dynamic_grouping_reduces_tool_count():
    """Intent classification must reduce tools from full set to a subset."""
    full_count = len(TOOL_SCHEMAS)
    messages_and_expected_max = [
        ("hi", full_count),  # should be 0
        ("fix the auth bug", full_count),
        ("run the tests", full_count),
        ("take a screenshot", full_count),
        ("commit my changes", full_count),
    ]
    for msg, _ in messages_and_expected_max:
        groups = classify_intent(msg)
        tools = tools_for_groups(groups)
        assert len(tools) < full_count, (
            f"'{msg}' should use fewer tools than the full set "
            f"({len(tools)} vs {full_count})"
        )


def test_greetings_use_zero_tools():
    """Pure greetings must not send any tool schemas to the model."""
    greetings = ["hi", "hello", "hey", "thanks", "ok", "cool", "got it",
                 "sounds good", "good morning", "how are you"]
    for msg in greetings:
        groups = classify_intent(msg)
        tools = tools_for_groups(groups)
        assert len(tools) == 0, (
            f"'{msg}' should use 0 tools, got {len(tools)}: {[t['function']['name'] for t in tools]}"
        )
