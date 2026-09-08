"""Mechanical completion checks — the gate between "the model says it finished" and COMPLETED.

Why this exists
---------------
backend/agents/plan.py owns *when* a task may finish; this module owns *whether it did*. The split
is the point: plan.py is pure state and deliberately has no filesystem, so the reality check lives
here, and `ExecutionPlan.record_validation` takes its answer from this module rather than from the
model's own account of its work.

Nothing here reads the transcript for a claim of success. Every validator asks something that can
only be answered by the world outside the model: does this file exist on disk and is it non-empty,
did this command exit 0, was this tool actually dispatched, did the repository change. The failure
this closes is the oldest one in the loop — a model replying "Done." having written nothing, and
the loop believing it, because the only thing it had to go on was that sentence.

Fail-closed, with one deliberate exception
------------------------------------------
An unknown validator name fails: a plan referencing a check that does not exist is a plan whose
completion nobody has verified, and treating that as a pass is how a typo becomes a silent success.
The exception is a validator that cannot be *run* rather than one that ran and said no (see
`no_build_errors`) — that returns a pass whose detail says, in words, that it was not checked. A
validator that guesses is worse than one that abstains; an abstention that hides itself is worst of
all, which is why `detail` is always populated, including on a pass.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from fastapi import HTTPException

from backend.agents.plan import Task
from backend.agents.progress import RepoSnapshot, compare, snapshot
from backend.agents.tools import _get_build_errors
from backend.files.api import repo_root

# The same allowance backend/agents/task.py::validate_completion applies, imported rather than
# copied so the two checks can never drift into disagreeing about what delegation satisfies.
from backend.agents.task import _DELEGATABLE_TOOLS

logger = logging.getLogger(__name__)

# Tool calls that hand the actual file writing to a worker model running its own sub-loop
# (backend/agents/tools.py: _delegate_task / _delegate_build). The worker's inner write_file calls
# never reach the parent job's tools_called list — only the single delegate_* call does — so
# without this allowance, delegating (which the tool descriptions actively encourage for exactly
# the multi-file builds these validators exist to check) looks byte-for-byte identical to never
# having written anything, and a task that genuinely succeeded gets told it failed.
#
# task.py only allows for delegate_task; delegate_build is included here as well because it has the
# same property for the same reason — it too authors files inside a sub-loop the parent cannot see.
_DELEGATING_TOOLS = frozenset({"delegate_task", "delegate_build"})

# Characters that mean an expected-artifact entry is a pattern rather than a literal path.
_GLOB_CHARS = ("*", "?", "[")

# _get_build_errors returns this exact prefix shape when tsc reported problems; anything else it
# returns is either a clean pass or a state where the check could not run at all.
_TSC_ERROR_LINE = re.compile(r"^\d+\s+type error\(s\)")

# How much of a pass detail to keep. These strings land in Task.validation_detail, which is
# re-sent to the model in its per-round context block (plan.task_context_block), so an unbounded
# listing of 200 matched artifact paths would be paid for on every subsequent round of the task.
_DETAIL_CHARS = 400


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    #: ALWAYS populated, including on a pass ("index.html exists, 41203 bytes"). A bare True with
    #: no explanation is indistinguishable, in a log or in the UI, from a check that never ran.
    detail: str
    #: Which validator names actually ran, in order — including ones that failed or were unknown,
    #: so the record shows what was attempted rather than only what succeeded.
    checked: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Ctx:
    """Everything a validator is allowed to look at. Frozen and passed by value so no validator can
    influence another one's result — each is an independent question about the world."""

    task: Task
    repository: str
    tools_called: tuple[str, ...]
    exit_codes: tuple[int, ...]
    snapshot_before: RepoSnapshot | None
    #: Serialized DesignIntent for this task, when it is a frontend task. Carried here so a
    #: validator can ask whether the artifact actually does what the intent called for.
    design: dict | None = None

    def effective_tools(self) -> set[str]:
        """The set of tools to check requirements against, with the delegation allowance applied."""
        called = set(self.tools_called)
        if called & _DELEGATING_TOOLS:
            called |= _DELEGATABLE_TOOLS
        return called


