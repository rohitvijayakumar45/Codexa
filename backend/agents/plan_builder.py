"""Derives the ExecutionPlan a job runs: the model may propose it, Codexa owns it.

Why this exists
---------------
The plan state machine (backend/agents/plan.py) is only as useful as the plan it is given, and the
plan is the one artefact that decides how much of the problem the model is asked about at once.
The motivating incident is the same one plan.py opens with: a model handed one large open-ended
request spent 48 minutes and 39,655 reasoning tokens designing three complete, different products
and discarding two, writing zero files. It was not being lazy or slow — it was answering the
question it was asked, which was the entire problem, every single round. Splitting that request
into "inspect the repo", then "commit to a direction", then "write index.html" makes the same model
produce a file in minutes, because the third task is not answerable by more deliberation.

So this module's job is to turn a request into an ordered list of tasks each of which is finishable
and, ideally, checkable from outside the model. Two paths do that:

* A model PROPOSES a plan. Models are genuinely good at decomposing a brief they just read, and a
  proposal shaped by the actual request beats any generic template. It is a single non-streaming
  call, low temperature, hard-capped output.
* Codexa OWNS the result. Every proposal is normalised and validated before it becomes a plan:
  task count clamped, invented tool names dropped, artifact paths forced repository-relative,
  dependencies rebuilt from real ids. Nothing the model returns is used as-is.

And the proposal path can never fail a job. Every failure mode — an exception, a timeout, a rate
limit, fenced JSON, prose around the JSON, an empty task list, a plan of one giant task — falls
silently back to `fallback_plan`, which is deterministic, LLM-free and importable on its own. A
planning step that can itself hang or error would be a new instance of exactly the failure this
whole feature exists to remove.
"""

from __future__ import annotations

import json
import logging
import re
from itertools import chain
from typing import Any

from backend.agents.plan import ExecutionPlan, Task, make_task
from backend.agents.task import TaskContract, TaskIntent
from backend.agents.tools import tool_groups

logger = logging.getLogger(__name__)

# backend/agents/validators.py resolves validator NAMES against reality (files on disk, exit codes).
# Imported rather than reimplemented — validation against reality has exactly one owner, and a
# second, subtly different copy of it living here is how "the plan says PASSED but the file isn't
# there" happens.
#
# Imported hard, with no fallback, on purpose. A plan whose tasks carry no validators is a checklist
# the model ticks off itself, which is the exact thing this system exists to replace: every task
# would then complete on the model's first non-tool reply. Degrading quietly to that on an import
# error would turn a broken module into a silently unenforced platform — far worse than failing
# loudly at startup.
from backend.agents.validators import infer_validators


# Floor and ceiling on a proposed plan. The floor is the whole point of the feature: one or two
# tasks is the "solve the entire problem" framing wearing a plan's clothes, and it reproduces the
# 48-minute round exactly. The ceiling is the opposite failure — a plan of thirty micro-steps makes
# advancing the plan the work, and plan.py's own granularity note says the same thing.
MIN_TASKS = 3
MAX_TASKS = 12

# Intents where a sub-MIN_TASKS proposal is a signal the model did not decompose anything, rather
# than an honest read of a small request. "Explain decorators" legitimately needs one task; "build a
# polished interactive page" does not.
_SUBSTANTIAL_INTENTS = frozenset({TaskIntent.CREATE, TaskIntent.MODIFY})

# Every tool name that actually exists. A required_tool the executor has never heard of can never be
# called, so a task requiring one can never satisfy its own completion condition — it sits at the
# head of the plan burning attempts until the job dies. Dropping unknown names is strictly better
# than honouring them.
_REAL_TOOLS: frozenset[str] = frozenset(chain.from_iterable(tool_groups.values()))

