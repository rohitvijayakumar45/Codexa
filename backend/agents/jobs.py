"""Background job manager for the agent tool-calling loop.

The agent loop (classify intent -> stream a round -> execute tool calls -> repeat) used to run
inline inside the HTTP request's StreamingResponse generator. That ties the model's actual work to
the lifetime of one HTTP connection: a browser tab switch or a backend restart tears down the
connection, Starlette cancels the generator mid-round, and every token the provider already
generated (and billed) for that round is thrown away — the next attempt starts the whole
conversation over.

This module decouples the two. `JobManager.start` spawns the loop on a background thread, keyed by
a job id. The thread appends every SSE-shaped event to an in-memory log and checkpoints the full
job state (messages, round, tool call history) to disk after each round. The `/chat/agent/stream`
endpoint is just a subscriber: it replays the event log from index 0 (so reattaching after a dropped
connection sees the whole thing) and tails new events as they arrive. If the process restarts while a
job was mid-flight, the on-disk checkpoint lets `resume` continue the loop from the last completed
round instead of from scratch — only the in-flight round's tokens are ever wasted, not the whole
task.
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import queue
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

import litellm

from backend.agents.context_window import GRACE_MULTIPLIER_IN_RADIUS, relevant_paths
from backend.agents.controller import TASK_CONTEXT_MARK, ExecutionController
from backend.agents.design_intent import DesignIntent, brief as design_brief, derive as derive_design
from backend.agents.llm import LLMClient, is_rate_limit_error
from backend.agents.plan import ExecutionPlan, TaskStatus, ValidationState, summarize_for_event
from backend.agents.plan_builder import build_plan
from backend.agents.receipts import ActionReceipt, already_performed, record_receipt
from backend.agents import round_telemetry as telemetry
from backend.agents.task import (
    TaskContract,
    TaskIntent,
    build_task_prompt,
    generate_contract,
    resolve_contract_source,
    validate_completion,
)
from backend.agents.token_budget import predict_token_budget
from backend.agents.tools import (
    _COMPACTED_MARK,
    GRAPH_DIRTYING_TOOLS,
    classify_intent,
    execute_tool,
    groups_providing,
    parse_args,
    tools_for_groups,
)
from backend.agents.verification import build_correction_message, extract_claims, verify_claims
from backend.graph.service import GraphService
from backend.memory.store import MemoryStore
from backend.repository.api import reindex_repository

logger = logging.getLogger(__name__)

JOBS_DIR = Path(__file__).parent.parent / "data" / "jobs"

_STALE_AFTER_ROUNDS = 3
_MAX_ROUNDS = 10

# Debug escape hatch: CODEXA_ROUND_BUDGET=0 (or "unlimited") removes the round cap entirely, so a
# job runs until it finishes, fails, or is cancelled.
#
# Deliberately an env override rather than a raised constant, because this codebase has real history
# here: removing a bound to "let it finish" is what produced runs that burned quota until a human
# noticed. It is safe to use for debugging only because the round cap is not what makes a job
# terminate — the per-round generation budget, the wall-clock ceiling, the per-task round and
# intervention budgets, and the validation-attempt budget all still apply, and a plan whose tasks
# have all failed still ends the job. What this removes is the outer counter, which on a long
# legitimate build was firing before the work was done.
_UNLIMITED_ROUNDS = (os.getenv("CODEXA_ROUND_BUDGET", "").strip().lower() in ("0", "unlimited", "none"))
_STALL_NUDGE_TEXT = (
    "[SYSTEM: the connection stalled mid-response (provider timeout). "
    "Continue exactly from where you left off — do not repeat any text "
    "already written above. If you were in the middle of a tool call such "
    "as write_file, redo that call from scratch with the complete content, "
    "since a partial/interrupted tool call was not saved.]"
)

# Fires exactly once per streak (only when same_tool_signature_streak first EQUALS this, not >=),
# so it can't spam — the streak either breaks (signature changes, resets to 1) or keeps climbing
# silently past this point. Chosen to match cline's soft threshold (3) plus one, since a legitimate
# read-verify-read pattern can plausibly repeat 2-3 times; four in a row with identical arguments is
# past the point a human would call it deliberate.
_REPEAT_TOOL_CALL_THRESHOLD = 4
_TOOL_STATUS_LABELS = {
    "read_file": "Reading {path}",
    "write_file": "Writing {path}",
    "edit_file": "Editing {path}",
    "list_directory": "Looking through the repository",
    "run_command": "Running a command",
    "run_tests": "Running tests",
    "run_python": "Running Python",
    "search_code": "Searching the codebase",
    "grep": "Searching the codebase",
    "delete_file": "Deleting {path}",
    "git_diff": "Checking what's changed",
    "git_commit": "Committing changes",
}


def _friendly_tool_status(name: str, args: dict) -> str:
    """Human-readable status for a dispatched tool call, filling the same silent gap
    _round-start status covers but with detail specific to what's actually happening
    (rather than the generic "working on the next step") - directly what was asked for:
    something other than a bare "thinking" indicator while a model is mid-task."""
    path = args.get("path") or args.get("file_path") or args.get("filename") or ""
    template = _TOOL_STATUS_LABELS.get(name, "")
    if "{path}" in template:
        return template.format(path=path) if path else template.split(" {path}")[0]
    if template:
        return template
    return f"Using {name}" if name and not name.startswith("_") else "Working on the next step"


def _contract_from_dict(contract_dict: dict) -> TaskContract:
    """Rehydrate the serialized contract stored on the job. Factored out because three separate
    call sites in `_loop` were reconstructing it inline with the same six fields, and a field added
    to TaskContract had to be remembered in all of them."""
    return TaskContract(
        intent=TaskIntent(contract_dict.get("intent", TaskIntent.CONVERSATION.value)),
        required_tools=contract_dict.get("required_tools", []),
        allowed_tools=contract_dict.get("allowed_tools", []),
        success_criteria=contract_dict.get("success_criteria", []),
        constraints=contract_dict.get("constraints", []),
        suggested_workflow=contract_dict.get("suggested_workflow", []),
    )


def _attach_preamble(job: "Job", preamble: str) -> None:
    """Put the task prompt and design brief into the job's system message, whatever shape it is in.

    This is the second time this guarantee has been broken by the SHAPE of the caller's message
    rather than by its absence.

    The first version lived in backend/chat/api.py and ran only `if messages[0]["role"] ==
    "system"`, so a job started through the API with just a user message got no task prompt at all.
    Moving it here fixed that. But the frontend's system message is not a string: chat/api.py wraps
    it as `[{"type": "text", "text": ..., "cache_control": {...}}]` for prefix caching, and the
    replacement checked `isinstance(existing, str)` — so for every job started from the UI it
    matched neither branch and silently did nothing. Verified on a live job: TASK MODE present
    (added by the HTTP layer, which handles the list), DESIGN INTENT absent. The design pipeline was
    dark again, in exactly the way it had just been fixed not to be.

    So this handles all three shapes explicitly, and appends to the CACHED block on purpose: the
    preamble is stable for the life of the job, which is what a cached prefix is for.
    """
    if not preamble:
        return
    first = job.messages[0] if job.messages else None
    if first is None or first.get("role") != "system":
        job.messages.insert(0, {"role": "system", "content": preamble})
        job.message_rounds.insert(0, -100)
        return

    existing = first.get("content")
    if isinstance(existing, str):
        if "DESIGN INTENT" not in existing:
            first["content"] = existing + "\n\n" + preamble
        return
    if isinstance(existing, list):
        for block in existing:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if "DESIGN INTENT" not in text:
                    block["text"] = text + "\n\n" + preamble
                return
        existing.append({"type": "text", "text": preamble})
        return
    # Some other shape entirely — never silently drop it, which is the whole failure being fixed.
    job.messages.insert(0, {"role": "system", "content": preamble})
    job.message_rounds.insert(0, -100)


# The prefixes of the two recovery directives. Used to find and REPLACE a stale one rather than
# appending another, so exactly one is ever live.
_DIRECTIVE_MARKS = ("[SYSTEM: that round was stopped", "[SYSTEM: planning for this task")


def _replace_directive(
    messages: list[dict], message_rounds: list[int], text: str, current_round: int
) -> None:
    """Keep exactly one recovery directive in the transcript, at the end.

    The previous rule was "do not append if an identical one is among the last three messages", and
    it does not hold. By the time a later round is cut, the earlier directive has scrolled past that
    window behind the assistant/tool pairs in between — so it appended again. Measured on a live
    job: FOUR copies of the same 2,227-character execution directive, ~9KB of duplicated instruction
    re-sent on every subsequent request for the rest of the run.

    That is not merely wasteful. A history filling with byte-identical system messages is the exact
    pattern documented in this file's stall-recovery path as having preceded two providers going
    permanently silent, which is why that path collapses its own runs of nudges.

    Replacing rather than appending also keeps the instruction adjacent to the round it applies to,
    where a model is most likely to act on it. The two lists are edited together — they are
    index-matched and compaction reads round numbers positionally.
    """
    for i in range(len(messages) - 1, -1, -1):
        content = messages[i].get("content")
        if (
            messages[i].get("role") == "user"
            and isinstance(content, str)
            and content.startswith(_DIRECTIVE_MARKS)
        ):
            del messages[i]
            del message_rounds[i]
    messages.append({"role": "user", "content": text})
    message_rounds.append(current_round)


def _recent_non_context_messages(messages: list[dict], count: int) -> list[dict]:
    """The last `count` messages, ignoring the controller's execution-state block.

    That block is re-appended at the end of the transcript every round, so any "what was the
    previous message?" check reads it instead of the real one. Several guards in this loop are
    exactly that kind of check, and they must see the conversation, not the state banner sitting on
    top of it."""
    out: list[dict] = []
    for m in reversed(messages):
        content = m.get("content")
        if isinstance(content, str) and content.startswith(TASK_CONTEXT_MARK):
            continue
        out.append(m)
        if len(out) >= count:
            break
    return out


def _last_user_text(messages: list[dict]) -> str:
    """Fallback source for plan building when `job.contract_source` is absent — a job checkpointed
    by an older build, which would otherwise plan against an empty string."""
    for m in reversed(messages):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            return m["content"]
    return ""


class _GenerationBudgetExceeded(Exception):
    """One round generated too much, or ran too long, without producing an action.

    Carries WHY so the controller can recover differently for different causes — see
    backend/agents/controller.py. `chars` is deliberation only; tool-call arguments are never
    counted, because those are the product rather than the deliberation.
    """

    def __init__(self, chars: int, seconds: float, reason: str) -> None:
        super().__init__(f"round exceeded its {reason} budget ({chars} chars, {seconds:.0f}s)")
        self.chars = chars
        self.seconds = seconds
        self.reason = reason


# Deliberation characters one round may generate before it is cut. Counted across BOTH channels.
#
# The original version counted only `reasoning_content`, and that hole caused a real deadlock. A job
# sat on one round for over twenty minutes: not stalled (chunks kept arriving, so the 90s watchdog
# reset every time) and never cut (the counter saw nothing, because the model was deliberating in
# the CONTENT channel instead). Two guards, both blind, and an unbounded round between them. The
# lesson is that a budget which depends on correctly classifying what a provider is emitting will
# eventually be wrong about it — so this counts every character the model generates that is not a
# tool-call argument, and the wall-clock ceiling below backs it up regardless of classification.
_PLANNING_CHARS = 40_000
# Deliberation allowed in a round once a direction is committed.
#
# This was 18,000, on the theory that a committed direction means the thinking is done. That theory
# is wrong for precisely the task that matters most: a round whose job is to produce a 1,000-line
# document legitimately deliberates about its content before emitting the first token of the tool
# argument. Measured on a real run, three consecutive rounds were cut at 18,004 / 18,007 / 18,004
# characters — the same "regenerate and discard" signature as the original 40k deadlock, at a lower
# threshold, with no artifact produced.
#
# So the budget follows what the task must PRODUCE, not what phase it is in. A task expecting an
# artifact gets the full planning allowance, because composing that artifact is the deliberation. A
# task that only has to run or verify something gets the short leash, which is where the original
# reasoning does hold.
_EXECUTION_CHARS = 18_000
_AUTHORING_CHARS = _PLANNING_CHARS

# The backstop. Independent of channel, of token counting, and of anything the provider chooses to
# call its output — the one guard that cannot be evaded by emitting through an unexpected field.
# Generous: a large write_file legitimately streams for minutes on a slow free-tier provider, and
# cutting real output would be far worse than the hang this prevents.
_MAX_ROUND_SECONDS = 9 * 60.0

# Debug escape hatch, same shape as CODEXA_ROUND_BUDGET: CODEXA_ROUND_SECONDS=0 removes the
# wall-clock ceiling.
#
# Worth stating why it needs one. This ceiling was chosen precisely because it does NOT depend on
# classifying what the model is emitting — that independence is what let it catch a deadlock the two
# character budgets were blind to. But it is the same independence that makes it unable to tell
# "thinking in circles for nine minutes" from "streaming a 500-line document for nine minutes", and
# on a slow free-tier provider the second is ordinary. Observed cutting a write at 14,596 characters
# — far under the authoring budget — purely on elapsed time, leaving "..." on disk.
#
# With this off, the character budgets and the per-task budgets still bound the job; what is lost is
# the backstop against a round that emits through a channel nothing counts.
if os.getenv("CODEXA_ROUND_SECONDS", "").strip().lower() in ("0", "unlimited", "none"):
    _MAX_ROUND_SECONDS = float("inf")


# Back-compat alias: the exception was named for the reasoning channel before it learned to
# count both. Kept so existing imports resolve to the same class rather than silently catching
# nothing.
_ReasoningBudgetExceeded = _GenerationBudgetExceeded
_MAX_REASONING_CHARS_PER_ROUND = _PLANNING_CHARS

_COMMIT_FIRST_TEXT = (
    "[SYSTEM: that round was stopped — it spent its whole generation budget deciding, and the "
    "work was lost because nothing recorded it. That has now happened without producing anything, "
    "so stop deciding and record what you have already decided.\n\n"
    "Your next message must be a single commit_direction call. It is cheap, it writes nothing to "
    "disk, and it is the only thing that makes your decision survive into the next round. Give it "
    "the concept in one or two sentences, the handful of implementation decisions that must not be "
    "re-litigated (typography, palette, layout approach, the signature interaction), the primary "
    "artifact path, and the concrete next call.\n\n"
    "If you have not decided yet, decide now with whatever you have and commit that — a committed "
    "direction you refine while building is worth incomparably more than a better one you never "
    "reach.]"
)

# The decision/action split for authoring specifically. Measured cause: an authoring round given
# no structure to follow reasons through the WHOLE artifact in its head — every section, every
# interaction — before emitting a single character of the file, and that reasoning routinely runs
# past the budget before the tool call ever arrives. One job cut on the exact same authoring task
# twice in a row for this reason (rounds 4 and 5, ~80,000 characters combined, both discarded) and
# only wrote the file on round 6, once forced. The fix already exists for the project-direction
# decision (commit_direction, above) — this is that same mechanism, one level down: instead of
# forcing the expensive write directly, force the cheap plan for THIS artifact first. A concrete
# section list to implement is a much shorter horizon than "write the whole thing," and the
# artifact tool that follows has something to execute rather than something to still work out.
_STRUCTURE_FIRST_TEXT = (
    "[SYSTEM: that round was stopped — it spent its whole budget reasoning through this artifact "
    "in full before writing any of it, and none of that reasoning survived the cut.\n\n"
    "Your next message must be a single commit_direction call, using the `structure` field only: "
    "the sections and interactions this artifact needs, in order, one short phrase each. Do not "
    "restate the project direction — that is already settled. This is only the plan for the file "
    "you are about to write. The call after this one is the write itself, implementing exactly "
    "this list.\n\n"
    "Name WHAT each section is, never HOW it is built — 'filterable archive grid', not the actual "
    "HTML for it. A phrase containing a tag, a selector or a line of code means the artifact is "
    "leaking into the plan instead of the write, which is the exact failure this call exists to "
    "avoid.]"
)


def _execution_directive(commitment: dict | None, forced_tool: str | None) -> str:
    """The message that opens an execution round: what was settled, and the one thing left to do.

    Carries decisions and outcomes, never deliberation. Replaying the reasoning that produced a
    decision is what invites a model back into the deliberation it was cut out of; replaying the
    decision itself ends it.
    """
    lines = ["[SYSTEM: planning for this task is finished. The direction below is settled — do not "
             "reconsider it, do not compare alternatives, do not restate it.", ""]
    if commitment:
        if commitment.get("direction"):
            lines.append(f"COMMITTED DIRECTION: {commitment['direction']}")
        for decision in commitment.get("decisions", [])[:8]:
            lines.append(f"  - {decision}")
        if commitment.get("primary_artifact"):
            lines.append(f"PRIMARY ARTIFACT: {commitment['primary_artifact']}")
        lines.append("")
    if forced_tool:
        lines.append(
            f"OUTSTANDING ACTION: call {forced_tool} now, and nothing else. Write the complete "
            "content in that one call — a partial version you intend to finish later costs a second "
            "full generation of everything you already wrote."
        )
    else:
        lines.append("OUTSTANDING ACTION: perform the implementation this task requires, with a tool.")
    lines.append("]")
    return "\n".join(lines)

# Superseded by the two directives above, which distinguish 'decide first' from
# 'the decision is made, act'. Kept so older references resolve.
_REASONING_NUDGE_TEXT = _COMMIT_FIRST_TEXT


_MAX_STALL_RECOVERIES = 2
# This no longer needs to be raised on its own to tolerate a genuinely flaky provider — once
# exhausted, error_reason="stall_exhausted" now flows through the SAME auto-continue mechanism as
# round-exhaustion (reset to 0, retried, bounded by _MAX_AUTO_CONTINUES below), so the real total
# tolerance for a job is _MAX_STALL_RECOVERIES * _MAX_AUTO_CONTINUES mid-stream failures across its
# whole run, not just this number. Composing the two bounded mechanisms this way was the actual fix
# for a job that died needing a manual restart despite its auto-continue counter being nowhere near
# its own cap — this exhaustion reason simply wasn't recognized by that mechanism at all before.
# How many times a job auto-continues itself past running out of tool-calling rounds before it
# finally surfaces to the user with the manual Continue action instead. Originally set to 2 on the
# untested assumption that "most large-but-legitimate builds finish within one or two of these" —
# real overnight evidence directly contradicted that: an ambitious full-stack build (ORBIT)
# genuinely needed on the order of 15 rounds of extension to make real forward progress (50+ real
# files written), not 2. At the old cap, a live, healthy, still-progressing job was hitting this
# limit and requiring a manual restart to do the EXACT same thing this mechanism already does
# (bump round_budget, reset counters) — turning a self-healing case into a disruptive one. Raised
# to give real ambitious tasks enough headroom to actually finish unattended; a genuinely
# stuck/thrashing job (see: the repeated-tool-call/no-progress pattern found the same night, not
# yet guarded against here) still isn't caught by round-count alone regardless of this number, so
# raising it doesn't materially worsen that separate, already-identified risk.
# A ceiling stays, and the reason is empirical rather than cautious: removing it made several test
# suites hang outright, because nothing in this loop can tell "still making real progress" from
# "failing identically forever". Against a permanently broken provider an uncapped job does not
# stop — it burns quota until a human cancels it. That is the same shape as the thrashing seen in a
# real overnight run (80 run_commands, no new files, no falling error count), just without the
# backstop. The genuinely correct fix is progress-based stopping, not a bigger number; until that
# exists this bound is what guarantees termination.
#
# 20 rather than the original 2: real evidence showed an ambitious full-stack build legitimately
# needing ~15 extensions to finish, so a small cap was interrupting healthy jobs to ask a human to
# press a button that does exactly what this already does. Override with CODEXA_MAX_AUTO_CONTINUES.
_MAX_AUTO_CONTINUES = int(os.getenv("CODEXA_MAX_AUTO_CONTINUES", "20") or 20)
# A REAL, observed failure mode: a provider (seen live on tokenrouter/GLM) accepted the request and
# kept the connection open but never sent a single byte back — not even a keepalive — for over 25
# minutes straight, with zero log activity. The per-call `timeout=` kwarg passed to litellm did NOT
# catch this (a fully silent connection isn't the same as a dropped one, and evidently isn't what
# that timeout enforces for every provider/proxy shape). Neither could job.cancelled help — it's
# only checked between chunks, and zero chunks were ever arriving. _stream_with_watchdog enforces
# OUR OWN wall-clock deadline independently of whatever the HTTP client's timeout does or doesn't
# catch, by running the actual iteration in a background thread and raising TimeoutError from the
# consumer side if nothing (chunk, completion, or error) shows up within this many seconds — which
# then flows into the EXISTING stall-recovery retry path below exactly like any other TimeoutError.
_CHUNK_TIMEOUT_SECONDS = 90.0

# Checkpoint write retries. Sized for the failure actually seen (a sync client or scanner holding a
# file open for a few milliseconds), not for a disk that is genuinely full or read-only — against
# those this gives up quickly and says so. Worst case adds ~0.15s to one checkpoint, which is
# nothing next to a round.
_CHECKPOINT_ATTEMPTS = 5
_CHECKPOINT_RETRY_DELAY = 0.01


def _stream_with_watchdog(source: Iterator[Any]) -> Iterator[Any]:
    """Re-yields everything from `source`, but raises TimeoutError if _CHUNK_TIMEOUT_SECONDS pass
    with nothing arriving — chunk, natural completion, or an error from `source` itself. Runs the
    real iteration in a daemon thread so a call that never returns at all (the actual incident this
    exists for) can't block the caller forever: if it eventually does resolve after we've already
    given up, the producer thread just finishes writing to a queue nobody's reading, then exits."""
    q: "queue.Queue[tuple[str, Any]]" = queue.Queue()
    # Signals the producer to stop pulling from the provider once the consumer is finished with it.
    # Without this, a consumer that stops early — the reasoning-budget cut, a caller that breaks out,
    # any exception raised while iterating — leaves the producer looping forever on a live stream:
    # it keeps consuming provider quota for output nobody reads and keeps growing an unbounded
    # queue, for the lifetime of the process. Daemon threads only die at shutdown, which for a
    # long-running server is never.
    stop = threading.Event()

    def _produce() -> None:
        try:
            for item in source:
                if stop.is_set():
                    break
                q.put(("chunk", item))
            else:
                q.put(("done", None))
        except Exception as exc:  # noqa: BLE001 - forwarded to the consumer, not swallowed
            q.put(("error", exc))
        finally:
            close = getattr(source, "close", None)
            if callable(close):
                try:
                    close()  # ends the underlying HTTP response rather than leaving it open
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    pass

    threading.Thread(target=_produce, daemon=True).start()
    try:
        while True:
            try:
                kind, payload = q.get(timeout=_CHUNK_TIMEOUT_SECONDS)
            except queue.Empty:
                raise TimeoutError(
                    f"No response from the model for {_CHUNK_TIMEOUT_SECONDS:.0f}s — the connection "
                    "was accepted but stayed silent (treating this as a stall)."
                ) from None
            if kind == "chunk":
                yield payload
            elif kind == "error":
                raise payload
            else:
                return
    finally:
        # Setting `stop` alone is not cancellation, it is a request the producer can only honour
        # AFTER its next chunk arrives — which on a model mid-way through a long reasoning pass can
        # be a very long time, and on a silent connection is never. For that whole window the
        # provider keeps generating and keeps billing for output nobody will read. That is exactly
        # the case the reasoning-budget cut creates, so it is the common path, not an edge one.
        #
        # Closing the response from the consumer side is what actually propagates the cancellation:
        # it tears down the underlying HTTP stream, so the producer's blocked `next()` raises
        # instead of waiting and the generation stops at the provider. The producer's own `finally`
        # still closes too — harmless, and it remains the path for a normal end-of-stream.
        stop.set()
        close = getattr(source, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 - best-effort; a failed close must not mask the real error
                logger.debug("stream close on cancel failed", exc_info=True)


def _mark_wait(job: "Job", state: str) -> None:
    """Bracket-log a potentially-blocking wait boundary and refresh the job's progress clock.

    Adopted from goose's WAITING_LLM_STREAM_START/END, WAITING_TOOL_START/END:name pattern (see
    HARNESS_RESEARCH_FINDINGS.md problem 2). The point: when a job goes silent for a long time,
    the last log line names exactly what it was waiting on — a stuck stream vs. a stuck tool vs.
    genuinely idle between rounds — instead of the loop just going dark with nothing to grep for.

    last_activity_ts is what a status poll reports as idle_seconds. It is refreshed here, at wait-
    boundary transitions, not only once per completed round — a job stuck mid-round (blocked on a
    single slow tool call, say) still shows a real, moving number instead of one that only updates
    on round completion and would otherwise read as "idle" for however long that round takes.
    """
    job.current_wait_state = state
    job.last_activity_ts = time.time()
    logger.debug("job=%s wait_state=%s", job.id, state)


def _tool_call_signature(name: str, args: dict) -> str:
    """Canonical (order-independent) identity for one tool call, used to detect exact repeats.

    A round can look completely healthy by every existing signal here — a tool ran, a result came
    back, the round-counter advanced — while still being pure waste if it's the Nth identical
    read_file("same/path") in a row. Nothing based on round completion can see that shape; this is
    a second, independent detector (goose's tool_monitor.rs / cline's LoopDetectionTracker) keyed
    on call identity instead. json.dumps(sort_keys=True) makes two calls with the same arguments in
    a different key order compare equal, same as cline's canonical-JSON signature.
    """
    try:
        canonical = json.dumps(args, sort_keys=True, default=str)
    except TypeError:
        canonical = str(args)
    return f"{name}:{canonical}"


# A plain assistant reply past this size is essentially never a normal chat answer — it's a code/
# file dump narrated as text (e.g. a model that couldn't or didn't call write_file and pasted the
# whole file inline instead). Left uncompacted, one such message gets re-sent in full on every
# subsequent round of every later job in the same conversation, for the rest of the conversation's
# life — the single largest driver of a job's cumulative prompt-token cost ballooning over rounds.
_LARGE_ASSISTANT_TEXT_CHARS = 4000


def _compact_stale_payloads(
    messages: list[dict], message_rounds: list[int], current_round: int,
    *, graph: Any = None, repository: str | None = None,
    task_start_rounds: dict[str, int] | None = None,
) -> None:
    """Collapse bulky tool payloads a few rounds after the model has already acted on them, so a
    long task doesn't keep re-sending the same huge blobs every round. When a graph is available,
    a write_file/edit_file payload for a file still within the current blast-radius neighborhood
    (backend/agents/context_window.py) gets extra rounds of grace before compaction — the model is
    more likely to still need it — while a payload for a file the task has clearly moved past
    compacts on the normal, shorter schedule. A large plain-text assistant reply (no tool_calls)
    compacts on the flat schedule too — a wall of narrated code/file content that was never actually
    written via write_file otherwise sits in history at full size forever.

    get_design_guidance is pinned (SWE-agent's history_processors.py tag-based-pin pattern, see
    HARNESS_RESEARCH_FINDINGS.md problem 3 — never elided, not even on the flat schedule) for as
    long as it was fetched during the CURRENTLY active task. This is the direct fix for a real,
    diagnosed bug: guidance loaded during planning was going stale by round 3, several rounds
    before the authoring round that actually needed it, so the model authored generic output
    having "forgotten" the very rules it fetched earlier in the same task. A call made during an
    EARLIER task still compacts on the normal schedule — only the live task's guidance is exempt.
    task_start_rounds tracks the round each task began; the highest value in it is the currently
    active task's start round (tasks start in order, exactly one active at a time), used here as a
    cheap proxy that needs no extra plumbing from the caller.
    """
    protected_paths: set[str] | None = None
    if graph is not None and repository is not None:
        try:
            protected_paths = relevant_paths(messages, repository=repository, graph=graph)
        except Exception:  # noqa: BLE001 - a lookup failure should just fall back to the flat rule
            protected_paths = None
    current_task_start = max(task_start_rounds.values()) if task_start_rounds else None

    for i, msg in enumerate(messages):
        age = current_round - message_rounds[i]
        if msg.get("role") == "tool" and msg.get("name") == "get_design_guidance":
            if current_task_start is not None and message_rounds[i] >= current_task_start:
                continue  # pinned: fetched during the task that's still in progress right now
            if age < _STALE_AFTER_ROUNDS:
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and not content.startswith(_COMPACTED_MARK):
                msg["content"] = (
                    f"{_COMPACTED_MARK} — this design guidance ({len(content)} chars) was loaded "
                    "earlier in this conversation and already used. Call get_design_guidance again "
                    "if you need to re-check its rules.]"
                )
        elif msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                if fn.get("name") not in ("write_file", "edit_file"):
                    continue
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(args, dict):
                    # A model can emit arguments that are valid JSON but not an object — a bare
                    # string or a list. json.loads then SUCCEEDS and the next line does .get() on a
                    # str, raising AttributeError out of compaction, which runs outside any try in
                    # the round loop. That killed the job with error_reason=None, so it was neither
                    # auto-continued nor eligible for Continue, and the bad message stayed in the
                    # history so every resume re-crashed on it. Permanently unrecoverable, from one
                    # malformed argument.
                    continue
                threshold = _STALE_AFTER_ROUNDS
                if protected_paths and args.get("path") in protected_paths:
                    threshold *= GRACE_MULTIPLIER_IN_RADIUS
                if age < threshold:
                    continue
                changed = False
                for key in ("content", "new_text", "old_text"):
                    val = args.get(key)
                    if isinstance(val, str) and len(val) > 200 and not val.startswith(_COMPACTED_MARK):
                        # Self-describing on purpose. The old text ("N chars, already written to
                        # disk.") assumed the reader remembered writing it — true for the model that
                        # made the call, false for one that just took over mid-job via key/model
                        # rotation, which sees only this string with no memory behind it. That
                        # reader has been observed copying the marker into a real file as if it were
                        # content, destroying it. Spelling out what this is, what to do instead, and
                        # what never to do makes the placeholder safe to encounter cold — the guard
                        # in tools.py stays as the backstop, but it should not be what's load-bearing.
                        args[key] = (
                            f"{_COMPACTED_MARK} — {len(val)} chars omitted from this transcript to "
                            f"save context. THIS IS NOT FILE CONTENT and never was: the real content "
                            f"was already written to disk successfully by this call. To see what is "
                            f"actually there now, call read_file on this path. Never copy this text "
                            f"into a file or pass it as content to any tool.]"
                        )
                        changed = True
                if changed:
                    fn["arguments"] = json.dumps(args)
        elif msg.get("role") == "assistant" and not msg.get("tool_calls"):
            if age < _STALE_AFTER_ROUNDS:
                continue
            content = msg.get("content", "")
            if (
                isinstance(content, str)
                and len(content) > _LARGE_ASSISTANT_TEXT_CHARS
                and not content.startswith(_COMPACTED_MARK)
            ):
                msg["content"] = (
                    f"{_COMPACTED_MARK} — a prior reply here narrated {len(content)} chars of text "
                    "(often a code/file dump instead of an actual write_file call). Redacted since "
                    "it's stale — re-read the real file with read_file if you need its contents.]"
                )
        elif msg.get("role") == "user" and isinstance(msg.get("content"), list):
            # A screenshot follow-up (see jobs.py's tool-call loop, appended right after a
            # screenshot tool result). A base64 PNG is the single heaviest thing that can end up
            # in this message history — far worse per-round than any text payload above — and once
            # the model has actually looked at it and moved on, re-sending it every remaining round
            # is pure waste. Same flat schedule as everything else here.
            if age < _STALE_AFTER_ROUNDS:
                continue
            blocks = msg["content"]
            if any(b.get("type") == "image_url" for b in blocks if isinstance(b, dict)):
                msg["content"] = (
                    f"{_COMPACTED_MARK} — a screenshot was shown here and already reviewed. "
                    "Call screenshot again if you need to see the current state.]"
                )


@dataclass
class Job:
    id: str
    repository: str
    model: str
    messages: list[dict] = field(default_factory=list)
    message_rounds: list[int] = field(default_factory=list)
    round: int = 0
    tools_called: list[str] = field(default_factory=list)
    # Real exit codes from run_command/run_tests calls this job has made, keyed by tool_call_id — the
    # ground truth backend/agents/verification.py binds a "tests passed" claim to, instead of trusting
    # the model's own reading of the command's text output.
    tool_exit_codes: dict[str, int] = field(default_factory=dict)
    active_tool_groups: list[str] = field(default_factory=list)
    contract: dict | None = None  # serialized TaskContract
    working_repo: str = "codexa-os"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    stall_recoveries: int = 0
    cancelled: bool = False
    status: str = "running"  # running | done | error | interrupted
    # round_budget starts at _MAX_ROUNDS but can be raised (see JobManager.continue_job) — a
    # genuinely large task hitting the round cap is NOT the same failure as a stalled/broken job,
    # and until this existed the only recovery was the frontend starting an entirely new job from a
    # condensed text history, throwing away every tool call and all reasoning already done.
    # error_reason distinguishes "ran out of rounds" (continuable — just needs a bigger budget and
    # the SAME message history) from every other terminal error (not continuable the same way).
    round_budget: int = _MAX_ROUNDS
    error_reason: str | None = None
    # How many times _run has already auto-continued this job past a round-exhaustion error — see
    # _MAX_AUTO_CONTINUES. Bounded so a genuinely stuck/looping job still surfaces to the user
    # instead of silently re-running forever; a user-triggered continue_job() does NOT count here
    # (it's an explicit choice, not automatic), which is why it's a separate counter from that.
    auto_continues: int = 0
    events: list[dict] = field(default_factory=list)
    # Hash-chained log of every mutating tool call this job has made (backend/agents/receipts.py) —
    # tamper-evident (each entry commits to the previous one's result hash), and lets a resumed round
    # recognize a mutating call it already performed instead of repeating it (see `already_performed`).
    receipts: list[ActionReceipt] = field(default_factory=list)
    # --- persistent execution plan (backend/agents/plan.py) -------------------------------------
    # The serialized ExecutionPlan. This is the job's execution POSITION, and it is checkpointed
    # with everything else precisely so that a restart, a model rotation, or a user clicking
    # Continue all resume on the same task with the same history — rather than handing a fresh model
    # the whole problem again and hoping it re-derives where the last one had got to.
    plan: dict | None = None
    # The text the contract (and therefore the plan) was generated from. Stored because a bare
    # "continue" nudge is not what should be planned against — see task.resolve_contract_source —
    # and because a resumed job must be able to rebuild its plan from the ORIGINAL request rather
    # than from whatever the most recent message happened to be.
    contract_source: str = ""
    # Serialized DesignIntent (backend/agents/design_intent.py) for a frontend task, else None.
    # Persisted so a resumed job, a rotated model and every refinement pass all build against
    # the same decided intent rather than re-inferring one from whatever is left in context.
    design: dict | None = None
    # What the agent has DECIDED, recorded by the commit_direction tool. This is the semantic
    # checkpoint: a compact set of settled facts that survives a cut round, so the next round
    # continues from "I already decided what this is, now build it" instead of re-deriving the same
    # decisions and being cut again at the same size. Never chain-of-thought — a discarded
    # transcript cannot be a continuity mechanism, which is exactly why the previous design
    # deadlocked.
    commitment: dict | None = None
    # Consecutive rounds cut without the active task advancing. Reset by real progress and by a task
    # change. Drives escalation: two identical cuts in a row means repeating the round is pointless,
    # so the controller must change execution mode rather than retry.
    consecutive_cuts: int = 0
    # Where in `tools_called` / `exit_code_log` each task began. Without these, a per-task validator
    # would answer "did this task call write_file?" using a write_file from three tasks ago, and
    # every later task would validate itself on the strength of earlier work.
    task_tool_offsets: dict[str, int] = field(default_factory=dict)
    task_exit_offsets: dict[str, int] = field(default_factory=dict)
    # Exit codes in the order they happened. `tool_exit_codes` is keyed by tool_call_id, which is
    # the right shape for claim verification but cannot answer "what did THIS task's commands
    # return" — that needs an ordered log to slice.
    exit_code_log: list[int] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    # --- wait-state / stall telemetry (see _mark_wait, _tool_call_signature) --------------------
    # What the loop is blocked on right now: "idle" between rounds, "WAITING_LLM_STREAM", or
    # "WAITING_TOOL:<name>". Paired with last_activity_ts so a status poll can report "stuck on
    # WAITING_TOOL:run_command for 7123s" instead of a bare "running" that looks the same whether
    # the job is one second or seven hours into a hang.
    current_wait_state: str = "idle"
    last_activity_ts: float = field(default_factory=time.time)
    # Consecutive identical (tool_name, canonicalized-args) calls. Independent of round_budget,
    # stall_recoveries and consecutive_cuts above — none of those can see a round that "succeeds"
    # by every existing measure while just repeating the same no-op call. See _tool_call_signature.
    last_tool_signature: str | None = None
    same_tool_signature_streak: int = 0

    def to_disk(self) -> dict:
        d = asdict(self)
        d.pop("events")  # event log is replayed from memory; checkpoint only needs resumable state
        return d

    @classmethod
    def from_disk(cls, data: dict) -> "Job":
        data = dict(data)
        data["events"] = []
        data["receipts"] = [ActionReceipt.from_dict(r) for r in data.get("receipts", [])]
        return cls(**data)


class JobManager:
    def __init__(self, *, llm: LLMClient, graph: GraphService | None, store: MemoryStore | None) -> None:
        self._llm = llm
        self._graph = graph
        self._store = store
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        JOBS_DIR.mkdir(parents=True, exist_ok=True)

    # --- persistence ---------------------------------------------------------
    def _checkpoint(self, job: Job) -> None:
        """Persist the job's resumable state. Retries the atomic rename, because on this platform it
        fails transiently and losing a checkpoint is not a cosmetic failure.

        Observed on a real overnight run, repeatedly:

            job checkpoint failed for 05d1f8b6: [WinError 5] Access is denied:
            '...\\backend\\data\\jobs\\05d1f8b6.tmp' -> '...\\backend\\data\\jobs\\05d1f8b6.json'

        The project lives under OneDrive, and the sync client (an indexer or antivirus does the same)
        briefly opens files it notices changing. `os.replace` onto a handle another process holds
        fails immediately on Windows — unlike POSIX, where the rename would simply succeed. It is a
        race measured in milliseconds, and the old code treated it as unrecoverable: one warning,
        checkpoint dropped.

        What that costs is much more than a log line. The checkpoint IS the job's resumable state and
        its execution position — a lost one means a restart resumes at a stale round, the plan
        silently reverts to an older snapshot, and anything reading the file to find out what the job
        is doing is told something untrue. Retrying with a short backoff turns a lost checkpoint back
        into what it actually is: a write that needs to happen a few milliseconds later.
        """
        job.updated_at = time.time()
        path = JOBS_DIR / f"{job.id}.json"
        tmp = path.with_suffix(".tmp")
        payload = json.dumps(job.to_disk())
        last: OSError | None = None
        for attempt in range(_CHECKPOINT_ATTEMPTS):
            try:
                tmp.write_text(payload, encoding="utf-8")
                os.replace(tmp, path)
                if attempt:
                    logger.info("job %s: checkpoint succeeded on attempt %s", job.id, attempt + 1)
                return
            except OSError as exc:
                last = exc
                # Linear backoff: the lock is held by another process for a few milliseconds, not
                # contended in a way that needs exponential politeness.
                time.sleep(_CHECKPOINT_RETRY_DELAY * (attempt + 1))
        # Genuinely could not write. Still never raises — a job that dies because it could not
        # journal itself is worse than one running with a stale checkpoint — but this is now a real
        # anomaly rather than routine noise, so it is logged as an error.
        logger.error(
            "job %s: checkpoint FAILED after %s attempts (%s) — resume state is now stale",
            job.id, _CHECKPOINT_ATTEMPTS, last,
        )

    def _load_from_disk(self, job_id: str) -> Job | None:
        path = JOBS_DIR / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            return Job.from_disk(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning("job checkpoint unreadable for %s: %s", job_id, exc)
            return None

    # --- lifecycle -------------------------------------------------------------
    def create(self, *, repository: str, model: str, messages: list[dict]) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            repository=repository,
            model=model,
            messages=messages,
            message_rounds=[-100] * len(messages),
            working_repo=repository,
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def start(self, job: Job, *, last_user_text: str) -> None:
        # A bare nudge ("continue", "hi", a typo of either) sent mid-task — because the model
        # stalled or silently skipped a required tool call — carries no task information of its
        # own. generate_contract runs fresh per job (one per chat send, not once per conversation),
        # so contracting against the nudge alone would classify it as CONVERSATION and silently drop
        # whatever tool requirement the real outstanding task had, letting the model narrate a fake
        # "done" with nothing left to enforce it. Must match backend/chat/api.py's own
        # resolve_contract_source call for this same job's messages — see that function's docstring.
        contract_source = resolve_contract_source(last_user_text, job.messages[:-1] if job.messages else [])
        contract = generate_contract(contract_source)
        job.contract = {
            "intent": contract.intent.value,
            "required_tools": contract.required_tools,
            "allowed_tools": contract.allowed_tools,
            "success_criteria": contract.success_criteria,
            "constraints": contract.constraints,
            "suggested_workflow": contract.suggested_workflow,
        }
        intent = derive_design(contract_source, contract)
        groups = set(classify_intent(contract_source))
        # The contract decides what this job MUST do; the groups decide what it CAN do. Those two
        # were derived independently from the same text by different regexes, so they disagreed —
        # a job could be required to call write_file and never be offered it. Union them.
        groups |= groups_providing(contract.required_tools)
        if intent is not None:
            # A frontend task is told which design skills to load; the tool that loads them has to
            # be there.
            groups |= groups_providing(["get_design_guidance", "screenshot", "start_dev_server"])
        job.active_tool_groups = sorted(groups)
        # Kept so _loop can build (or rebuild) the execution plan from the ORIGINAL request. A plan
        # derived from a later "continue" nudge would describe the wrong job entirely.
        job.contract_source = contract_source

        # --- design intent, and the task prompt itself -----------------------------------------
        # Both are assembled HERE, server-side, rather than by the HTTP layer. backend/chat/api.py
        # appends build_task_prompt to the system message only `if messages[0]["role"] == "system"`,
        # so a job started through the API with just a user message silently received no task prompt
        # at all: no TASK MODE, no REQUIRED TOOLS, no constraints. Every job of a real overnight
        # benchmark run was in exactly that shape. A guarantee that depends on what the caller
        # happened to send is not a guarantee.
        job.design = intent.to_dict() if intent else None
        preamble = "\n\n".join(
            x for x in (build_task_prompt(contract), design_brief(intent)) if x
        )
        _attach_preamble(job, preamble)
        # Informational, not enforced (backend/agents/token_budget.py) — how many tokens tasks of
        # this same classified intent have actually cost historically, surfaced before any work
        # starts. Safe to compute before the thread launches: job.events isn't touched by anything
        # else until _run begins.
        prediction = predict_token_budget(contract.intent.value, self._llm.usage)
        self._emit(job, {"predicted_budget": {
            "intent": contract.intent.value,
            "predicted_tokens": prediction.predicted_tokens,
            "based_on_samples": prediction.based_on_samples,
            "confidence": prediction.confidence,
        }})
        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        thread.start()

    def cancel(self, job_id: str) -> bool:
        """User-initiated stop. Checked between chunks and between rounds — the model call already
        in flight finishes (or its connection closes as soon as the next check fires) rather than
        being killed instantly, but no further rounds or tool calls run."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return False
        job.cancelled = True
        return True

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            return job
        job = self._load_from_disk(job_id)
        if job is not None and job.status == "running":
            # On-disk checkpoint says "running" but the job isn't in the live registry — the
            # process that was running it is gone (crash/restart). Flag for the caller to resume.
            job.status = "interrupted"
        return job

    def _rotate_away_from_stalled_model(self, model: str) -> str | None:
        """Picks a different model to resume a stall-exhausted job with. A stall is NOT a rate
        limit — run_round's own ring/key failover in llm.py never sees it at all (is_rate_limit_error
        is False for a timeout), so left alone, EVERY resume (automatic auto-continue or a manual
        Continue click) kept retrying the identical already-dead connection for the job's entire
        remaining budget — confirmed against a real dead job that spent all 20 auto-continues stuck
        on tokenrouter/z-ai/glm-5.3-free. None if there's no tier/ring info or nothing else to try
        (caller keeps the current model in that case — better than an empty job.model)."""
        tier = self._llm.tier_of(model)
        if not tier:
            return None
        ring = getattr(self._llm, "failover_ring", lambda _t: [])(tier)
        candidates = ring or self._llm.models_for_tier(tier)
        return next((m for m in candidates if m != model), None)

    def continue_job(self, job_id: str) -> Job | None:
        """Explicit user action ("Continue" in the UI) for a job that errored out from one of the
        two specific mechanically-recoverable reasons — ran out of tool-calling rounds
        (error_reason == "max_rounds") or exhausted its stall-recovery retries on a flaky provider
        connection (error_reason == "stall_exhausted") — NOT a crash/restart reattach, that's
        resume()'s job. Grants a fresh budget for whichever ran out and re-runs the SAME job (same
        id, same messages/tools_called/receipts history) from where it left off, so nothing already
        done gets thrown away. Returns None if the job doesn't exist or isn't in that specific
        continuable state (any other error, or a job that's still actually running)."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            job = self._load_from_disk(job_id)
        if job is None or job.status != "error" or job.error_reason not in (
            "max_rounds", "stall_exhausted", "plan_blocked", "tasks_failed",
        ):
            return None
        rotated_model: str | None = None
        if job.error_reason in ("plan_blocked", "tasks_failed"):
            # Every remaining task is blocked behind a failure and the plan's revision budget is
            # spent. A human clicking Continue is new information — they have seen what failed and
            # want another go — so give the plan a genuine second chance rather than resuming
            # straight back into the same wall: unblock what was blocked, clear the counters that
            # closed those doors, and restore some revision budget for recovery tasks.
            #
            # Deliberately NOT auto-continued in _run: automatic retry into a plan that just
            # exhausted its own recovery would be an unbounded loop, and unbounded retry against a
            # permanently failing provider is precisely what the auto-continue ceiling exists to
            # prevent. This one needs a person.
            plan = ExecutionPlan.from_dict(job.plan)
            if plan is not None:
                for task in plan.tasks:
                    if task.status in (TaskStatus.BLOCKED, TaskStatus.FAILED):
                        task.status = TaskStatus.PENDING
                        task.failure_reason = ""
                        task.interventions = 0
                        task.attempts = 0
                        task.rounds_spent = 0
                        task.rounds_without_progress = 0
                        task.validation_state = ValidationState.UNVALIDATED
                plan.revisions = 0
                job.plan = plan.to_dict()
            job.round_budget += _MAX_ROUNDS
        elif job.error_reason == "max_rounds":
            job.round_budget += _MAX_ROUNDS
        else:
            job.stall_recoveries = 0
            # Retrying the exact model that just stalled out is very likely to just stall again -
            # rotate here, at the single point this job actually resumes, rather than requiring one
            # more full failed cycle before _loop's own stall-exhaustion path gets a chance to.
            rotated_model = self._rotate_away_from_stalled_model(job.model)
            if rotated_model:
                job.model = rotated_model
        job.status = "running"
        job.error_reason = None
        # A human just intervened manually - by definition this only happens once _run's own
        # automatic continuations (_MAX_AUTO_CONTINUES) were already exhausted. Give auto-continue a
        # fresh bounded budget of its own again rather than leaving it permanently disabled for the
        # rest of this job's life after the first manual click.
        job.auto_continues = 0
        # A stale True here (e.g. this exact job was cancelled at some earlier point, then still
        # reached max_rounds on the attempt that was already in flight when cancel fired) would
        # make _loop's very first round-loop check kill it again instantly and silently - status
        # "done", cancelled: true, no error - indistinguishable from the job just stopping dead.
        job.cancelled = False
        # job.events IS reset here (unlike a genuine mid-flight resume, where it's already empty
        # anyway) — a fresh SSE subscription always replays from index 0, and leaving the stale
        # terminal error event in the log would replay it immediately on reattach, flipping the UI
        # right back to "error" the instant Continue is clicked even though the job is genuinely
        # running again. The frontend already holds onto the prior thinking/content client-side
        # before calling continue, so nothing is visually lost - just not replayed twice.
        job.events = []
        if rotated_model:
            self._emit(job, {"model_switched": rotated_model})
        with self._lock:
            self._jobs[job_id] = job
        thread = threading.Thread(target=self._run, args=(job,), daemon=True, kwargs={"resuming": True})
        thread.start()
        return job

    def resume(self, job_id: str) -> Job | None:
        """Reattaches a job that isn't in the in-memory registry (server restarted while it was
        mid-flight) and continues its tool-calling loop from the last checkpointed round."""
        with self._lock:
            if job_id in self._jobs:
                return self._jobs[job_id]
        job = self._load_from_disk(job_id)
        if job is None:
            return None
        if job.status in ("done", "error"):
            # Already finished before the disconnect — nothing to resume, just replay what's stored.
            # Re-synthesize a terminal event so a stream subscriber that only has the checkpoint
            # (events log isn't persisted) still sees a clean ending.
            job.events = [{
                "done": job.status == "done",
                "usage": {
                    "prompt_tokens": job.prompt_tokens,
                    "completion_tokens": job.completion_tokens,
                    "context_window": 0,
                    "model": job.model,
                },
            }] if job.status == "done" else [{"error": "Job did not complete before the server restarted."}]
            with self._lock:
                self._jobs[job_id] = job
            return job
        job.status = "running"
        with self._lock:
            self._jobs[job_id] = job
        thread = threading.Thread(target=self._run, args=(job,), daemon=True, kwargs={"resuming": True})
        thread.start()
        return job

    def load_interrupted_ids(self) -> list[str]:
        """Jobs left mid-flight by an unclean shutdown — call once at startup for observability."""
        ids = []
        for path in JOBS_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("status") == "running":
                data["status"] = "interrupted"
                try:
                    path.write_text(json.dumps(data), encoding="utf-8")
                except OSError:
                    pass
                ids.append(data.get("id"))
        return ids

    # --- the loop itself ---------------------------------------------------------
    def _emit(self, job: Job, payload: dict) -> None:
        job.events.append(payload)

    def _run(self, job: Job, *, resuming: bool = False) -> None:
        while True:
            try:
                self._loop(job, resuming=resuming)
            except Exception as exc:  # noqa: BLE001 - surface to subscribers, never crash the thread pool
                job.status = "error"
                self._emit(job, {"error": f"{type(exc).__name__}: {exc}"})
                self._checkpoint(job)
                return
            # _loop returned normally (no exception) — auto-continue the mechanically-recoverable
            # cases (ran out of rounds, or the stall-recovery retry budget ran out on a flaky
            # provider — neither is a real failure), up to _MAX_AUTO_CONTINUES times. Originally
            # this only covered "max_rounds" — a live incident showed a job dying with
            # error_reason="stall_exhausted" instead (a SEPARATE, much stricter retry budget,
            # _MAX_STALL_RECOVERIES) went completely unrecognized here and sat there forever
            # despite auto_continues being nowhere near its cap. Both reasons get the same
            # treatment now. Reuses the exact same fields/semantics as the user-facing
            # continue_job() — this is just that same recovery firing automatically instead of
            # waiting for someone to click a button, which is the entire point of running a build
            # unattended overnight.
            recoverable_reason = job.error_reason if job.status == "error" else None
            if not (
                recoverable_reason in ("max_rounds", "stall_exhausted")
                and job.auto_continues < _MAX_AUTO_CONTINUES
            ):
                logger.warning(
                    "job %s: _run not auto-continuing (status=%r error_reason=%r "
                    "auto_continues=%s/%s round=%s round_budget=%s)",
                    job.id, job.status, job.error_reason, job.auto_continues,
                    _MAX_AUTO_CONTINUES, job.round, job.round_budget,
                )
                return
            job.auto_continues += 1
            job.status = "running"
            job.error_reason = None
            if recoverable_reason == "max_rounds":
                job.round_budget += _MAX_ROUNDS
                reason_text = "ran out of tool-calling rounds"
            else:
                job.stall_recoveries = 0
                reason_text = "the connection kept stalling"
                # Same rotation continue_job() does for a manual Continue click - retrying the exact
                # model that just stalled out is very likely to just stall again, so an automatic
                # auto-continue rotates too, rather than burning its whole budget on one dead model.
                next_model = self._rotate_away_from_stalled_model(job.model)
                if next_model:
                    job.model = next_model
                    self._emit(job, {"model_switched": next_model})
            self._emit(job, {"tool_call": {"name": "_auto_continue", "args": {
                "reason": f"{reason_text} — continuing automatically",
                "auto_continues_used": job.auto_continues, "auto_continues_remaining": _MAX_AUTO_CONTINUES - job.auto_continues,
                "new_round_budget": job.round_budget,
            }}})
            self._checkpoint(job)
            resuming = True

    def _loop(self, job: Job, *, resuming: bool) -> None:
        llm = self._llm
        # Key rotation happens several layers down, inside the streaming call, where nothing has a
        # job handle to emit from. Installing this for the duration of the loop is what lets a
        # switch between two keys of the SAME model reach the UI at all — the model id is identical
        # across that switch, so without it the interface shows no change while a different quota
        # bucket takes over, and "why did it stall at round 40" stays unanswerable afterwards.
        if hasattr(llm, "_on_key_switch"):
            llm._on_key_switch = lambda _m, label: self._emit(job, {"status": f"Switched to {label}"})
        model = job.model
        messages = job.messages
        message_rounds = job.message_rounds
        contract_dict = job.contract or {}
        active_tools = tools_for_groups(job.active_tool_groups)
        tools_called = job.tools_called
        receipts = job.receipts
        working_repo = job.working_repo

        # --- execution plan -------------------------------------------------------------------
        # Built once per job and then owned by Codexa for the rest of its life. Rebuilding it on a
        # resume would be the same mistake this replaces: handing a fresh model the whole problem
        # and asking it to work out where the last one had reached. from_dict returns None for a job
        # checkpointed before this existed, which is exactly the right trigger to build one.
        plan = ExecutionPlan.from_dict(job.plan)
        if plan is None:
            plan = build_plan(
                job.contract_source or _last_user_text(messages),
                _contract_from_dict(contract_dict),
                llm=llm, model=model, repository=working_repo,
            )
            job.plan = plan.to_dict()
            if plan.tasks:
                logger.info("job %s: planned %s tasks", job.id, len(plan.tasks))
                # Size the round budget to the plan. _MAX_ROUNDS (10) was chosen for the old
                # single-shot loop, where one round was expected to do everything; an eight-task
                # plan cannot fit in it, and observed runs spent seven rounds on task 1 alone. The
                # result was that every plan-driven job exhausted its budget before reaching the
                # task that writes the file, surfaced "Ran out of tool-calling rounds" to the user,
                # and then silently auto-continued — alarming, and pure churn. Four rounds per task
                # is a working allowance (act, check, correct, act again); the real ceilings on a
                # runaway job are unchanged: MAX_ROUNDS_PER_TASK bounds each task, the intervention
                # budget abandons one that stops advancing, and _MAX_AUTO_CONTINUES still bounds
                # the job overall.
                job.round_budget = max(job.round_budget, len(plan.tasks) * 4)
            self._checkpoint(job)
        # An empty plan is not a failure — a conversational or explain-shaped turn genuinely has no
        # tasks to track, and forcing one on it would put a build-shaped checklist in front of
        # someone who asked a question. `controller` stays None for those, and every plan-aware
        # branch below is guarded on it, leaving the original loop behaviour exactly intact.
        controller = (
            ExecutionController(job, plan, repository=working_repo, emit=lambda p: self._emit(job, p))
            if plan.tasks else None
        )
        if plan.tasks:
            # Emitted on EVERY entry to the loop, not only when the plan was first constructed.
            # The emit used to sit inside `if plan is None:`, so a resumed job, an auto-continue or
            # a Continue click never re-sent it — and `continue_job` clears `job.events`, so a
            # client replaying from index 0 saw no plan at all until the next task transition, which
            # on a stuck job may never arrive. That is the "task card does not show up" report.
            self._emit(job, {"plan": summarize_for_event(plan)})

        # Set by the reasoning-budget cut or by the execution controller, and consumed by the very
        # next round then cleared. Asking a model that is deep in planning to please call a tool does
        # not work — measured: after the cut and an explicit "your next message must call a tool",
        # the next round spent another 23,692 characters planning and still called nothing.
        # tool_choice removes the option: the response cannot be prose, it has to be a tool call.
        # drop_params handles providers that do not support it, so this degrades to the plain nudge
        # rather than erroring.
        #
        # `forced_tool` names the ONE call that would advance the active task (chosen by the
        # controller, which knows the task's outstanding artifact); `force_any_tool` is the weaker
        # fallback used when there is no plan to consult. The distinction is load-bearing:
        # tool_choice="required" alone was measured to be gameable — after a cut, the model called
        # screenshot against a URL serving nothing (ERR_CONNECTION_REFUSED) and list_directory on an
        # empty repository, satisfying the constraint with the two cheapest calls available, then
        # went straight back to planning. Forcing *a* tool buys a tool call; forcing *the* tool buys
        # the task.
        forced_tool: str | None = None
        force_any_tool = False
        # This round's reasoning volume, read by the controller after the round so a task's total
        # deliberation can be bounded across rounds and not merely within one.
        round_reasoning_chars = 0
        # Instrumentation. Replaced at the top of every round; marked from inside the stream so the
        # timings are taken as close to the provider as possible rather than after the loop has
        # already done its own work. See backend/agents/round_telemetry.py for why this exists.
        round_timer = telemetry.RoundTimer()
        round_record: telemetry.RoundRecord | None = None
        round_written = False
        # Round on which each task became active, so a round's context can be split into "produced
        # while working on this task" and "inherited from earlier tasks". The controller tracks tool
        # and exit-code offsets per task for validation; this is the same idea for the transcript.
        task_start_rounds: dict[str, int] = {}

        def stream_round(*, with_tools: bool) -> Iterator[tuple[str, Any]]:
            nonlocal forced_tool, force_any_tool, round_reasoning_chars
            choice: Any = "auto"
            available = {s["function"]["name"] for s in active_tools}
            if forced_tool and forced_tool in available:
                choice = {"type": "function", "function": {"name": forced_tool}}
            elif forced_tool or force_any_tool:
                # No specific target survived (the named tool isn't exposed to this job, or nothing
                # was named): fall back to the contract's own outstanding requirement, then to
                # "call something" as a last resort.
                outstanding = [t for t in contract_dict.get("required_tools", []) if t not in set(tools_called)]
                target = next((t for t in outstanding if t in available), None)
                choice = (
                    {"type": "function", "function": {"name": target}} if target else "required"
                )
            # One round only — never leave the model permanently unable to deliver a final answer,
            # which by definition is not a tool call.
            forced_tool, force_any_tool = None, False
            kwargs = {"tools": active_tools, "tool_choice": choice} if with_tools else {}
            chunks = []
            # Deliberation characters, across BOTH channels. Counting only reasoning_content left a
            # hole a real job fell into for twenty minutes: chunks kept arriving so the stall
            # watchdog reset every time, while the model deliberated in the content channel where
            # the counter could not see it. Tool-call arguments are never counted here — those
            # arrive via delta.tool_calls and are the product, not the deliberation.
            spent = 0
            started_at = time.time()
            # Once a direction is committed the thinking has been done and recorded, so a round
            # whose job is to emit one call gets a much shorter leash than one still deciding.
            authoring = bool(active_task is not None and active_task.expected_artifacts)
            if not job.commitment:
                limit, phase = _PLANNING_CHARS, "planning"
            elif authoring:
                # Producing the artifact IS the deliberation for this task.
                limit, phase = _AUTHORING_CHARS, "authoring"
            else:
                limit, phase = _EXECUTION_CHARS, "execution"
            _mark_wait(job, "WAITING_LLM_STREAM")
            for chunk in _stream_with_watchdog(llm.stream(model, messages, timeout=240, **kwargs)):
                if job.cancelled:
                    break
                # The backstop, checked on every chunk: independent of channel, of token counting,
                # and of whatever a provider chooses to call its output. It is the only guard here
                # that cannot be evaded by emitting through an unexpected field, which is exactly
                # how the last deadlock survived two other guards.
                elapsed = time.time() - started_at
                if elapsed > _MAX_ROUND_SECONDS:
                    raise _GenerationBudgetExceeded(spent, elapsed, "wall-clock")
                chunks.append(chunk)
                round_timer.mark_first_token()
                # Refreshed on every chunk (not logged every time — that would be one debug line per
                # token) so idle_seconds stays accurate through a long streaming round instead of
                # only updating at the round boundary.
                job.last_activity_ts = time.time()
                delta = chunk.choices[0].delta
                thinking = getattr(delta, "reasoning_content", None)
                if thinking:
                    spent += len(thinking)
                    round_reasoning_chars = spent
                    if spent > limit:
                        raise _GenerationBudgetExceeded(spent, elapsed, phase)
                    yield ("thinking", thinking)
                if delta.content:
                    spent += len(delta.content)
                    round_reasoning_chars = spent
                    if spent > limit:
                        raise _GenerationBudgetExceeded(spent, elapsed, phase)
                    yield ("delta", delta.content)
            round_timer.mark_generation_done()
            _mark_wait(job, "idle")
            final = litellm.stream_chunk_builder(chunks, messages=messages)
            usage = (
                llm.record_usage("chat", model, final, task_intent=contract_dict.get("intent"))
                if final else {"prompt_tokens": 0, "completion_tokens": 0}
            )
            yield ("final", (final.choices[0].message if final else None, usage))

        def finish_round_telemetry(
            outcome: str,
            *,
            tools: Sequence[str] = (),
            progress: Any = None,
            usage: dict | None = None,
            visible: str = "",
        ) -> None:
            """Close out this round's record and append it.

            Called from every exit a round has — normal, cut, stall, cancellation — because the cut
            and stall paths are precisely the rounds worth measuring, and a record written only on
            the happy path would leave exactly the pathology invisible. Idempotent per round:
            whichever exit fires first writes, later calls are no-ops.
            """
            nonlocal round_written
            if round_record is None or round_written or not telemetry.enabled():
                return
            round_written = True
            round_record.outcome = outcome
            round_record.reasoning_chars = round_reasoning_chars
            round_record.visible_chars = len(visible)
            round_record.tool_calls = list(tools)
            if usage:
                round_record.prompt_tokens = int(usage.get("prompt_tokens", 0))
                round_record.completion_tokens = int(usage.get("completion_tokens", 0))
            if progress is not None:
                round_record.made_progress = bool(getattr(progress, "made_progress", False))
                round_record.files_changed = (
                    len(progress.created) + len(progress.modified) + len(progress.deleted)
                )
            round_record.first_token_ms = round_timer.first_token_ms
            round_record.generation_ms = round_timer.generation_ms
            round_record.total_round_ms = round_timer.total_ms
            round_record.model = model
            telemetry.write(round_record)

        def run_round(*, with_tools: bool) -> Iterator[tuple[str, Any]]:
            nonlocal model
            tried = {model}
            # 8, not 5: a tier with a failover ring (see llm.failover_ring) can round-robin back to
            # its own start once exhausted instead of giving up — heavy's ring is 3 models, so this
            # gives room for a full lap plus a bit, rather than dying right as it wraps around.
            for attempt in range(1, 9):
                emitted = False
                try:
                    for kind, payload in stream_round(with_tools=with_tools):
                        if kind != "final":
                            emitted = True
                        yield (kind, payload)
                    return
                except Exception as exc:
                    if emitted:
                        raise
                    # is_rate_limit_error (not a bare isinstance(exc, litellm.RateLimitError))
                    # because a real rate limit can arrive wrapped in litellm.MidStreamFallbackError
                    # (a ServiceUnavailableError subclass) - the narrower check silently missed it,
                    # which is why a real Gemini 429 fell all the way through to a hard job failure
                    # instead of even reaching this last-resort model switch.
                    if is_rate_limit_error(exc):
                        tier = llm.tier_of(model)
                        # getattr, not a direct llm.failover_ring(tier) call: several test doubles
                        # implement the older tier_of/models_for_tier interface without this newer
                        # method — treat "doesn't have one" the same as "no ring for this tier"
                        # rather than crashing the whole round-switch path on an AttributeError.
                        ring = getattr(llm, "failover_ring", lambda _t: [])(tier) if tier else []
                        if ring:
                            next_model = next((m for m in ring if m not in tried), None)
                            if next_model is None and attempt < 8:
                                # Whole ring exhausted (e.g. 3.8 -> 3.7 -> GLM all rate-limited) -
                                # round-robin back to the top instead of dropping to the tier's
                                # weaker last-resort models or giving up outright. By the time a lap
                                # completes, real wall-clock time has passed (each attempt is a real
                                # network round-trip) and an earlier model's rate-limit window may
                                # have rolled.
                                tried = set()
                                next_model = ring[0]
                                # Sticky key rotation is right WITHIN a lap but wrong across one: a
                                # model whose keys were all spent early in the lap would otherwise
                                # be retried only on its last key forever, leaving its other
                                # separately-metered keys untouched for the rest of the job. This
                                # matters most for an ultra_heavy (GLM-only) ring, where the whole
                                # point of the tier is that its several keys ARE the rotation.
                                reset_keys = getattr(llm, "reset_keys", None)
                                if callable(reset_keys):
                                    reset_keys(ring)
                        else:
                            # No ring for this tier - old linear-until-exhausted behavior, unchanged.
                            next_model = next(
                                (m for m in llm.models_for_tier(tier) if m not in tried), None,
                            ) if tier else None
                        if next_model:
                            model = next_model
                            tried.add(model)
                            yield ("model_switched", model)
                            # Alongside the raw id (which drives the model picker), a human label
                            # naming the exact key — "Gemini 3.7 Flash #2". With several keys per
                            # model the id alone cannot say which of the independent buckets is now
                            # live, which is the only detail that explains a sudden change in pace.
                            describe = getattr(llm, "describe_active", None)
                            if callable(describe):
                                yield ("status", f"Switched to {describe(model)}")
                            continue
                    if attempt >= 2:
                        raise

        # job.round is checkpointed as the last *completed* round, so resuming continues at the
        # next one — redoing it would re-query the model with that round's messages already in
        # history (harmless but wastes a round of the _MAX_ROUNDS budget for nothing new).
        start_round = job.round + 1 if resuming else 0
        rounds = (
            itertools.count(start_round) if _UNLIMITED_ROUNDS
            else range(start_round, job.round_budget)
        )
        # Whether any earlier round in this job already streamed visible text. Every round's
        # narration lands in the SAME assistant message on the client ("I'll inspect the repo." then,
        # three tool calls later, "Now I'll write the file."), and nothing separated them, so the UI
        # rendered "the repo.Now I'll write the file" — dozens of rounds fused into one unreadable
        # paragraph. The loop is the only place that knows exactly where a round begins, so the
        # separator is emitted here rather than guessed at on the client.
        visible_text_emitted = resuming and any(
            m.get("role") == "assistant" and isinstance(m.get("content"), str) and m["content"].strip()
            for m in messages
        )
        for _round in rounds:
            if job.cancelled:
                job.status = "done"
                self._emit(job, {"done": True, "cancelled": True, "usage": {
                    "prompt_tokens": job.prompt_tokens, "completion_tokens": job.completion_tokens,
                    "context_window": llm.context_window(model), "model": model,
                }})
                self._checkpoint(job)
                return
            job.round = _round
            # Reset per ROUND. It was initialised once at _loop scope, so a round that emitted no
            # reasoning at all (a pure write_file round) left the previous round's value in place
            # and charged it to the task a second time. Three such rounds crossed the per-task
            # reasoning ceiling and triggered a spurious intervention on a task that was writing
            # files perfectly.
            round_reasoning_chars = 0
            _compact_stale_payloads(
                messages, message_rounds, _round, graph=self._graph, repository=working_repo,
                task_start_rounds=task_start_rounds,
            )

            # --- select the task this round is for --------------------------------------------
            # Exactly one task is active at a time, and the model is told about that one rather than
            # about the whole problem. This is the structural half of the fix for indefinite
            # planning: bounding reasoning per round made an endless round recoverable, but the
            # model kept re-deriving the entire plan because the entire plan is what it was being
            # asked about, every round. Narrow the question and the deliberation narrows with it.
            active_task = None
            snapshot_before = None
            if controller is not None:
                active_task = controller.current_task()
                if active_task is None:
                    blocker = controller.blocking_reason()
                    if blocker is not None:
                        # Work remains but nothing can be started — every path forward is blocked
                        # behind a failure. Surfacing this is the point: the alternative is a loop
                        # that spins looking for a task, or worse, one that reports success.
                        job.status = "error"
                        job.error_reason = "plan_blocked"
                        self._emit(job, {"error": f"Execution stopped — {blocker}", "continuable": True})
                        self._checkpoint(job)
                        return
                    # The plan ran to the end. If it gave up on part of the way there, say so rather
                    # than letting the run report clean success: is_complete() is satisfied by
                    # "every task terminal and at least one succeeded", which is the right rule for
                    # advancing a plan and the wrong one for announcing a result. A UI build whose
                    # screenshot task failed three times has produced a page nobody ever looked at,
                    # and reporting that as done is the platform committing the model's own
                    # silent-success failure on its behalf. Continuable: continue_job resets exactly
                    # these tasks and runs them again.
                    failed = controller.failed_tasks()
                    if failed:
                        job.status = "error"
                        job.error_reason = "tasks_failed"
                        self._emit(job, {"error": (
                            f"Finished with {len(failed)} incomplete task(s): " + "; ".join(
                                f"{t.objective} — {t.failure_reason or t.validation_detail}"
                                for t in failed
                            )
                        ), "continuable": True})
                        self._checkpoint(job)
                        return
                else:
                    if controller.begin_task(active_task):
                        task_start_rounds.setdefault(active_task.id, _round)
                        self._emit(job, {"status": f"Starting: {active_task.objective}"})
                    controller.apply_task_context(messages, message_rounds, active_task, _round)
                    # Taken before the round so the comparison afterwards measures exactly this
                    # round's effect on the repository, and nothing else.
                    snapshot_before = controller.snapshot_repo()
                    reason = controller.intervention_reason(active_task)
                    if reason is not None:
                        forced_tool = controller.intervene(
                            active_task, reason, messages, message_rounds, _round,
                            {s["function"]["name"] for s in active_tools},
                        )
                        force_any_tool = forced_tool is None and bool(active_tools)
            # A round with no reasoning_content chunks (most models don't emit them) left the UI
            # showing literally nothing between "the last tool result" and "the next thing that
            # happens" - could be several real seconds on a slow provider. This gives the frontend
            # something honest to show for that gap instead of a dead silence that looks identical
            # to "hung". Superseded immediately by real thinking/delta/tool_call events once any
            # arrive - this is only ever the placeholder for the gap before those start.
            self._emit(job, {"status": "Understanding the task and planning next steps" if _round == 0 else "Working on the next step"})

            # --- instrument this round ---------------------------------------------------------
            # Taken here, after the task context and any intervention directive have been applied,
            # because `messages` is now byte-for-byte what the provider is about to receive. Taken
            # before generation starts so the timer's zero is the moment the request leaves.
            round_timer = telemetry.RoundTimer()
            round_written = False
            round_record = None
            if telemetry.enabled():
                round_record = telemetry.new_record(job_id=job.id, round_no=_round, model=model)
                if active_task is not None:
                    round_record.task_id = active_task.id
                    round_record.task_objective = active_task.objective
                    round_record.task_index = next(
                        (i for i, t in enumerate(plan.tasks) if t.id == active_task.id), None
                    )
                    round_record.task_state = active_task.status.value
                round_record.context = telemetry.split_context(
                    messages,
                    message_rounds,
                    task_started_round=(
                        task_start_rounds.get(active_task.id) if active_task is not None else None
                    ),
                ).as_dict()

            msg = None
            usage = {"prompt_tokens": 0, "completion_tokens": 0}
            partial_content = ""
            try:
                for kind, payload in run_round(with_tools=bool(active_tools)):
                    if kind == "final":
                        msg, usage = payload
                    elif kind == "model_switched":
                        self._emit(job, {kind: payload})
                    else:
                        if kind == "delta":
                            if payload and not partial_content and visible_text_emitted:
                                # First visible text of a new round, after an earlier round already
                                # wrote some: start a new paragraph instead of fusing onto the last
                                # word of the previous round. Emitted as its own delta and kept OUT
                                # of partial_content, which is the model's own words and goes back
                                # into the transcript if this round stalls.
                                self._emit(job, {"delta": "\n\n"})
                            partial_content += payload
                            if payload:
                                visible_text_emitted = True
                        self._emit(job, {kind: payload})
            except _GenerationBudgetExceeded as exc:
                # A cut still ends the wait — without this, wait_state is left reading
                # "WAITING_LLM_STREAM" for the rest of the job's life (this is the only path out of
                # stream_round that doesn't reach the normal _mark_wait(job, "idle") after the loop).
                _mark_wait(job, "idle")
                # A cut is not one failure, it is four, and they need different answers. Recovering
                # them identically is what produced the deadlock: rounds 32 and 33 were cut at
                # 40,053 and 40,002 characters — the same deliberation regenerated and thrown away
                # twice — because "retry the round" was the only response available.
                #
                # The distinction that matters is whether anything was DECIDED. Before a commitment
                # exists, the useful recovery is to make deciding itself the next action: forcing an
                # expensive write_file on a model that could not reach the end of its own planning
                # asks it to do the hard thing under a shorter leash. commit_direction is cheap
                # enough to reach inside any budget, and once it lands the decision is durable and
                # the next round is a genuinely different round.
                job.consecutive_cuts += 1
                committed = bool(job.commitment)
                available = {s["function"]["name"] for s in active_tools}
                cause = (
                    "wall_clock" if exc.reason == "wall-clock"
                    else ("cap_after_commit" if committed else "cap_before_commit")
                )
                logger.warning(
                    "job %s: round %s cut (%s) at %s chars / %.0fs — streak %s, committed=%s",
                    job.id, _round, cause, exc.chars, exc.seconds, job.consecutive_cuts, committed,
                )
                self._emit(job, {"tool_call": {"name": "_round_cut", "args": {
                    "cause": cause, "chars": exc.chars, "seconds": round(exc.seconds),
                    "consecutive": job.consecutive_cuts, "committed": committed,
                }}})

                if controller is not None and active_task is not None:
                    active_task.reasoning_chars += round_reasoning_chars

                # Whether THIS task has already committed its own structure plan. Checked against
                # structure_task_id (stamped when commit_direction lands with a `structure` field)
                # rather than merely "job.commitment exists" — that would be true forever after the
                # very first project-direction commit, and every later authoring task would look
                # "already planned" when none of them had been.
                task_structure_id = (
                    (job.commitment or {}).get("design", {}).get("structure_task_id")
                )
                needs_structure = (
                    committed and controller is not None and active_task is not None
                    and bool(active_task.expected_artifacts)
                    and task_structure_id != active_task.id
                    and "commit_direction" in available
                )

                if not committed and "commit_direction" in available:
                    # Make the decision the action. This is the whole fix: the model stops being
                    # asked to finish a large implementation inside a budget it keeps overrunning,
                    # and is asked instead for the one cheap call that turns its thinking into state.
                    forced_tool = "commit_direction"
                    self._emit(job, {"status": "Pausing planning — recording the decision first"})
                    guidance = _COMMIT_FIRST_TEXT
                elif needs_structure:
                    # Same mechanism, one level down: this task is about to author an artifact and
                    # has no plan for it yet. Force the cheap plan before the expensive write,
                    # rather than forcing the write directly onto a model still working it out.
                    forced_tool = "commit_direction"
                    self._emit(job, {"status": "Pausing — planning this artifact's structure first"})
                    guidance = _STRUCTURE_FIRST_TEXT
                else:
                    # Committed already, structure already planned (or not an authoring task), or
                    # no commitment tool available: drive the outstanding action with the shortest
                    # possible horizon.
                    if controller is not None and active_task is not None:
                        forced_tool = controller.forced_tool_for(active_task, available)
                    force_any_tool = forced_tool is None and bool(active_tools)
                    self._emit(job, {"status": "Planning is done — performing the outstanding action"})
                    guidance = _execution_directive(job.commitment, forced_tool)

                finish_round_telemetry("cut", visible=partial_content)
                _replace_directive(messages, message_rounds, guidance, _round)
                self._checkpoint(job)
                continue
            except Exception:
                # Same reasoning as the _GenerationBudgetExceeded branch above: this is the other
                # non-normal exit from stream_round (a stall/timeout/transport error), and it must
                # end the wait too or wait_state sticks on "WAITING_LLM_STREAM" through the whole
                # stall-recovery detour below.
                _mark_wait(job, "idle")
                # Used to only take this recovery path `if saw_any_chunk:` — a round that failed
                # with ZERO chunks ever received (a real, observed case: _stream_with_watchdog's
                # TimeoutError firing on a connection that stayed completely silent) fell through to
                # an UNGUARDED retry-without-tools call instead, with no exception handling and no
                # bounded retry count at all. Any failure there — including the exact same kind of
                # silent hang happening again — killed the job outright with a bare "TimeoutError: "
                # message, bypassing every safety net below. Zero chunks is just as much a stall as
                # some-then-none; both now go through the SAME bounded, checkpointed recovery.
                if job.stall_recoveries >= _MAX_STALL_RECOVERIES:
                    # Every round this job attempted died mid-stream before completing — which
                    # means validate_completion below (the task-contract gate) never got a
                    # chance to run for any of them either. Re-raising here would surface only a
                    # raw "TimeoutError: ..." to the user, saying nothing about whether the
                    # actual task happened — the exact gap that let a prior incomplete CREATE
                    # task die silently while its required write_file call was never made. Say
                    # so explicitly instead of leaving that ambiguous.
                    contract = _contract_from_dict(contract_dict)
                    passed, _ = validate_completion(contract, tools_called)
                    detail = (
                        "The connection kept stalling and this attempt didn't finish."
                        if passed
                        else (
                            "The connection kept stalling before the required tool "
                            f"({', '.join(contract.required_tools)}) could be called — nothing "
                            "was actually created or changed. Send the request again."
                        )
                    )
                    # A stall is NOT a rate limit — is_rate_limit_error(exc) is False for it, so
                    # run_round's own ring/key failover (see llm.failover_ring) never even sees this
                    # failure. job.model is deliberately left as-is here (the model that just failed)
                    # rather than rotated at this exact point — the single place that happens is
                    # wherever this job actually RESUMES (_run's auto-continue, or a manual Continue
                    # click via continue_job), so it rotates exactly once per exhaustion instead of
                    # needing this same dead model to fail a second time first. See
                    # _rotate_away_from_stalled_model.
                    finish_round_telemetry("stalled", visible=partial_content)
                    job.status = "error"
                    job.error_reason = "stall_exhausted"
                    self._emit(job, {"error": detail, "continuable": True})
                    self._checkpoint(job)
                    return
                finish_round_telemetry("stalled", visible=partial_content)
                job.stall_recoveries += 1
                if partial_content:
                    messages.append({"role": "assistant", "content": partial_content})
                    message_rounds.append(_round)
                # A REAL, observed failure mode: a run of consecutive ZERO-chunk stalls (no partial
                # content each time) used to append a fresh, byte-identical nudge message every
                # single time — a live incident saw 6+ of these stack up back to back across
                # repeated auto-continues, on TWO separate jobs, both of which then never got a
                # single real response again for the rest of their run. A history bloating with
                # exact duplicate messages is exactly the kind of malformed-looking input that could
                # itself be contributing to a provider going silent, not just a symptom of it - so
                # collapse a run of them into one instead of letting it compound. Only applies when
                # the immediately preceding message is already this exact nudge (i.e. the PRIOR
                # round also stalled with zero content) - a nudge after real partial content, or the
                # first stall in a fresh streak, still gets appended normally.
                # "The previous message is already this nudge" — but read past the execution-state
                # block, which the controller re-appends at the top of every round and which
                # therefore always sits last. Checking messages[-1] literally silently disabled this
                # collapse the moment plans were introduced: the nudges stacked again, which is the
                # exact pattern that preceded two jobs going permanently silent.
                already_nudged = any(
                    m.get("role") == "user" and m.get("content") == _STALL_NUDGE_TEXT
                    for m in _recent_non_context_messages(messages, 1)
                )
                if not already_nudged:
                    messages.append({"role": "user", "content": _STALL_NUDGE_TEXT})
                    message_rounds.append(_round)
                self._checkpoint(job)
                continue

            job.prompt_tokens += usage["prompt_tokens"]
            job.completion_tokens += usage["completion_tokens"]
            if job.cancelled:
                # Cancellation was checked between chunks and at the top of the round, and nowhere
                # in between — so a cancel that landed mid-stream still fell through to the tool
                # executor below and ran every write_file, delete_file and run_command in the
                # partial message. Worse, if the break truncated before any tool call arrived, the
                # round looked like a completion claim and could mark the active task COMPLETED.
                # Stopping means stopping: nothing after this point should act on a cancelled round.
                finish_round_telemetry("cancelled", usage=usage, visible=partial_content)
                job.status = "done"
                self._emit(job, {"done": True, "cancelled": True, "usage": {
                    "prompt_tokens": job.prompt_tokens, "completion_tokens": job.completion_tokens,
                    "context_window": llm.context_window(model), "model": model,
                }})
                self._checkpoint(job)
                return

            tool_calls = getattr(msg, "tool_calls", None) or [] if msg else []
            if tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in tool_calls
                    ],
                })
                message_rounds.append(_round)
                repeat_streak_hit = False
                for tc in tool_calls:
                    name = tc.function.name
                    args = parse_args(tc.function.arguments)
                    tools_called.append(name)
                    self._emit(job, {"tool_call": {"name": name, "args": args}})
                    self._emit(job, {"status": _friendly_tool_status(name, args)})
                    # See _tool_call_signature: an independent stall detector, keyed on call
                    # identity rather than round completion. Deliberately checked BEFORE the
                    # already-performed skip below — a model re-issuing the same call it was just
                    # told was already done is exactly the "not learning from the observation"
                    # pattern this exists to catch, not a case to exempt from it.
                    signature = _tool_call_signature(name, args)
                    if signature == job.last_tool_signature:
                        job.same_tool_signature_streak += 1
                    else:
                        job.last_tool_signature = signature
                        job.same_tool_signature_streak = 1
                    if job.same_tool_signature_streak == _REPEAT_TOOL_CALL_THRESHOLD:
                        repeat_streak_hit = True
                    # A mutating call already recorded as SUCCEEDED (identical tool + args) is not
                    # re-executed — a real safety net against the model issuing the same write twice
                    # in one turn. Only successful calls are ever recorded (see below the execute_tool
                    # call), so a call that previously failed is never mistaken for "already done" —
                    # the model still sees the failure and gets a real chance to retry/fix it.
                    prior = already_performed(receipts, tool=name, args=args) if name in GRAPH_DIRTYING_TOOLS else None
                    if prior is not None:
                        result = f"(skipped — identical to a call already made this turn, action {prior.action_id})"
                    else:
                        tool_ctx: dict = {}
                        _mark_wait(job, f"WAITING_TOOL:{name}")
                        result = execute_tool(
                            name, args, working_repo, graph=self._graph, store=self._store,
                            context=tool_ctx, llm=llm, model=model,
                            prior_commitment=job.commitment,
                        )
                        _mark_wait(job, "idle")
                        if tool_ctx.get("new_repository"):
                            working_repo = tool_ctx["new_repository"]
                            job.working_repo = working_repo
                            if controller is not None:
                                # The controller captured the repository name at construction and
                                # kept it, so after a mid-job switch every snapshot, progress
                                # comparison and validator inspected the abandoned repository:
                                # perpetual "no progress" and failed tasks while real files were
                                # being written somewhere else.
                                controller.repository = working_repo
                            self._emit(job, {"repo_switched": working_repo})
                        if tool_ctx.get("commitment"):
                            # Promote it onto the job so it is checkpointed and survives the cut,
                            # the restart and the model rotation that would otherwise lose it.
                            job.commitment = tool_ctx["commitment"]
                            design = job.commitment.get("design")
                            if design and design.get("structure") and active_task is not None:
                                # Stamped here, not inside _commit_direction, because that function
                                # has no notion of "the current task" — only the loop knows which
                                # task this structure plan was written for. This is what lets the
                                # cut-handler tell "this task already has its plan" from "it does
                                # not yet" on the very next round.
                                design["structure_task_id"] = active_task.id
                            self._emit(job, {"status": "Direction committed"})
                        if "exit_code" in tool_ctx:
                            job.tool_exit_codes[tc.id] = tool_ctx["exit_code"]
                            # Ordered mirror of the same data. tool_exit_codes is keyed by
                            # tool_call_id, which is right for claim verification but cannot answer
                            # "what did THIS task's commands return" — that needs a list to slice by
                            # the task's start offset.
                            job.exit_code_log.append(tool_ctx["exit_code"])
                        if tool_ctx.get("tainted_findings"):
                            self._emit(job, {"tool_call": {"name": "_taint_detected", "args": {
                                "source": name, "reasons": tool_ctx["tainted_findings"],
                            }}})
                        # execute_tool's outer try/except (tools.py) turns any raised exception into
                        # exactly this text — never raises. Only record a receipt for a call that
                        # didn't hit that path, so a genuinely failed write is never later confused
                        # with "already performed" (see above).
                        if name in GRAPH_DIRTYING_TOOLS and not result.startswith(f"Tool '{name}' failed:"):
                            record_receipt(receipts, tool=name, args=args, result=result)
                    self._emit(job, {"tool_result": {"name": name, "result": result[:600]}})
                    messages.append({"role": "tool", "tool_call_id": tc.id, "name": name, "content": result})
                    message_rounds.append(_round)
                    screenshot_b64 = tool_ctx.get("screenshot_b64") if not prior else None
                    if screenshot_b64:
                        # A vision-capable model gets the actual rendered image, not just a file
                        # path — this is the real fix for "the model never looked at its own UI
                        # work": a text confirmation that a screenshot was SAVED is not the same as
                        # having SEEN it. Compacted by _compact_stale_payloads above once stale.
                        self._emit(job, {"tool_call": {"name": "_visual_review", "args": {"status": "showing screenshot"}}})
                        messages.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": (
                                    "Screenshot from the tool call above. Look at it carefully "
                                    "before continuing — check typography, color use, spacing, "
                                    "whether it looks generic or matches the design guidance you "
                                    "loaded, and whether every part of the brief actually shows up."
                                )},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}},
                            ],
                        })
                        message_rounds.append(_round)
                if repeat_streak_hit:
                    # Appended once the whole round's tool results are in — a role:"user" message
                    # can't be interleaved between an assistant tool_calls message and its matching
                    # role:"tool" results without breaking the format every provider expects.
                    messages.append({
                        "role": "user",
                        "content": (
                            f"[SYSTEM: the last {_REPEAT_TOOL_CALL_THRESHOLD} tool calls were "
                            f"identical ({job.last_tool_signature.split(':', 1)[0]}, same "
                            "arguments). Repeating it again will not produce a different result — "
                            "use what it already returned, or change your approach.]"
                        ),
                    })
                    message_rounds.append(_round)
                # Checkpoint once the whole round's tool calls have finished (not mid-round) — job.round
                # is only advanced at the top of the NEXT round, so resume (`start_round = job.round + 1`)
                # assumes the checkpointed state always has a round's tool_calls fully matched by their
                # tool results. Checkpointing mid-round would leave an assistant tool_calls message with
                # no matching result for the not-yet-executed calls; resume would then skip past them
                # entirely (start_round jumps beyond this round) AND hand the provider a message history
                # with unanswered tool_calls, which most providers reject outright.
                job.model = model
                # --- did this round actually move anything? -----------------------------------
                # Measured against the filesystem, not against how much the model generated. A
                # round that emitted 40,000 reasoning characters and changed no file is active and
                # unproductive, and until this comparison existed nothing in the loop could tell
                # that apart from real work.
                if controller is not None and active_task is not None and snapshot_before is not None:
                    signal = controller.record_round(
                        active_task,
                        before=snapshot_before,
                        tools_this_round=[tc.function.name for tc in tool_calls],
                        reasoning_chars=round_reasoning_chars,
                    )
                    if signal.made_progress:
                        self._emit(job, {"status": signal.describe()})
                    controller.sync()
                    # A task whose checks now pass is finished, whether or not the model has
                    # noticed. Waiting for it to fall silent to find out is what let one task run
                    # fifteen rounds past its own completion, manufacturing work to fill them.
                    controller.try_advance(active_task)
                    finish_round_telemetry(
                        "ok", tools=[tc.function.name for tc in tool_calls], progress=signal, usage=usage,
                        visible=(msg.content or "") if msg else "",
                    )
                finish_round_telemetry(
                    "ok", tools=[tc.function.name for tc in tool_calls], usage=usage,
                    visible=(msg.content or "") if msg else "",
                )
                self._checkpoint(job)
                continue

            # No tool calls in this round. With a plan active that is a CLAIM that the current task
            # is finished — never the finding that it is. Check it against the repository, and either
            # advance the plan or hand back exactly what is still missing. Only once every task is
            # genuinely complete does the round fall through to the job-level gates below.
            if controller is not None and active_task is not None and not active_task.is_terminal:
                # `active_task` was captured at the top of the round. An intervention during that
                # round can FAIL it and insert a recovery task, after which treating this round as a
                # completion claim marked the FAILED task COMPLETED — leaving the plan showing the
                # task both done and awaiting recovery.
                signal = controller.record_round(
                    active_task,
                    before=snapshot_before or controller.snapshot_repo(),
                    tools_this_round=[],
                    reasoning_chars=round_reasoning_chars,
                )
                finish_round_telemetry(
                    "ok", progress=signal, usage=usage, visible=(msg.content or "") if msg else "",
                )
                task_completed = controller.on_completion_claim(
                    active_task, messages, message_rounds, _round
                )
                job.model = model
                self._checkpoint(job)
                if not task_completed:
                    # Validation rejected the claim. The correction naming what is missing is
                    # already in the transcript — but a model that just declared itself finished has
                    # demonstrated it will not reach for the tool on its own, so prose alone is the
                    # weakest possible response. Force the outstanding call.
                    #
                    # This also fixes an ordering race: a no-tool round increments BOTH the
                    # validation attempts and the no-progress streak, and with both budgets at 3 the
                    # attempts always won — the task reached FAILED at round 2 while the streak was
                    # still 2, so the intervention that would have forced the tool never fired at
                    # all. Forcing here means the rejection itself drives the next round.
                    if not active_task.is_terminal:
                        forced_tool = controller.forced_tool_for(
                            active_task, {s["function"]["name"] for s in active_tools}
                        )
                        force_any_tool = forced_tool is None and bool(active_tools)
                    continue
                if controller.blocking_reason() is not None:
                    # A task finished but the plan has not. Keep going rather than treating this
                    # round's final-looking message as the end of the whole job.
                    continue

            # Last exit a round has: no tools, no plan (or the plan just finished). Idempotent, so
            # this is a no-op whenever one of the paths above already wrote.
            finish_round_telemetry("ok", usage=usage, visible=(msg.content or "") if msg else "")
            contract = _contract_from_dict(contract_dict)
            passed, correction = validate_completion(contract, tools_called)
            # No round-number cutoff here (there used to be one, `_round < 8`) — that let a job
            # with an UNSATISFIED contract (required_tools never called) get silently accepted as
            # "done" once it got close to the round cap, on the theory that forcing more retries
            # right before exhaustion was pointless. That reasoning no longer holds now that
            # exhaustion auto-continues itself (_MAX_AUTO_CONTINUES) instead of being a hard dead
            # end — so there's no longer a good reason to let an incomplete task falsely succeed
            # instead of genuinely running out of rounds (which recovers on its own) or genuinely
            # finishing. The model must not be the sole authority on whether a task is complete.
            if not passed:
                self._emit(job, {"tool_call": {"name": "_task_validation", "args": {"status": "incomplete"}}})
                messages.append({"role": "user", "content": correction})
                message_rounds.append(_round)
                job.model = model
                self._checkpoint(job)
                continue
            content = msg.content or "" if msg else ""
            # The graph was only ever built once, at repo load — an edit here (write_file etc.)
            # used to leave lookup_symbol/get_dependencies/find_references silently returning
            # pre-edit results forever after. Reindex once per turn (not per tool call, so a
            # multi-file scaffold doesn't pay for a full repo re-parse N times) if anything in this
            # turn actually touched files. Never fails the turn — a stale graph is recoverable
            # (next reindex or /repository/reload fixes it), losing the user's actual answer isn't.
            if any(t in GRAPH_DIRTYING_TOOLS for t in tools_called):
                try:
                    self._emit(job, {"tool_call": {"name": "_graph_reindex", "args": {"repository": working_repo}}})
                    reindex_repository(working_repo, store=self._store, graph=self._graph)
                    self._emit(job, {"tool_result": {"name": "_graph_reindex", "result": "Graph reindexed."}})
                except Exception as exc:  # noqa: BLE001 - never fail the turn over a stale graph
                    logger.warning("post-turn graph reindex failed for %s: %s", working_repo, exc)
                    self._emit(job, {"tool_result": {"name": "_graph_reindex", "result": f"Reindex failed: {exc}"}})

            # Second, complementary gate on top of validate_completion above: that only checks a
            # *required tool* was called, not that what the model just told the user is actually
            # true (e.g. claiming a function was created that doesn't exist, or that tests passed
            # after a run that failed). Runs after the reindex above so FILE_EXISTS/SYMBOL_EXISTS
            # claims are checked against the post-edit graph, not a stale pre-edit one.
            try:
                claims = extract_claims(content, llm)
                failed_claims = verify_claims(
                    claims, graph=self._graph, messages=messages,
                    tool_exit_codes=job.tool_exit_codes, repository=working_repo,
                ) if claims else []
            except Exception as exc:  # noqa: BLE001 - verification failure must never block the answer
                logger.warning("claim verification failed for job %s: %s", job.id, exc)
                failed_claims = []
            if failed_claims:  # same reasoning as validate_completion above - no round cutoff
                self._emit(job, {"tool_call": {"name": "_claim_verification", "args": {
                    "status": "failed", "claims": [c.target for c, _ in failed_claims],
                }}})
                messages.append({"role": "user", "content": build_correction_message(failed_claims)})
                message_rounds.append(_round)
                job.model = model
                self._checkpoint(job)
                continue

            job.status = "done"
            job.model = model
            self._emit(job, {"done": True, "usage": {
                "prompt_tokens": job.prompt_tokens,
                "completion_tokens": job.completion_tokens,
                "context_window": llm.context_window(model),
                "model": model,
            }})
            self._checkpoint(job)
            return

        job.status = "error"
        job.error_reason = "max_rounds"
        # Only tell the USER about this when it is actually their problem. _run auto-continues this
        # exact reason up to _MAX_AUTO_CONTINUES times, in the same thread, usually within
        # microseconds — so emitting an error here surfaced a red "Ran out of tool-calling rounds"
        # card with Continue/Retry buttons in front of a job that was healthy, mid-task, and about
        # to carry on by itself. Observed on a real run sitting at round 9 of 20 with two files
        # already written. The state transition still happens (that is what _run reads); only the
        # user-facing event is withheld until the automatic recovery has genuinely been exhausted
        # and a human really does have to decide something.
        if job.auto_continues >= _MAX_AUTO_CONTINUES:
            self._emit(job, {
                "error": "Ran out of tool-calling rounds without a final response.",
                "continuable": True,
            })
        else:
            self._emit(job, {"status": "Extending the round budget — still working"})
        self._checkpoint(job)