def _trim(text: str) -> str:
    return text if len(text) <= _DETAIL_CHARS else text[: _DETAIL_CHARS - 3] + "..."


# --- individual validators ----------------------------------------------------
# Each returns (passed, detail). Each may raise; validate_task catches and converts to a FAIL, so
# none of them needs its own defensive try/except for the unexpected.


def _artifacts_exist(ctx: _Ctx) -> tuple[bool, str]:
    """Every expected artifact is on disk and is actually a thing, not a promise of one.

    "Non-empty" was the first version of this rule and it was not enough. A real run wrote a genuine
    26,343-byte index.html, thrashed for three rounds, then overwrote it with the literal 11-byte
    text "PLACEHOLDER" — and the task passed validation, because non-emptiness was the entire
    question being asked. A check a token gesture can satisfy is the model's own "Done." wearing a
    validator's clothes. See `_substance_problem` for what is actually asked now.
    """
    patterns = [p.strip() for p in ctx.task.expected_artifacts if p and p.strip()]
    if not patterns:
        # The validator was listed but the task names nothing to check. Passing with an honest
        # detail beats failing closed here: a model-proposed plan can list this validator without
        # artifacts, and failing would deadlock the task on something the model cannot fix by doing
        # more work. The detail keeps it from reading as a verified pass.
        return True, "no expected artifacts declared for this task"

    root = repo_root(ctx.repository)  # HTTPException 404 if not loaded -> caught upstream as a FAIL
    found: list[str] = []
    problems: list[str] = []
    for pattern in patterns:
        if ".." in pattern.replace("\\", "/").split("/"):
            # expected_artifacts comes from a model-proposed plan; a traversal segment would let a
            # task validate itself against a file outside the repository entirely.
            problems.append(f"{pattern} (rejected: path escapes the repository)")
            continue
        if any(ch in pattern for ch in _GLOB_CHARS):
            matches = [p for p in root.glob(pattern) if _is_nonempty(p)]
            if matches:
                found.append(f"{pattern} matched {len(matches)} file(s)")
            else:
                problems.append(f"{pattern} (glob matched no non-empty file)")
            continue
        target = (root / pattern).resolve()
        if root not in target.parents and target != root:
            problems.append(f"{pattern} (rejected: path escapes the repository)")
        elif not target.exists():
            problems.append(f"{pattern} (missing)")
        elif not target.is_file():
            problems.append(f"{pattern} (exists but is not a file)")
        elif (problem := _substance_problem(target)) is not None:
            problems.append(f"{pattern} ({problem})")
        else:
            found.append(f"{pattern} exists, {target.stat().st_size} bytes")

    if problems:
        return False, _trim("not usable on disk: " + "; ".join(problems))
    return True, _trim("; ".join(found))


# A file this small cannot be a built artifact. Chosen from a real failure rather than taste: a run
# under the execution plan wrote a genuine 26,343-byte index.html, thrashed for three rounds, then
# overwrote it with the literal 11-byte text "PLACEHOLDER" — and the task validated, because the only
# question being asked was "is it non-empty". A validator satisfiable by a token gesture is not a
# validator; it is the model's own "Done." with an extra step.
_MIN_SUBSTANTIVE_BYTES = 200

# Whole-file contents that are a stand-in for work rather than the work. Matched against the entire
# stripped file, never against a substring — the word "placeholder" appearing inside a real 600-line
# page (a CSS class, an input's placeholder attribute) is completely ordinary and must not fail it.
_SENTINEL_CONTENTS = frozenset({
    "placeholder", "todo", "tbd", "coming soon", "wip", "stub", "content here",
    "<!doctype html>", "...", "n/a",
})

# Markup that must contain a body to be a page at all. A head-only HTML file is the shape produced by
# a model that writes its stylesheet, runs out of room, and intends to "fill in the rest next round".
_MARKUP_SUFFIXES = frozenset({".html", ".htm"})