# Proposal call limits. Low temperature because this is structure, not prose; the token cap is small
# because a plan of twelve one-line objectives does not need more, and an uncapped planning call is
# a place a reasoning model will happily spend the whole budget thinking about the build instead of
# describing it.
_PROPOSAL_TEMPERATURE = 0.2
# Raised from 1400. A reasoning model spends its budget thinking BEFORE any content is emitted, so
# a cap sized for the JSON alone can be entirely consumed by reasoning and return an empty string —
# reproduced directly: max_tokens=20 returned "", max_tokens=1400 returned the JSON. 3000 leaves
# room for the deliberation a twelve-task decomposition actually takes.
_PROPOSAL_MAX_TOKENS = 3000
# This call sits on the critical path: nothing else happens until it returns or gives up.
#
# It has been wrong in both directions. At 90s it cost a run 100 seconds of dead time against an
# unreachable provider. Lowered to 25s, it then failed on EVERY job of an overnight run — the
# default model is a reasoning model that spends a minute or more thinking before it emits its
# first JSON token, so 25s could not succeed even when the provider was perfectly healthy. The
# consequence was invisible and much worse than slowness: every plan in the system silently became
# the deterministic template, which is how a template's genericness became the product.
#
# 75s is chosen from the measurement rather than from taste: a real HELIX proposal returned valid
# JSON, and the failures at 25s were timeouts and not refusals. A proposal that misses this window
# still costs the job nothing — fallback_plan is deterministic and good — so the risk of the higher
# number is bounded dead time, while the risk of the lower one was silently disabling the feature.
_PROPOSAL_TIMEOUT_S = 75
_PROPOSAL_REQUEST_CHARS = 4000

_MAX_OBJECTIVE_CHARS = 160
_MAX_CRITERIA_PER_TASK = 5
_MAX_TOOLS_PER_TASK = 5
_MAX_ARTIFACTS_PER_TASK = 5

# A filename written plainly in the request. Deliberately narrow: extensions we can act on, and no
# spaces, so a sentence like "the design is very .. html-ish" cannot masquerade as a path.
_FILENAME = re.compile(
    r"\b([A-Za-z0-9_.\-/]+\.(?:html?|css|js|jsx|ts|tsx|py|md|json|ya?ml|toml|txt|sh))\b"
)
# "a single self-contained HTML file", "one HTML page", "single-file html" and friends.
_SINGLE_HTML = re.compile(
    r"\b(single|one|self.?contained|standalone|single.?file)\b[^.\n]{0,60}?"
    r"\b(html|web ?page|page)\b",
    re.IGNORECASE,
)
_DRIVE_OR_UNC = re.compile(r"^(?:[A-Za-z]:|//|\\\\)")


# ── artifact detection and path hygiene ────────────────────────────────────────


def _detect_primary_artifact(request: str) -> str | None:
    """The one file this request is obviously about, or None.

    None is the correct and common answer. An expected artifact is checked against the filesystem
    by validators.py, so guessing one is not a harmless nicety: a build that correctly writes
    `src/App.tsx` while the plan expects the invented `components/Widget.tsx` fails validation on
    every attempt, exhausts MAX_ATTEMPTS_PER_TASK and FAILS a task that actually succeeded. No
    artifact check is weaker than a correct one but far better than a wrong one, so anything short
    of "the request names it, or it can only be index.html" returns None.
    """
    text = request or ""
    named = {m.group(1) for m in _FILENAME.finditer(text)}
    cleaned = {p for p in (_normalise_artifact(n) for n in named) if p}
    if len(cleaned) == 1:
        # Exactly one file named in the whole request — that is the deliverable. Two or more and we
        # cannot tell which is primary (a spec that mentions package.json in passing while asking
        # for index.html), so we decline rather than pick.
        return next(iter(cleaned))
    if _SINGLE_HTML.search(text):
        # The one safe guess in the whole space: a self-contained single-page request has exactly
        # one conventional home, and prompts/single-html-benchmark.md names it explicitly.
        return "index.html"
    return None


def _normalise_artifact(path: str) -> str | None:
    """Force a proposed path to be repository-relative, or reject it.

    Validation resolves these paths against the repository. A plan must therefore not be able to
    point them anywhere else — a model writing `/etc/passwd` or `../../secrets.env` as an expected
    artifact would otherwise have Codexa stat those paths on its behalf. Leading `./` and `/` are
    stripped rather than rejected because models routinely write `/index.html` meaning "at the root
    of the project"; `..` and drive-letter/UNC prefixes are rejected outright because there is no
    charitable repository-relative reading of either.
    """
    if not isinstance(path, str):
        return None
    p = path.strip().strip("`'\"").replace("\\", "/").strip()
    if not p or "\x00" in p:
        return None
    if _DRIVE_OR_UNC.match(p):
        # Checked before the strip loop below, not only after: `//server/share` would otherwise be
        # flattened into the innocuous-looking relative `server/share` instead of being refused.
        return None
    while p.startswith("./") or p.startswith("/"):
        p = p[2:] if p.startswith("./") else p[1:]
    p = p.strip()
    if not p or _DRIVE_OR_UNC.match(p):
        return None
    if any(seg == ".." for seg in p.split("/")):
        return None
    if len(p) > 200:
        return None
    return p


# ── proposal parsing ───────────────────────────────────────────────────────────


