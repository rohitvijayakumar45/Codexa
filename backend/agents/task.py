"""Intent classifier, task contract, and completion validator.

Orchestrates the agent loop by:
1. Classifying user intent into a task type (CREATE, MODIFY, DELETE, RUN, ANALYZE, SEARCH, EXPLAIN)
2. Generating a task contract with required tools, success criteria, and constraints
3. Validating that the model completed the task (required tools were called, artifacts created)

This enforces the principle: "Never confuse generating an implementation with implementing it."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class TaskIntent(str, Enum):
    CREATE = "CREATE_ARTIFACT"
    MODIFY = "MODIFY_ARTIFACT"
    DELETE = "DELETE_ARTIFACT"
    RUN = "RUN_EXECUTION"
    ANALYZE = "ANALYZE_REPOSITORY"
    SEARCH = "SEARCH_EXTERNAL"
    EXPLAIN = "EXPLAIN_CONCEPT"
    CONVERSATION = "CONVERSATION"


# Mirrors the mutating subset of backend/agents/tools.py's _EXECUTOR_TOOL_NAMES (the tools a
# delegated worker may use) — kept local rather than imported to avoid a new task.py -> tools.py
# coupling for one small set. Used by validate_completion below.
_DELEGATABLE_TOOLS = {"write_file", "edit_file", "delete_file", "move_file", "create_directory", "run_command"}


@dataclass
class TaskContract:
    intent: TaskIntent
    required_tools: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    suggested_workflow: list[str] = field(default_factory=list)


# ── Intent detection patterns ───────────────────────────────────────────────

_CREATE = re.compile(
    r"\b(build|create|make|scaffold|generate|implement|develop|construct|produce|"
    r"write|add a new|set up|setup a|spin up|spin up a|stand up|stand up a) "
    r"(a |an |the |my |your |one |single |new |simple |basic |full |complete |"
    r"simple |starter )?",
    re.IGNORECASE,
)

_MODIFY = re.compile(
    r"\b(fix|modify|update|change|refactor|rename|replace|patch|migrate|"
    r"improve|enhance|extend|upgrade|adjust|tweak|optimi[sz]e|rewrite|redesign|"
    r"reorganise|reorganize|restructure|overhaul) "
    r"(the |this |that |my |your |a |an )?",
    re.IGNORECASE,
)

_DELETE = re.compile(
    r"\b(delete|remove|drop|clear|erase|destroy|clean up|clean out|get rid of) "
    r"(the |this |that |my |your |a |an )?",
    re.IGNORECASE,
)

_RUN = re.compile(
    r"\b(run|execute|start|launch|deploy|install|build|compile|serve|"
    r"test|lint|typecheck|type-check|check|verify|validate|build a|"
    r"npm |pip |yarn |pnpm |docker |make |cargo )",
    re.IGNORECASE,
)

_ANALYZE = re.compile(
    r"\b(analy[sz]e|inspect|examine|review|audit|investigate|explore|"
    r"understand|map out|trace|profile|benchmark|measure|compare|"
    r"what (does|do|is|are)|how (does|do|is|are)|where (is|are|do|does)|"
    r"show me|list|describe the structure|give me an overview)",
    re.IGNORECASE,
)

_SEARCH = re.compile(
    r"\b(search the web|google|look (it )?up online|find online|"
    r"stackoverflow|documentation|docs online|npm package|pip package|"
    r"what (is|are) the best|recommend|suggest|what should I use)",
    re.IGNORECASE,
)

_EXPLAIN = re.compile(
    r"\b(explain|describe|tell me about|how (does|do|would|could|should)|"
    r"why (does|do|is|are|would|could|should)|what (is|are) (a |an |the )?|"
    r"what does .+ mean|what is the difference|compare .+ and|"
    r"walk me through|walkthrough|overview of|summary of|"
    r"help me understand|teach me)",
    re.IGNORECASE,
)

# ── Artifact detection ──────────────────────────────────────────────────────

_HTML_FILE = re.compile(r"\b(html|webpage|page|landing|site|website|benchmark|dashboard)\b", re.IGNORECASE)
_REACT_FILE = re.compile(r"\b(react|component|tsx?|jsx?|vue|svelte|angular)\b", re.IGNORECASE)
_PYTHON_FILE = re.compile(r"\b(python|\.py|script|module|package|fastapi|django|flask)\b", re.IGNORECASE)
_CONFIG_FILE = re.compile(r"\b(config|configuration|settings|\.json|\.yaml|\.toml|\.env|dockerfile)\b", re.IGNORECASE)
_ANY_FILE = re.compile(
    r"\b(file|document|readme|changelog|license|documentation|doc|"
    r"benchmark|test file|test case)\b",
    re.IGNORECASE,
)

# ── UI-specific detection ───────────────────────────────────────────────────

_UI_TASK = re.compile(
    r"\b(ui|ux|interface|frontend|front-end|landing|page|layout|design|"
    r"look|feel|style|css|tailwind|animation|responsive|mobile|"
    r"screenshot|visual|pixel|mockup|wireframe|prototype)",
    re.IGNORECASE,
)


def is_bare_continuation(message: str, system_note: str = "") -> bool:
    """True for a short nudge ("continue", "hi", a stall retry, a typo of either) that carries no
    task information of its own. Gated on length rather than a fixed phrase list so it also catches
    typos ("continye") a phrase match would miss.

    Why this matters: generate_contract(message) is called fresh for every new job — one per chat
    send, not once per conversation. A bare nudge sent mid-task (the model stalled, or silently
    never called a required tool, and the user typed "continue"/"hi" to prod it) classifies as
    CONVERSATION on its own, which carries required_tools=[] — silently dropping whatever tool
    requirement the actual outstanding task had. The caller (backend/agents/jobs.py's
    JobManager.start) uses this to look back for the last substantive message and contract against
    that instead, rather than letting a one-word nudge erase task enforcement."""
    return len(message.strip()) <= 24 and classify_intent(message, system_note) == TaskIntent.CONVERSATION


def last_substantive_user_message(messages: list[dict]) -> str | None:
    """Scans prior conversation history (oldest to newest, read in reverse) for the last user
    message that wasn't itself a bare continuation — skipping over any number of stacked nudges
    ("continue", "hi", "continue" again) to find the real outstanding task. `messages` is the full
    history as sent to the model (role/content dicts); the caller excludes the current turn's own
    message before passing this in."""
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        text = m.get("content")
        if not isinstance(text, str) or not text.strip():
            continue
        if not is_bare_continuation(text):
            return text
    return None


def resolve_contract_source(last_user_text: str, prior_messages: list[dict]) -> str:
    """The text a task contract should actually be generated from: last_user_text itself, unless
    it's a bare continuation nudge with no task information of its own, in which case the last
    substantive message already in this conversation. Both call sites that generate a contract for
    the same job (backend/chat/api.py's system-prompt injection and backend/agents/jobs.py's
    JobManager.start) must resolve to the SAME source — otherwise the model is told one task mode in
    its system prompt while a different contract silently enforces (or fails to enforce) another."""
    if is_bare_continuation(last_user_text):
        prior = last_substantive_user_message(prior_messages)
        if prior is not None:
            return prior
    return last_user_text


_INTENT_PATTERNS = [
    # Priority order — used ONLY to break a tie when two patterns match at the exact same start
    # position (e.g. "how does X work" matches both EXPLAIN's and ANALYZE's "how does" branch).
    # EXPLAIN before ANALYZE for that case — "how does X work" is explain, "what files are there"
    # is analyze.
    (TaskIntent.EXPLAIN, _EXPLAIN),
    (TaskIntent.CREATE, _CREATE),
    (TaskIntent.MODIFY, _MODIFY),
    (TaskIntent.DELETE, _DELETE),
    (TaskIntent.SEARCH, _SEARCH),
    (TaskIntent.RUN, _RUN),
    (TaskIntent.ANALYZE, _ANALYZE),
]


def classify_intent(message: str, system_note: str = "") -> TaskIntent:
    """Classify user message into a single task intent.

    Picks whichever pattern's match starts EARLIEST in the text — not a fixed priority scan that
    stops at the first pattern in table order regardless of where it matched. That fixed-order scan
    was a real bug: a long CREATE-prefixed spec prompt ("Build a breathtaking... full-stack web
    application...") that happened to contain the word "explain" thousands of characters later — in
    an instruction like "Do NOT simply explain the architecture, implement it" — classified as
    EXPLAIN_CONCEPT (required_tools=[]) instead of CREATE_ARTIFACT, because EXPLAIN was checked
    first regardless of position. With nothing required, the job accepted the model's first plain
    text reply as "done" no matter how little of the actual multi-file build had happened — the
    exact "stops abruptly, no error" behavior this was written to fix. A prompt's leading verb is
    almost always its real intent; an incidental later mention of an unrelated verb inside a much
    longer prompt should not override it.
    """
    text = f"{message} {system_note}"
    best_intent: TaskIntent | None = None
    best_key: tuple[int, int] | None = None
    for intent, pattern in _INTENT_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        # Rank by (does it start a line, then how early). A verb that OPENS a line is someone
        # stating what they want; the same word mid-sentence is usually incidental. Position alone
        # was not enough: a real build request titled "# ATLAS — Single-HTML Frontend Benchmark"
        # classified as ANALYZE, because "Benchmark" (a legitimate analysis verb — "benchmark this
        # function") sat 11 characters before the "Build an ..." that opened the very next line.
        # required_tools for ANALYZE is empty, so nothing obliged the model to write anything, and
        # the job reported DONE after 48 minutes having produced zero files. A heading noun should
        # never outrank the imperative in the sentence beneath it.
        line_start = 0 if (match.start() == 0 or text[match.start() - 1] == "\n") else 1
        key = (line_start, match.start())
        if best_key is None or key < best_key:
            best_intent, best_key = intent, key
        # identical rank: keep whichever came first in _INTENT_PATTERNS (the old priority order)
    if best_intent is not None:
        return best_intent
    return TaskIntent.CONVERSATION


def generate_contract(message: str, system_note: str = "") -> TaskContract:
    """Generate a task contract from user message."""
    intent = classify_intent(message, system_note)
    text = f"{message} {system_note}".lower()

    # Detect artifact type.
    is_html = bool(_HTML_FILE.search(text))
    is_react = bool(_REACT_FILE.search(text))
    is_python = bool(_PYTHON_FILE.search(text))
    is_config = bool(_CONFIG_FILE.search(text))
    is_any_file = bool(_ANY_FILE.search(text))
    is_ui = bool(_UI_TASK.search(text))

    if intent == TaskIntent.CREATE:
        required = ["write_file"]
        success = ["Artifact created in the project"]
        workflow = [
            "inspect project structure",
            "determine target path",
            "create/write artifact",
            "verify the file exists",
            "report what was created",
        ]
        constraints = [
            "Do not return source code as chat response — use write_file",
            # A real overnight build ended with FOUR mutually incompatible design systems in one
            # app: an index.css class vocabulary, two separately-invented Tailwind token families
            # (apex-*, linen-*/jade-*) defined nowhere, and one view of raw hex. Each writing pass
            # invented plausible-sounding names instead of checking what the earlier files already
            # established — and because undefined Tailwind/CSS classes fail silently, it compiled
            # and "ran" while rendering as unstyled boxes. Naming the convention once, up front,
            # is what makes it survivable when later passes have lost the earlier files from
            # context (or hand the work to a delegated worker that never had them at all).
            "Establish the project's conventions ONCE before writing the second file — the design "
            "tokens, CSS class prefixes, context/hook names, and export style — and reuse those "
            "exact names in every later file and in every delegated spec. If a token or class is "
            "not already defined in the stylesheet or config, either define it there or use one "
            "that exists; never invent a parallel vocabulary.",
        ]
        if is_ui:
            workflow.insert(2, "load design guidance")
            workflow.insert(4, "start dev server and screenshot")
            # Not just suggested — enforced. This is the direct fix for a real, observed failure:
            # a UI build ran, wrote real files, but never actually looked at its own output before
            # declaring done, and the result read as generic/flat where a competing tool's build
            # (same underlying model) looked deliberately designed. "Looks done" and "was actually
            # looked at" are different claims; only the second one is checkable, so that's what's
            # required — a static HTML entry file works too, see start_dev_server's own handling.
            required = required + ["screenshot"]
            constraints = constraints + [
                "Do not claim the result is finished, polished, or matches the brief without "
                "having actually looked at the screenshot from this build — a text description "
                "of what you wrote is not a substitute for having seen it rendered.",
            ]
        return TaskContract(
            intent=intent,
            required_tools=required,
            success_criteria=success,
            constraints=constraints,
            suggested_workflow=workflow,
        )

    if intent == TaskIntent.MODIFY:
        required = ["edit_file"]  # or apply_patch/write_file — at least one must be called
        success = ["File modified successfully"]
        workflow = [
            "inspect existing implementation",
            "identify relevant files",
            "make targeted change",
            "verify the change",
        ]
        constraints = ["Inspect the file before modifying"]
        if is_ui:
            workflow.append("screenshot and visually verify")
            required = required + ["screenshot"]  # see the CREATE branch's comment — same reasoning
            constraints = constraints + [
                "Do not claim the change looks right without having actually looked at the "
                "screenshot from this change.",
            ]
        return TaskContract(
            intent=intent,
            required_tools=required,
            success_criteria=success,
            constraints=constraints,
            suggested_workflow=workflow,
        )

    if intent == TaskIntent.DELETE:
        return TaskContract(
            intent=intent,
            required_tools=["delete_file"],
            success_criteria=["Artifact removed from project"],
            constraints=["Confirm before deleting"],
            suggested_workflow=["verify target exists", "delete", "confirm removal"],
        )

    if intent == TaskIntent.RUN:
        return TaskContract(
            intent=intent,
            required_tools=["run_command"],
            success_criteria=["Command executed successfully"],
            suggested_workflow=["execute command", "report result"],
        )

    if intent == TaskIntent.SEARCH:
        return TaskContract(
            intent=intent,
            required_tools=["web_search"],
            success_criteria=["Search results returned"],
            suggested_workflow=["search", "summarize findings"],
        )

    if intent == TaskIntent.ANALYZE:
        return TaskContract(
            intent=intent,
            required_tools=[],  # read-only — no mandatory tools
            success_criteria=["Analysis provided"],
            suggested_workflow=["gather information", "provide analysis"],
        )

    if intent == TaskIntent.EXPLAIN:
        return TaskContract(
            intent=intent,
            required_tools=[],
            success_criteria=["Explanation provided"],
            suggested_workflow=["explain in chat"],
        )

    # CONVERSATION
    return TaskContract(
        intent=intent,
        required_tools=[],
        success_criteria=["Response provided"],
        suggested_workflow=["respond in chat"],
    )


def build_task_prompt(contract: TaskContract) -> str:
    """Build the task-specific system prompt to inject into the agent loop."""
    if contract.intent == TaskIntent.CONVERSATION:
        return ""

    lines = [
        f"TASK MODE: {contract.intent.value}",
        "",
    ]

    if contract.required_tools:
        lines.append(f"REQUIRED TOOLS: {', '.join(contract.required_tools)}")
        # MODIFY's edit_file/apply_patch/write_file are interchangeable alternatives to EACH OTHER
        # (validate_completion treats any one as satisfying that part) — but every other required
        # tool listed (e.g. screenshot, for an is_ui task) is a SEPARATE, additional requirement,
        # not one more option in that same either-or. Say so explicitly; "at least one of these"
        # would otherwise read as license to skip screenshot as long as write_file happened.
        if contract.intent == TaskIntent.MODIFY and len(contract.required_tools) > 1:
            lines.append(
                "edit_file, apply_patch, and write_file are interchangeable — call any one of "
                "those. Every OTHER tool listed here is separately mandatory on top of that."
            )
        else:
            lines.append("Every tool listed here is mandatory — all of them, not just one.")
        lines.append(
            "A response that doesn't call all of them does NOT complete the task."
        )
        lines.append("")

    if contract.constraints:
        lines.append("CONSTRAINTS:")
        for c in contract.constraints:
            lines.append(f"- {c}")
        lines.append("")

    if contract.suggested_workflow:
        lines.append("SUGGESTED WORKFLOW:")
        for i, step in enumerate(contract.suggested_workflow, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    if contract.success_criteria:
        lines.append("COMPLETION REQUIREMENTS:")
        for c in contract.success_criteria:
            lines.append(f"- {c}")
        lines.append("")

    return "\n".join(lines)


def validate_completion(
    contract: TaskContract,
    tools_called: list[str],
) -> tuple[bool, str]:
    """Check if the model completed the task by calling required tools.

    Returns (passed, message). If passed is False, the message explains what's missing
    and should be sent back to the model as a correction prompt.
    """
    if not contract.required_tools:
        return True, ""

    called_set = set(tools_called)
    required_set = set(contract.required_tools)

    # delegate_task (backend/agents/tools.py: _delegate_task) hands mechanical file/dir operations
    # to a fast worker model that executes them in its own sub-loop — those inner tool calls never
    # reach this job's own tools_called list, only the single "delegate_task" call does. Without
    # this, delegating (which the tool description now actively encourages, for exactly the
    # multi-file builds this validator exists to check) would look identical to never having
    # written anything, and the model would be told its completed work is incomplete.
    if "delegate_task" in called_set:
        called_set |= _DELEGATABLE_TOOLS

    # For MODIFY, edit_file OR apply_patch OR write_file all count as "the edit happened" — but
    # this must only satisfy THAT part of required_tools, not short-circuit the whole check. It
    # used to return True here unconditionally, which happened to be harmless while MODIFY's only
    # required tool was edit_file itself, but would have silently satisfied an unrelated
    # requirement (e.g. screenshot, for an is_ui MODIFY task) just because some edit occurred.
    if contract.intent == TaskIntent.MODIFY:
        modify_tools = {"edit_file", "apply_patch", "write_file"}
        if called_set & modify_tools:
            called_set |= modify_tools

    missing = required_set - called_set
    if not missing:
        return True, ""

    # Build correction prompt.
    intent_desc = {
        TaskIntent.CREATE: "creating a project artifact",
        TaskIntent.MODIFY: "modifying an existing file",
        TaskIntent.DELETE: "deleting an artifact",
        TaskIntent.RUN: "executing a command",
        TaskIntent.SEARCH: "searching for information",
    }.get(contract.intent, "completing the task")

    return False, (
        f"TASK NOT COMPLETED — The request requires {intent_desc}. "
        f"You must call {', '.join(missing)} before producing a final response. "
        f"A response containing code without calling the tool does NOT complete the task. "
        f"Continue execution."
    )