def _substance_problem(path: Path) -> str | None:
    """Why this file is not a real artifact, or None if it looks like one.

    Deliberately shallow. This is not a quality judgement — it cannot tell a beautiful page from an
    ugly one, and should not try. It answers one much narrower question that the previous check got
    wrong: is there actually something here, or is this a promise of something? Everything it rejects
    is a file no amount of good intent could call finished.
    """
    try:
        if not path.is_file():
            return "does not exist"
        size = path.stat().st_size
    except OSError as exc:
        return f"could not be read ({exc})"
    if size == 0:
        return "is empty"
    if size < _MIN_SUBSTANTIVE_BYTES:
        # Read it before judging: a genuinely tiny file can be legitimate (a one-line config), so the
        # size alone only earns a closer look, not a rejection.
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return None
        if text.lower().strip("#/*<!->_ \t\n") in _SENTINEL_CONTENTS:
            return f"contains only a placeholder ({size} bytes: {text[:40]!r})"
        if path.suffix.lower() in _MARKUP_SUFFIXES:
            return f"is {size} bytes — too small to be a page"
    if path.suffix.lower() in _MARKUP_SUFFIXES:
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:200_000].lower()
        except OSError:
            return None
        if "<body" not in head and "</html>" not in head:
            # Head-only markup: the stylesheet got written and the page never did.
            return "has no <body> — the document was never finished"
    return None


def _is_nonempty(path: Path) -> bool:
    return _substance_problem(path) is None


def _tools_called(ctx: _Ctx) -> tuple[bool, str]:
    """Every tool the task declared it could not be finished without was actually dispatched."""
    required = [t for t in ctx.task.required_tools if t]
    if not required:
        return True, "no required tools declared for this task"
    missing = sorted(set(required) - ctx.effective_tools())
    if missing:
        return False, f"required tool(s) never called: {', '.join(missing)}"
    return True, f"called {', '.join(sorted(set(required)))}"


def _command_succeeded(ctx: _Ctx) -> tuple[bool, str]:
    """The most recent command this task ran exited 0.

    Most recent rather than all of them: a task that runs a build, sees it fail, fixes the cause and
    runs it again has succeeded, and requiring every historical exit code to be 0 would make the
    normal edit-run-edit-run loop unpassable. Exit codes arrive from Job.tool_exit_codes, a dict
    keyed by tool_call_id — insertion-ordered, so the caller's last element is genuinely the latest
    command, not an arbitrary one.
    """
    if not ctx.exit_codes:
        return False, "no command was run in this task (no exit code recorded)"
    last = ctx.exit_codes[-1]
    if last == 0:
        return True, f"last command exited 0 ({len(ctx.exit_codes)} run in this task)"
    return False, f"last command exited {last}"


def _no_build_errors(ctx: _Ctx) -> tuple[bool, str]:
    """No type/build errors reported for the repository.

    Reuses backend/agents/tools.py::_get_build_errors, which is safe to call from here on both
    counts that matter: it mutates nothing (`npx tsc --noEmit`), and it is bounded — it returns
    immediately without spawning anything when there is no tsconfig.json, and the subprocess it
    does spawn is capped at 30s by _run_command. That is not free, but it is bounded, and it only
    runs for a task that explicitly asked for this check.

    Three outcomes, not two. A clean report passes. A report naming errors fails. Anything else —
    the command timed out, npx is not installed, the process could not launch — is an ABSTENTION:
    it returns passed=True with a detail that says in words it was not checked. Failing a task
    because a toolchain is missing punishes the model for the environment; passing it silently
    would be a fabricated verification. Saying so is the only honest third option.
    """
    report = (_get_build_errors(ctx.repository) or "").strip()
    if report.startswith("No type errors"):
        return True, "no type errors"
    if report.startswith("No typecheck config found"):
        return True, "not checked: no typecheck config in this repository"
    if _TSC_ERROR_LINE.match(report):
        return False, _trim(report)
    return True, _trim(f"not checked: build error report was inconclusive ({report[:120]})")


def _screenshot_taken(ctx: _Ctx) -> tuple[bool, str]:
    """A screenshot was taken during this task.

    Weaker than it looks, and knowingly so: it proves the tool ran, not that the page rendered
    anything. A screenshot of ERR_CONNECTION_REFUSED satisfies this — that is a real observed
    escape (see backend/agents/progress.py::is_thrashing). This is the cheap half of the visual
    check; the honest half is that jobs.py feeds the actual image back to a vision-capable model.
    """
    if "screenshot" in ctx.tools_called:
        return True, "screenshot was taken"
    return False, "no screenshot was taken in this task"