def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers. Models fence structured output by habit even when told not
    to, and treating that as unparseable would throw away a perfectly good plan."""
    t = text.strip()
    if "```" not in t:
        return t
    fenced = re.findall(r"```(?:json|JSON)?\s*(.*?)```", t, re.DOTALL)
    return fenced[0].strip() if fenced else t.replace("```json", " ").replace("```", " ").strip()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Pull the outermost balanced `{...}` out of a reply and parse it.

    Brace-balanced rather than regex-greedy, and string-aware, because task objectives frequently
    contain braces and quotes ("wire up the {count} badge") and a greedy first-`{`-to-last-`}` slice
    gets those wrong in both directions. A plain json.loads is tried first for the common case where
    the model did exactly as asked.
    """
    if not text:
        return None
    body = _strip_fences(text)
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    start = body.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(body)):
            ch = body[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        candidate = json.loads(body[start : i + 1])
                    except (json.JSONDecodeError, ValueError):
                        break  # this opener didn't yield valid JSON; try the next one
                    if isinstance(candidate, dict):
                        return candidate
                    break
        start = body.find("{", start + 1)
    return None


def _clean_str(value: Any, *, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()


def _clean_str_list(value: Any, *, limit: int, item_limit: int) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        cleaned = _clean_str(item, limit=item_limit)
        if cleaned and cleaned not in out:
            out.append(cleaned)
        if len(out) >= limit:
            break
    return out


# ── proposal → plan (the "Codexa owns it" half) ────────────────────────────────


def _plan_from_proposal(data: dict[str, Any], request: str, contract: TaskContract) -> ExecutionPlan | None:
    """Normalise a parsed proposal into a real ExecutionPlan, or return None to fall back.

    Everything here is a repair or a refusal; nothing is taken on trust. Returning None rather than
    raising keeps the single decision point in build_plan: any doubt at all means the deterministic
    plan runs, and the job proceeds.
    """
    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return None

    entries: list[dict[str, Any]] = []
    for raw in raw_tasks:
        if not isinstance(raw, dict):
            continue
        objective = _clean_str(raw.get("objective"), limit=_MAX_OBJECTIVE_CHARS)
        if not objective:
            continue
        entries.append(
            {
                "objective": objective,
                # Unknown names dropped, not passed through: see _REAL_TOOLS.
                "required_tools": [
                    t
                    for t in _clean_str_list(raw.get("required_tools"), limit=_MAX_TOOLS_PER_TASK, item_limit=60)
                    if t in _REAL_TOOLS
                ],
                "expected_artifacts": [
                    p
                    for p in (
                        _normalise_artifact(a)
                        for a in _clean_str_list(
                            raw.get("expected_artifacts"), limit=_MAX_ARTIFACTS_PER_TASK, item_limit=200
                        )
                    )
                    if p
                ],
                "completion_criteria": _clean_str_list(
                    raw.get("completion_criteria"), limit=_MAX_CRITERIA_PER_TASK, item_limit=200
                ),
                "depends_on_previous": bool(raw.get("depends_on_previous", True)),
            }
        )
        if len(entries) >= MAX_TASKS:
            # Keep the first MAX_TASKS rather than sampling: plans are ordered, and the front of a
            # proposal is the part that gets the job to a written file.
            break

    if len(entries) < MIN_TASKS and contract.intent in _SUBSTANTIAL_INTENTS:
        logger.warning(
            "plan proposal had %d task(s) for a %s request — below MIN_TASKS, using deterministic plan",
            len(entries),
            contract.intent.value,
        )
        return None
    if not entries:
        return None

    tasks: list[Task] = []
    for i, entry in enumerate(entries, start=1):
        # depends_on ids are built here, from ids make_task actually generated, and never taken from
        # the model. A model inventing its own id graph produces unsatisfiable dependencies with
        # some regularity, and plan.is_ready() treats a dependency it cannot find as never satisfied
        # — one typo'd id is a permanently stuck plan that no amount of model effort can clear.
        depends_on = [tasks[-1].id] if (entry["depends_on_previous"] and tasks) else []
        task = make_task(
            entry["objective"],
            index=i,
            depends_on=depends_on,
            required_tools=entry["required_tools"],
            expected_artifacts=entry["expected_artifacts"],
            completion_criteria=entry["completion_criteria"],
        )
        task.validators = list(infer_validators(task))
        tasks.append(task)

    objective = _clean_str(data.get("objective"), limit=300) or _default_objective(request)
    return ExecutionPlan(objective=objective, tasks=tasks, committed=True)


def _default_objective(request: str) -> str:
    text = " ".join((request or "").split())
    return text[:200].strip() or "Complete the requested work"


# ── the proposal call ──────────────────────────────────────────────────────────


_PROPOSAL_SYSTEM = (
    "You are the planning stage of an execution engine. You decompose a request into an ordered "
    "list of tasks that another agent will execute one at a time. You do not design the solution "
    "and you do not write any code here — only the plan. Reply with JSON and nothing else."
)


def _proposal_prompt(request: str, contract: TaskContract, repository: str) -> str:
    req = " ".join((request or "").split())
    truncated = len(req) > _PROPOSAL_REQUEST_CHARS
    req = req[:_PROPOSAL_REQUEST_CHARS] + (" ... [truncated]" if truncated else "")
    lines = [
        f"REQUEST:\n{req}",
        "",
        f"CLASSIFIED INTENT: {contract.intent.value}",
    ]
    if repository:
        lines.append(f"REPOSITORY: {repository}")
    if contract.required_tools:
        lines.append(f"TOOLS THE FINISHED JOB MUST HAVE CALLED: {', '.join(contract.required_tools)}")
    if contract.suggested_workflow:
        lines.append("SUGGESTED WORKFLOW: " + " -> ".join(contract.suggested_workflow))
    lines += [
        "",
        "AVAILABLE TOOL NAMES (use only these; any other name is discarded):",
        ", ".join(sorted(_REAL_TOOLS)),
        "",
        "Reply with ONLY this JSON:",
        '{"objective": "one sentence", "tasks": [',
        '  {"objective": "short imperative", "required_tools": ["write_file"],',
        '   "expected_artifacts": ["index.html"], "completion_criteria": ["..."],',
        '   "depends_on_previous": true}',
        "]}",
        "",
        "RULES:",
        f"- Between {MIN_TASKS} and {MAX_TASKS} tasks, in execution order.",
        "- Each task must be finishable on its own and, where possible, checkable from outside: a "
        "file exists, a command exits 0, a screenshot was taken.",
        "- The first task inspects what is already there. An early task commits to ONE direction "
        "in a sentence. Do not plan to evaluate alternatives — that is the failure this replaces.",
        "- Get to the task that writes the primary file early; refinement tasks come after it.",
        "- expected_artifacts are repository-relative paths only. Omit them unless you are certain "
        "of the path; a wrong path fails a correct build forever.",
        "- required_tools are the tools that task cannot be finished without, not every tool it "
        "might touch.",
        "- No prose before or after the JSON.",
    ]
    return "\n".join(lines)


def _request_proposal(
    request: str,
    contract: TaskContract,
    *,
    llm: Any,
    model: str,
    repository: str,
) -> ExecutionPlan | None:
    messages = [
        {"role": "system", "content": _PROPOSAL_SYSTEM},
        {"role": "user", "content": _proposal_prompt(request, contract, repository)},
    ]
    raw = llm.complete(
        messages,
        model=model,
        agent="plan",
        temperature=_PROPOSAL_TEMPERATURE,
        max_tokens=_PROPOSAL_MAX_TOKENS,
        timeout=_PROPOSAL_TIMEOUT_S,
    )
    data = _extract_json_object(raw if isinstance(raw, str) else "")
    if data is None:
        logger.warning("plan proposal was not parseable JSON — using deterministic plan")
        return None
    return _plan_from_proposal(data, request, contract)


# ── deterministic plans ────────────────────────────────────────────────────────
#
# This is not a degraded mode. It runs whenever the proposal path is unavailable or refused, which
# on a rate-limited provider is often, so it has to be a plan someone would have written by hand.
# The shapes below encode the order that actually produces finished work: look, commit, build the
# thing, make it real, look at it, fix what you saw. Proportionality matters as much as quality —
# an EXPLAIN request given an eight-task build plan is its own absurdity, and would keep a job alive
# for eight tasks' worth of rounds to answer a question.


def _build_tasks(specs: list[dict[str, Any]]) -> list[Task]:
    """Turn ordered task specs into a strictly sequential plan.

    Every task depends on the one before it. Real builds are sequential — you cannot refine a file
    you have not written — and a linear chain has the property that a failure stops the plan (via
    plan.fail's dependent-blocking) instead of letting later tasks run against a state that never
    materialised.
    """
    tasks: list[Task] = []
    for i, spec in enumerate(specs, start=1):
        task = make_task(
            spec["objective"],
            index=i,
            depends_on=[tasks[-1].id] if tasks else [],
            required_tools=spec.get("required_tools", ()),
            expected_artifacts=spec.get("expected_artifacts", ()),
            completion_criteria=spec.get("completion_criteria", ()),
        )
        task.validators = list(infer_validators(task))
        tasks.append(task)
    return tasks


def _create_specs(request: str, contract: TaskContract) -> list[dict[str, Any]]:
    artifact = _detect_primary_artifact(request)
    artifacts = [artifact] if artifact else []
    # task.py signals "this is a UI job" by adding screenshot to required_tools (see its is_ui
    # branch). That, not another keyword regex here, is the single source of truth for whether the
    # browser tasks belong in this plan — two independent detectors would eventually disagree, and
    # the disagreement would show up as a plan requiring a screenshot of something with no UI.
    is_ui = "screenshot" in contract.required_tools

    specs: list[dict[str, Any]] = [
        {
            "objective": "Inspect the repository and establish the conventions to follow",
            "required_tools": ["list_directory"],
            "completion_criteria": [
                "Know what already exists and where the new work belongs",
                "Know the existing naming, token and style conventions, or that there are none",
            ],
        },
        {
            # The anti-divergence step, and the reason this plan exists at all. The observed 48
            # minute round was three product designs in a row; a task whose entire deliverable is
            # one committed direction makes that divergence finish instead of recur, and everything
            # after it is execution against a decision already made.
            # required_tools is what gives this task a mechanical completion criterion, and without
            # one it could not end on the round that finished it. `try_advance` refuses to complete
            # a task with no validators — deliberately, so "nothing to verify" cannot mean "complete
            # the instant it starts" — so a criterion-less task could only finish via a round with
            # NO tool calls. That forced the model to keep generating prose in order to end the
            # task, and it filled that prose with the design of every LATER task.
            #
            # Measured on two real runs: the task above, which advances on its tool round, spent 69
            # reasoning characters. This one, with no criterion, spent 2,002 and 5,806 across two
            # rounds — and a third run reached roughly 18,000, all of it designing work that
            # belonged to tasks three through nine. The leak was structural, not a lapse of focus.
            "objective": "Commit to one direction and state it in a few sentences",
            "required_tools": ["commit_direction"],
            "completion_criteria": [
                "One concept, stated once, in no more than a few sentences",
                "No alternatives evaluated — a better idea goes in a comment, not into a rethink",
            ],
        },
        {
            "objective": (
                f"Write the complete first version of {artifact}" if artifact else "Write the primary file"
            ),
            "required_tools": ["write_file"],
            "expected_artifacts": artifacts,
            "completion_criteria": [
                "The file exists on disk and is complete enough to open",
                "Written in one piece, not assembled from fragments",
            ],
        },
        {
            "objective": "Implement the core experience end to end",
            "required_tools": ["write_file", "edit_file"],
            "expected_artifacts": artifacts,
            "completion_criteria": [
                "The main flow works, not just its markup or scaffolding",
                "Content is real, not placeholder",
            ],
        },
        {
            "objective": "Add the interaction states: hover, focus, active, loading, empty, error",
            "required_tools": ["edit_file"],
            "expected_artifacts": artifacts,
            "completion_criteria": [
                "Loading, empty, error, selected and focused states exist",
                "Interactions respond when used, not merely when described",
            ],
        },
        {
            # Motion gets its own milestone rather than a third of the task above. Folded in with
            # interactions and states it was always the part that got dropped: observed output kept
            # improving visually while its animation stayed generic, because "add interactions,
            # transitions and states" is satisfied by doing the first two. A design commitment that
            # is not executable work does not get executed.
            "objective": "Build the motion system: one easing curve, one duration scale, applied "
                         "everywhere",
            "required_tools": ["edit_file"],
            "expected_artifacts": artifacts,
            "completion_criteria": [
                "Motion tokens are defined once and every transition uses them",
                "Only transform and opacity are animated",
                "prefers-reduced-motion disables movement",
            ],
        },
    ]

    if is_ui:
        specs += [
            {
                # A real UI build wrote correct files, declared itself done, and had never once
                # looked at its own output — it read as flat and generic next to a competing build
                # from the same model. "Looks finished" and "was actually looked at" are different
                # claims and only the second is checkable, so it gets its own task.
                "objective": "Run it and look at the actual rendered output",
                "required_tools": ["start_dev_server", "screenshot"],
                "completion_criteria": ["A screenshot of this build was taken and examined"],
            },
            {
                "objective": "Fix what the screenshot shows is wrong",
                "required_tools": ["edit_file", "screenshot"],
                "expected_artifacts": artifacts,
                "completion_criteria": [
                    "Every problem visible in the screenshot is addressed",
                    "A screenshot taken after the fixes confirms them",
                ],
            },
            {
                "objective": "Final visual and console check",
                "required_tools": ["screenshot", "browser_console"],
                "completion_criteria": [
                    "Checked at desktop and narrow widths",
                    "Zero console errors",
                ],
            },
        ]
    else:
        specs.append(
            {
                "objective": "Verify the result on disk and report what was created",
                "required_tools": ["read_file"],
                "expected_artifacts": artifacts,
                "completion_criteria": ["The written files are present and contain what was intended"],
            }
        )
    return specs


_FULLSTACK = re.compile(
    r"\b(full[- ]?stack|backend|back[- ]end|database|schema|persistence|persist|"
    r"api (?:layer|endpoint)|endpoints?|server|migration|orm|sqlite|postgres|prisma|"
    r"express|fastapi|django|flask|rest api|graphql)\b",
    re.IGNORECASE,
)
# A request that says "one file" cannot be a full-stack build no matter which nouns it also uses;
# VELUM's brief mentions an "archive" and AURELIA's mentions "portfolio data" without either being
# a server. This wins over _FULLSTACK.
_SINGLE_FILE_DECLARED = re.compile(
    r"\b(single[- ](?:self[- ]contained[- ])?(?:html|file|page)|one html file|"
    r"entirely (?:with)?in one html file|self[- ]contained html)\b",
    re.IGNORECASE,
)
# Size signals for a MODIFY. Word count alone is a poor proxy and was measured to be: "refactor the
# authentication module to use JWT everywhere, split the session helpers out, update every caller,
# and keep the tests passing" is thirty words and is emphatically not a small change. So brevity is
# necessary but not sufficient — scope words and multiple named files both veto it.
_SMALL_CHANGE_WORDS = 45
_BROAD_SCOPE = re.compile(
    r"\b(refactor|restructure|reorgani[sz]e|migrat\w*|rewrite|overhaul|redesign|port|"
    r"every|all (?:the )?(?:callers?|files?|usages?|references?)|across|throughout|"
    r"end[- ]to[- ]end|architecture|module)\b",
    re.IGNORECASE,
)


def _is_full_stack(request: str) -> bool:
    text = request or ""
    if _SINGLE_FILE_DECLARED.search(text):
        return False
    return bool(_FULLSTACK.search(text))


def _named_files(request: str) -> list[str]:
    """Every repository-relative file path the request actually names, in order."""
    seen: list[str] = []
    for m in _FILENAME.finditer(request or ""):
        p = _normalise_artifact(m.group(1))
        if p and p not in seen:
            seen.append(p)
    return seen


def _target_phrase(request: str) -> str:
    """A short human name for what is being changed, for use inside task objectives.

    The point is that a plan should read as being about THIS request. A generic "Locate the code
    that has to change" is the same sentence for every job in the system, which is exactly the
    complaint that produced this function: editing one file in an existing repository produced a
    task list indistinguishable from a greenfield build.
    """
    files = _named_files(request)
    if files:
        return ", ".join(files[:3]) + (" and others" if len(files) > 3 else "")
    words = " ".join((request or "").split())
    return (words[:60].rstrip() + "…") if len(words) > 60 else (words or "the requested change")


def _modify_specs(request: str, contract: TaskContract) -> list[dict[str, Any]]:
    """Plan for changing something that already exists — sized to the change.

    Previously this returned a fixed four-to-five task template that never looked at the request:
    the same list, with the same generic objectives, whether the ask was "rename this variable" or
    "restructure the whole dashboard". For a small edit that is pure overhead — four validated task
    transitions to change one line — and because no objective ever named the file, the plan gave the
    model no information it did not already have.

    Now the shape follows the request: a small, targeted change gets two tasks and names its target;
    a substantial one keeps the inspect/change/verify arc; and only a UI change pays for the
    run-and-look-at-it steps.
    """
    is_ui = "screenshot" in contract.required_tools
    files = _named_files(request)
    target = _target_phrase(request)
    # Small enough for two tasks only if it is short, touches at most one named file, is not a UI
    # change (those need the run-and-look steps), and uses no language implying breadth.
    small = (
        len((request or "").split()) <= _SMALL_CHANGE_WORDS
        and not is_ui
        and len(files) <= 1
        and not _BROAD_SCOPE.search(request or "")
    )

    if small:
        # Two tasks. Reading before editing is still required — it is what stops a blind rewrite —
        # but it does not need to be a separately validated milestone for a one-line change.
        return [
            {
                "objective": f"Read {target} and make the change",
                "required_tools": ["read_file", "edit_file"],
                "expected_artifacts": files[:1],
                "completion_criteria": [f"The change is applied on disk to {target}"],
            },
            {
                "objective": "Verify the change and report exactly what was altered",
                "required_tools": ["read_file"],
                "completion_criteria": ["The change is present on disk and nothing else broke"],
            },
        ]

    specs: list[dict[str, Any]] = [
        {
            "objective": f"Find and read the code behind {target}",
            "required_tools": ["search_code", "read_file"],
            "completion_criteria": ["The exact files and lines to change are identified"],
        },
        {
            "objective": f"Make the change to {target}",
            "required_tools": ["edit_file"],
            "expected_artifacts": files[:1],
            "completion_criteria": ["The change is applied to the files on disk"],
        },
    ]
    if is_ui:
        specs += [
            {
                "objective": "Run it and look at the rendered result",
                "required_tools": ["start_dev_server", "screenshot"],
                "completion_criteria": ["A screenshot taken after this change was examined"],
            },
            {
                "objective": "Fix what the screenshot shows is wrong",
                "required_tools": ["edit_file", "screenshot"],
                "completion_criteria": ["Visible problems addressed and re-checked"],
            },
        ]
    else:
        specs.append(
            {
                "objective": "Verify the change and report it",
                "required_tools": ["read_file"],
                "completion_criteria": ["The change is present on disk and nothing else broke"],
            }
        )
    return specs


def _fullstack_specs(request: str, contract: TaskContract) -> list[dict[str, Any]]:
    """Plan for a request that asks for a backend, a database and an API — not one page.

    Without this, a full-stack brief fell through to the single-file CREATE template and was planned
    as "write the primary file, implement the core experience, screenshot it". Every validator then
    checked a frontend, so a run could satisfy its whole plan having written no schema, no endpoint
    and no persistence at all — the plan cannot catch what it never asked for.

    Deliberately no expected_artifacts: the layout is the model's judgement (the brief explicitly
    says so), and naming a path the build did not choose makes a correct implementation fail
    validation forever. These tasks are enforced through required_tools and through the files-changed
    check instead.
    """
    return [
        {
            "objective": "Inspect the repository and choose the stack and project layout",
            "required_tools": ["list_directory"],
            "completion_criteria": ["The stack, directory layout and run commands are decided"],
        },
        {
            "objective": "Commit to one architecture and state it in a few sentences",
            # See the note on the single-file plan's commit task: a task with no mechanical
            # criterion can only end on a round with no tool calls, which is what turned "commit a
            # direction" into "design the whole application in prose".
            "required_tools": ["commit_direction"],
            "completion_criteria": ["A single direction is chosen and not revisited"],
        },
        {
            "objective": "Define the data model and database schema",
            "required_tools": ["write_file"],
            "completion_criteria": ["Tables/entities and their relationships exist as real files"],
        },
        {
            "objective": "Build the backend: API endpoints, validation and persistence",
            "required_tools": ["write_file"],
            "completion_criteria": ["Endpoints exist and read and write the database"],
        },
        {
            "objective": "Seed realistic data so the application is credible on first launch",
            "required_tools": ["write_file"],
            "completion_criteria": ["Seed data exists and loads"],
        },
        {
            "objective": "Build the frontend and wire it to the real API",
            "required_tools": ["write_file"],
            "completion_criteria": ["The interface reads and writes through the API, not mocks"],
        },
        {
            "objective": "Run the whole stack and exercise the main flows end to end",
            "required_tools": ["run_command"],
            "completion_criteria": ["The stack starts and a real create/read round-trip succeeds"],
        },
        {
            "objective": "Look at the running interface and fix what is wrong",
            "required_tools": ["screenshot", "edit_file"],
            "completion_criteria": ["A screenshot was examined and its problems addressed"],
        },
        {
            "objective": "Verify persistence survives a restart and tests pass",
            "required_tools": ["run_command"],
            "completion_criteria": ["Data survives a reload and the test command exits 0"],
        },
    ]


def _specs_for(request: str, contract: TaskContract) -> list[dict[str, Any]]:
    intent = contract.intent
    if intent is TaskIntent.CREATE:
        # A brief asking for a backend, a database and an API is not a page. Sent to its own
        # shape before the single-file template gets a chance to mis-plan it as one.
        if _is_full_stack(request):
            return _fullstack_specs(request, contract)
        return _create_specs(request, contract)
    if intent is TaskIntent.MODIFY:
        return _modify_specs(request, contract)
    if intent is TaskIntent.DELETE:
        return [
            {
                "objective": "Confirm the target exists and find what references it",
                "required_tools": ["list_directory", "find_references"],
                "completion_criteria": ["The target path is confirmed and its references are known"],
            },
            {
                "objective": "Delete the target",
                "required_tools": ["delete_file"],
                "completion_criteria": ["The path no longer exists"],
            },
            {
                "objective": "Confirm nothing was left pointing at it",
                "required_tools": ["search_code"],
                "completion_criteria": ["No dangling references remain"],
            },
        ]
    if intent is TaskIntent.RUN:
        return [
            {
                "objective": "Determine the exact command to run",
                "required_tools": ["get_project_metadata"],
                "completion_criteria": ["The command and working directory are known"],
            },
            {
                "objective": "Run it and report the real output",
                "required_tools": ["run_command"],
                "completion_criteria": [
                    "The command was executed and its exit code and output reported as they were",
                ],
            },
        ]
    if intent is TaskIntent.SEARCH:
        return [
            {
                "objective": "Search for the information",
                "required_tools": ["web_search"],
                "completion_criteria": ["Results retrieved"],
            },
            {
                "objective": "Summarise the findings and say what they imply here",
                "completion_criteria": ["Findings summarised with their source"],
            },
        ]
    if intent is TaskIntent.ANALYZE:
        return [
            {
                "objective": "Gather the relevant code and structure",
                "required_tools": ["list_directory", "search_code", "read_file"],
                "completion_criteria": ["The files that answer the question have been read"],
            },
            {
                "objective": "Answer the question from what was actually read",
                "completion_criteria": ["The analysis cites real files, not assumed ones"],
            },
        ]
    if intent is TaskIntent.EXPLAIN:
        # One task, no tools, no artifacts. An explanation is finished by being written; wrapping it
        # in a multi-task build plan would keep the job alive for rounds after the answer existed.
        return [
            {
                "objective": "Answer the question in chat",
                "completion_criteria": ["The question is answered directly"],
            }
        ]
    return []


def fallback_plan(request: str, contract: TaskContract) -> ExecutionPlan:
    """The deterministic, LLM-free plan for a request. Never calls a model, never touches the
    network, never raises — importable and callable on its own (jobs.py uses it when no planning
    model is configured, and build_plan falls back to it for every proposal failure).

    CONVERSATION returns an ExecutionPlan with NO tasks. That is a sentinel meaning "this request
    does not need a plan", not an empty plan to execute: plan.is_complete() returns False for a
    task-less plan by design, so a caller that installs one and then waits for it to complete waits
    forever. Callers must check `plan.tasks` and skip the plan-driven path entirely when it is empty.
    """
    if contract.intent is TaskIntent.CONVERSATION:
        return ExecutionPlan()
    specs = _specs_for(request, contract)
    if not specs:
        return ExecutionPlan()
    return ExecutionPlan(objective=_default_objective(request), tasks=_build_tasks(specs), committed=True)


# ── entry point ────────────────────────────────────────────────────────────────


def build_plan(
    request: str,
    contract: TaskContract,
    *,
    llm: object | None = None,
    model: str | None = None,
    repository: str = "",
) -> ExecutionPlan:
    """Return the ExecutionPlan for this request. Never raises.

    With `llm` and `model`, the model is asked ONCE for a proposal, which is then normalised and
    validated (see _plan_from_proposal) before it is allowed to become a plan. Anything that goes
    wrong — an exception, a timeout, a rate limit, unparseable output, too few tasks — logs a
    warning and falls through to `fallback_plan`. Planning is the step before any work happens; a
    planner that can fail a job would be worse than having no planner at all.

    A returned plan with no tasks means "no plan needed" (CONVERSATION, or an intent with nothing to
    execute) — see fallback_plan's note. Check `plan.tasks` before installing it.
    """
    try:
        if contract.intent is TaskIntent.CONVERSATION:
            return ExecutionPlan()
        if llm is not None and model:
            try:
                proposed = _request_proposal(
                    request, contract, llm=llm, model=model, repository=repository
                )
                if proposed is not None and proposed.tasks:
                    return proposed
            except Exception as exc:  # noqa: BLE001 - the proposal path must never fail a job
                logger.warning(
                    "plan proposal failed (%s: %s) — using deterministic plan",
                    type(exc).__name__,
                    exc,
                )
        return fallback_plan(request, contract)
    except Exception as exc:  # noqa: BLE001 - last resort; callers treat an empty plan as "no plan"
        logger.warning("plan construction failed (%s: %s) — running without a plan", type(exc).__name__, exc)
        return ExecutionPlan()