def _files_changed(ctx: _Ctx) -> tuple[bool, str]:
    """At least one file was created or modified since the task started."""
    if ctx.snapshot_before is None:
        # No baseline exists — the job started this task before snapshots were being taken, or a
        # snapshot failed and degraded to empty. There is no way to answer the question, so say so
        # rather than guessing in either direction.
        return True, "not checked: no repository snapshot was taken when this task started"
    signal = compare(
        ctx.snapshot_before,
        snapshot(ctx.repository),
        tools_ran=ctx.tools_called,
    )
    if signal.created or signal.modified:
        return True, _trim(signal.describe())
    if signal.deleted:
        # Deliberately not a pass: this validator is defined as "created or modified", and a task
        # whose only effect was deletion should be declaring that intent some other way rather than
        # passing a check named files_changed by accident. Naming the deletions here is what keeps
        # that failure diagnosable instead of looking like nothing happened at all.
        return False, _trim(f"only deletions since this task started: {signal.describe()}")
    return False, "no file was created or modified since this task started"


_DESIGN_EVIDENCE = {
    # Each entry: (human name, list of regexes, how many distinct signals must be present).
    # These test for the PRESENCE OF A CAPABILITY, never for whether it was done tastefully. A page
    # with zero event listeners is not "a matter of opinion" — it cannot respond to anything. That is
    # the only kind of judgement this is allowed to make, and it is deliberately the floor rather
    # than a score: passing means the thing is capable of the behaviour its design intent called for,
    # not that the behaviour is good.
    "interaction": ("interactive behaviour", [
        r"addEventListener\s*\(", r"\bon(?:click|input|change|submit|keydown)\s*=",
        r"<button", r"<input", r"<select", r'role="button"',
    ], 2),
    "states": ("real interaction states", [
        r":hover\b", r":focus-visible\b", r":active\b",
        r"\[?(?:disabled|aria-disabled)\]?", r"\b(?:is-|\.)?(?:loading|empty|error)\b",
    ], 3),
    "motion": ("motion", [
        r"@keyframes\b", r"transition\s*:", r"IntersectionObserver",
        r"requestAnimationFrame", r"cubic-bezier\s*\(",
    ], 2),
    "responsive": ("responsive layout", [r"@media[^{]*\((?:max|min)-width"], 1),
    "accessibility": ("accessibility affordances", [
        r"aria-[a-z]+=", r":focus-visible\b", r"prefers-reduced-motion",
        r'role="[a-z]+"', r"<label", r"alt=",
    ], 2),
}


def _design_evidence(ctx: _Ctx) -> tuple[bool, str]:
    """Does the artifact actually DO what its design intent said it must?

    The gap this closes: a frontend was considered finished when its file existed and a screenshot
    had been taken. Both were true of a page with almost no JavaScript, no interaction states and no
    responsive behaviour — every visual instruction in the brief honoured, and essentially no
    behaviour. "The HTML runs" was being allowed to mean "the frontend is finished", so there was
    never a reason to iterate past merely acceptable.

    This checks the file for evidence of the specific capabilities the task's design intent asked
    for. It is emphatically NOT a quality score: it cannot tell a beautiful hover state from an ugly
    one, and does not try. It can tell the difference between a product and a brochure, which is the
    distinction that was actually being lost.
    """
    intent = ctx.design or {}
    wanted = [c for c in intent.get("quality_checks", []) if c in _DESIGN_EVIDENCE]
    if not wanted:
        return True, "no design intent attached to this task"

    paths = [p for p in ctx.task.expected_artifacts if p]
    if not paths:
        return True, "no artifact declared to inspect for design evidence"

    try:
        root = repo_root(ctx.repository)
    except Exception as exc:  # noqa: BLE001
        return False, f"repository unavailable: {exc}"

    text = ""
    for rel in paths:
        try:
            target = (root / rel).resolve()
            if root in target.parents and target.is_file():
                text += target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    if not text:
        return False, "no readable artifact to inspect"

    missing, present = [], []
    for key in wanted:
        label, patterns, need = _DESIGN_EVIDENCE[key]
        hits = sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))
        (present if hits >= need else missing).append(f"{label} ({hits}/{need})")

    if missing:
        return False, (
            "the artifact shows no sign of: " + "; ".join(missing) +
            ". This is a capability check, not a style opinion — add the behaviour itself, then "
            "look at it in the browser."
        )
    return True, "design evidence present: " + "; ".join(present)


def _renders_cleanly(ctx: _Ctx) -> tuple[bool, str]:
    """Open the artifact in a real browser and require that it renders and does not throw.

    This is the check that was actually missing, and finding that out corrected an earlier diagnosis
    of my own. The suspicion was that these builds contained too little interaction. Measured, they
    do not: one 51KB page had 16 event listeners, 11 buttons, 30 transitions, focus-visible styles
    and a reduced-motion block; another had 45 listeners and 52% of its bytes in JavaScript. The
    capability was there all along.

    What was missing was any check that it RUNS. The second of those pages renders blank — its
    script dies on a syntax error, so none of its 45 listeners are ever attached — and it passed two
    full "look at it and fix what is wrong" refinement passes because the only mechanical checks were
    "the file exists" and "a screenshot was taken". Both were true of a page showing nothing.

    So this asks the two questions a person asks in the first second of looking at a page: did
    anything appear, and did the console go red. Both are facts, not opinions, and neither can be
    satisfied by a description of the work.

    Skipped rather than failed when Playwright is unavailable — an environment without a browser
    should not fail a task the model cannot fix — and the detail says so plainly.
    """
    paths = [p for p in ctx.task.expected_artifacts if p and not any(c in p for c in _GLOB_CHARS)]
    if not paths:
        return True, "no single artifact declared to render"

    try:
        root = repo_root(ctx.repository)
    except Exception as exc:  # noqa: BLE001
        return False, f"repository unavailable: {exc}"

    target = (root / paths[0]).resolve()
    if root not in target.parents or not target.is_file():
        return False, f"{paths[0]} is not a readable file in this repository"

    from backend.agents.tools import _screenshot_structured

    text, _png = _screenshot_structured(ctx.repository, url=target.as_uri(), viewport="1440x900")
    if "Playwright not installed" in text:
        return True, "not checked: no browser available in this environment"
    if text.startswith("Screenshot failed"):
        return True, f"not checked: {text[:160]}"

    blank = "rendered essentially NOTHING" in text
    errors = "console error(s)" in text
    if blank or errors:
        problems = []
        if blank:
            problems.append("the page renders essentially nothing")
        if errors:
            problems.append("the page throws console errors")
        return False, (
            " and ".join(problems).capitalize() + ". Full report:\n" + _trim(text) +
            "\nFix the errors and confirm the page actually renders before calling this done."
        )
    return True, _trim(text.replace("\n", " | "))


_VALIDATORS: dict[str, Callable[[_Ctx], tuple[bool, str]]] = {
    "renders_cleanly": _renders_cleanly,
    "design_evidence": _design_evidence,
    "artifacts_exist": _artifacts_exist,
    "tools_called": _tools_called,
    "command_succeeded": _command_succeeded,
    "no_build_errors": _no_build_errors,
    "screenshot_taken": _screenshot_taken,
    "files_changed": _files_changed,
}


# --- the entry point ----------------------------------------------------------


def validate_task(
    task: Task,
    *,
    repository: str,
    tools_called_in_task: Sequence[str],
    exit_codes: Sequence[int] = (),
    snapshot_before: RepoSnapshot | None = None,
    design: dict | None = None,
) -> ValidationResult:
    """Run every validator the task declares. ALL must pass — AND, never OR.

    AND rather than OR because these checks are complements, not alternatives: "the file exists"
    and "the build is clean" are two different ways for the same task to be unfinished, and a task
    that satisfies one of them has satisfied one of them. Any OR here would let a task pass by
    doing whichever half was easiest, which is the same shape as the escape observed under
    tool_choice="required".

    An empty `task.validators` passes — legitimate for a genuinely non-artifact task (inspect the
    repo, decide a direction) and the reason plan.py keeps `complete()` separate from
    `record_validation()`. The detail says exactly what that pass means so it can never be read, in
    a log or in the UI, as a verified one.

    Never raises. This runs on the job thread; a validator that takes down the thread would lose the
    entire job — every round of work already done — over a check that was only meant to observe it.
    """
    names: list[str] = []
    for name in task.validators:
        if name and name not in names:  # duplicates in a model-proposed plan are noise, not signal
            names.append(name)

    if not names:
        return ValidationResult(
            passed=True,
            detail="no mechanical check for this task",
            checked=[],
        )

    ctx = _Ctx(
        task=task,
        repository=repository,
        tools_called=tuple(tools_called_in_task),
        exit_codes=tuple(exit_codes),
        snapshot_before=snapshot_before,
        design=design,
    )

    checked: list[str] = []
    passes: list[str] = []
    failures: list[str] = []
    for name in names:
        checked.append(name)
        validator = _VALIDATORS.get(name)
        if validator is None:
            # Fail closed. A plan that names a check nobody implements is a plan whose completion
            # has not been verified, and the cost of the two outcomes is asymmetric: a false fail
            # costs one more attempt at a task; a false pass ships an unfinished job as done.
            logger.warning(
                "validate_task: task %s references unknown validator %r (known: %s)",
                task.id, name, ", ".join(sorted(_VALIDATORS)),
            )
            failures.append(f"{name}: unknown validator, cannot verify this task")
            continue
        try:
            ok, detail = validator(ctx)
        except HTTPException as exc:  # repository not loaded, path refused
            ok, detail = False, f"could not check: {exc.detail}"
            logger.warning("validate_task: %s failed on task %s: %s", name, task.id, exc.detail)
        except Exception as exc:  # noqa: BLE001 - a broken validator must not end the job
            ok, detail = False, f"raised {type(exc).__name__}: {exc}"
            logger.warning("validate_task: %s raised on task %s: %s", name, task.id, exc)
        (passes if ok else failures).append(f"{name}: {detail}")

    if failures:
        return ValidationResult(passed=False, detail=_trim("; ".join(failures)), checked=checked)
    return ValidationResult(passed=True, detail=_trim("; ".join(passes)), checked=checked)


def infer_validators(task: Task) -> list[str]:
    """Best-effort validator list for a task proposed without one.

    A model asked to produce a plan reliably fills in objectives and artifacts and reliably omits
    the field that decides whether it is allowed to call itself finished — which is unsurprising,
    since that field exists specifically to constrain it. Rather than let such a task through with
    nothing to check (empty validators is a legitimate pass, see validate_task), derive the checks
    its own declarations already imply.

    Returns only names present in _VALIDATORS, so an inferred list can never fail closed on itself.
    """
    inferred: list[str] = []
    if any(a and a.strip() for a in task.expected_artifacts):
        inferred.append("artifacts_exist")

    required = {t for t in task.required_tools if t}
    if required == {"screenshot"}:
        # tools_called and screenshot_taken would be exactly the same check here. Prefer the one
        # that names what it is verifying — the failure message a model gets back is "no screenshot
        # was taken in this task" rather than a generic missing-tool list.
        inferred.append("screenshot_taken")
    elif required:
        # tools_called subsumes screenshot_taken whenever screenshot is one of several required
        # tools, so adding both would only produce a duplicate failure line for one cause.
        inferred.append("tools_called")

    # A task that both takes a screenshot and expects a single renderable artifact is, by
    # construction, the task whose job is to look at the result. That is exactly where "did it
    # actually render, and did the console go red" belongs — and where its absence let a page that
    # renders blank pass two refinement passes on the strength of "the file exists" and "a
    # screenshot was taken", both of which are true of a page showing nothing.
    renderable = [a for a in task.expected_artifacts
                  if a and a.strip().lower().endswith((".html", ".htm"))]
    if renderable and "screenshot" in required:
        inferred.append("renders_cleanly")

    return [name for name in inferred if name in _VALIDATORS]
