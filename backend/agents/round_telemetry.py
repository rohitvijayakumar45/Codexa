"""Per-round accounting of where a job's context actually goes.

Every guard in the execution loop reacts to how much the model GENERATES. Nothing until now
measured what it was given, so every explanation for the observed pathology — tens of thousands of
deliberation characters before a single tool call — was a hypothesis about context composition that
could not be checked. Two mutually exclusive hypotheses were live at the same time:

  * the transcript accumulates across tasks, so a late task re-reads everything eight tasks of work
    produced and keeps mining it for decisions; or
  * the design brief and the objective alone open a search space that large, and history is
    irrelevant because the worst observed round was task ONE, whose transcript is nearly empty.

Those imply completely different fixes, and the difference between them is one measurement. This
module is that measurement: it splits the exact message list handed to the provider into labelled
buckets, counts each in tokens, and writes one JSON line per round.

It deliberately records generation and progress alongside the split, because the only interesting
quantity is the RATIO — context composition next to what the model then did with it. A round handed
180k tokens that emitted three tool calls and a round handed 8k that emitted 40k of reasoning and
nothing else are the two ends of the question.

Writing is best-effort and never raises into the loop: telemetry that can fail a job is worse than
no telemetry.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from backend.memory.store import DATA_DIR

logger = logging.getLogger(__name__)

# The structural markers the loop uses to find its own inserted blocks. Held by value rather than
# imported from their modules to keep this file free of import cycles (controller imports plan,
# jobs imports both, and jobs imports this).
_TASK_CONTEXT_MARK = "[EXECUTION STATE"
_DIRECTIVE_MARKS = ("[SYSTEM: that round was stopped", "[SYSTEM: planning for this task")
# Where the system message stops being the caller's prompt and starts being ours. Ordered: the task
# prompt is appended first, the design brief after it.
_TASK_PROMPT_MARK = "TASK MODE:"
_DESIGN_MARK = "DESIGN INTENT"

_ENABLED = os.getenv("CODEXA_ROUND_TELEMETRY", "1").strip().lower() not in ("0", "off", "false")


def enabled() -> bool:
    return _ENABLED


# --- token counting ---------------------------------------------------------------------------
# The transcript's early messages are byte-identical on every round of a job, and a long job runs
# dozens of rounds — counting them from scratch each time would make the instrument a meaningful
# share of the cost of the thing it measures. Cache on content identity.
_cache: dict[tuple[int, int], int] = {}
_MAX_CACHE = 4096


def count_tokens(text: str) -> int:
    """Token count for a string, cached, with a character-based fallback.

    Exactness is not the point — the comparison between buckets is. A fallback that is uniformly
    wrong by the same factor across every bucket still answers the question this file exists to
    answer, so an unavailable tokenizer degrades the numbers rather than the conclusion.
    """
    if not text:
        return 0
    key = (len(text), hash(text))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    try:
        import litellm

        n = int(litellm.token_counter(model="gpt-4", text=text))
    except Exception:  # noqa: BLE001 - any tokenizer failure falls back, never propagates
        n = max(1, len(text) // 4)
    if len(_cache) < _MAX_CACHE:
        _cache[key] = n
    return n


def _text_of(content: Any) -> str:
    """Flatten a message's content to text, handling the list-of-blocks shape the frontend sends."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


# --- the split --------------------------------------------------------------------------------

@dataclass
class ContextSplit:
    """Tokens by origin for one request's message list.

    The buckets are chosen so each maps to a specific thing that could be cut, and so that no token
    is counted twice: together they partition the request.
    """

    system_base: int = 0            # the caller's own system prompt
    task_prompt: int = 0            # build_task_prompt's TASK MODE block
    design_brief: int = 0           # DesignIntent.brief()
    task_context: int = 0           # the controller's per-round EXECUTION STATE block
    directive: int = 0              # a live recovery directive, if one is in play
    user: int = 0                   # real user turns, including the original request
    assistant_text: int = 0         # visible assistant prose carried forward
    assistant_tool_args: int = 0    # serialized tool_call arguments (write_file bodies live here)
    tool_results: int = 0           # tool return payloads
    other: int = 0

    # The same messages again, split by whether they predate the current task. This is the number
    # that decides between the two hypotheses.
    prior_task_total: int = 0
    current_task_total: int = 0

    messages: int = 0
    total: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def split_context(
    messages: Sequence[dict],
    message_rounds: Sequence[int] | None = None,
    *,
    task_started_round: int | None = None,
) -> ContextSplit:
    """Classify and count every message about to be sent.

    `task_started_round` is the round on which the currently active task began; messages tagged with
    an earlier round are attributed to prior tasks. When it is None (no plan, or the first task)
    everything counts as current.
    """
    split = ContextSplit(messages=len(messages))
    rounds: Sequence[int] = message_rounds or []

    for i, message in enumerate(messages):
        role = message.get("role")
        text = _text_of(message.get("content"))
        n = count_tokens(text)
        bucket = "other"

        if role == "system":
            # One system message holds up to three things appended by different layers. Split it at
            # the markers rather than attributing the whole block to whoever wrote first — the
            # design brief's size is itself under suspicion, and it is invisible if folded into a
            # single "system" number.
            design_at = text.find(_DESIGN_MARK)
            if design_at >= 0:
                split.design_brief += count_tokens(text[design_at:])
                text = text[:design_at]
            task_at = text.find(_TASK_PROMPT_MARK)
            if task_at >= 0:
                split.task_prompt += count_tokens(text[task_at:])
                text = text[:task_at]
            split.system_base += count_tokens(text)
            bucket = "system"
            n = 0  # attributed above, in pieces
        elif role == "tool":
            split.tool_results += n
            bucket = "tool"
        elif role == "assistant":
            split.assistant_text += n
            for call in message.get("tool_calls") or []:
                fn = call.get("function") or {}
                args = fn.get("arguments") or ""
                extra = count_tokens(args if isinstance(args, str) else json.dumps(args))
                split.assistant_tool_args += extra
                n += extra
            bucket = "assistant"
        elif role == "user":
            if text.startswith(_TASK_CONTEXT_MARK):
                split.task_context += n
                bucket = "task_context"
            elif text.startswith(_DIRECTIVE_MARKS):
                split.directive += n
                bucket = "directive"
            else:
                split.user += n
                bucket = "user"
        else:
            split.other += n

        if bucket != "system":
            split.total += n

        # Attribute to prior vs current task. The system message and the live per-round blocks
        # belong to no task in particular and are excluded from both — they are not history.
        if bucket in ("assistant", "tool", "user") and task_started_round is not None:
            at = rounds[i] if i < len(rounds) else None
            if at is not None and 0 <= at < task_started_round:
                split.prior_task_total += n
            else:
                split.current_task_total += n

    split.total += split.system_base + split.task_prompt + split.design_brief
    return split


# --- one round --------------------------------------------------------------------------------

@dataclass
class RoundRecord:
    at: str
    job_id: str
    round: int
    model: str
    task_id: str | None = None
    task_objective: str | None = None
    task_index: int | None = None

    context: dict = field(default_factory=dict)

    # What the model then did with it. reasoning_chars counts BOTH channels, matching the budget
    # guard: providers differ on which channel deliberation arrives in, and an earlier version of
    # that guard watched only one and missed a twenty-minute deadlock in the other.
    reasoning_chars: int = 0
    visible_chars: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    first_token_ms: int | None = None
    generation_ms: int | None = None
    total_round_ms: int | None = None

    tool_calls: list[str] = field(default_factory=list)
    made_progress: bool | None = None
    files_changed: int | None = None
    task_state: str | None = None
    outcome: str = "ok"     # ok | cut | stalled | cancelled | error

    def as_dict(self) -> dict:
        return asdict(self)


class RoundTimer:
    """Wall-clock marks for one round. Cheap enough to run unconditionally."""

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.first_token: float | None = None
        self.generation_done: float | None = None

    def mark_first_token(self) -> None:
        if self.first_token is None:
            self.first_token = time.monotonic()

    def mark_generation_done(self) -> None:
        self.generation_done = time.monotonic()

    def _ms(self, at: float | None) -> int | None:
        return None if at is None else int((at - self.started) * 1000)

    @property
    def first_token_ms(self) -> int | None:
        return self._ms(self.first_token)

    @property
    def generation_ms(self) -> int | None:
        return self._ms(self.generation_done)

    @property
    def total_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)


def _path() -> Path:
    override = os.getenv("CODEXA_TELEMETRY_PATH", "").strip()
    return Path(override) if override else DATA_DIR / "round_telemetry.jsonl"


def new_record(*, job_id: str, round_no: int, model: str) -> RoundRecord:
    return RoundRecord(
        at=datetime.now(timezone.utc).isoformat(), job_id=job_id, round=round_no, model=model
    )


def write(record: RoundRecord) -> None:
    """Append one round. Never raises — a failed write loses a data point, not a job."""
    if not _ENABLED:
        return
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.as_dict()) + "\n")
    except Exception as exc:  # noqa: BLE001 - instrumentation must not be able to fail a run
        logger.debug("round telemetry write failed: %s", exc)


# --- reading it back --------------------------------------------------------------------------

def load(path: Path | str | None = None, *, job_id: str | None = None) -> list[dict]:
    """Every recorded round, optionally for one job. Malformed lines are skipped, not fatal."""
    target = Path(path) if path else _path()
    if not target.exists():
        return []
    out: list[dict] = []
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if job_id is None or row.get("job_id") == job_id:
            out.append(row)
    return out


def summarize(rows: Iterable[dict]) -> dict:
    """Fold rounds into the comparison the measurement exists to make.

    Per task: how much context it was handed, how much of that came from earlier tasks, and how much
    deliberation it produced. If prior-task context climbs while reasoning stays flat, history is not
    the amplifier and the brief or the objective is.
    """
    by_task: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        key = row.get("task_id") or "-"
        if key not in by_task:
            order.append(key)
        entry = by_task.setdefault(key, {
            "task_id": key,
            "objective": row.get("task_objective"),
            "rounds": 0,
            "context_tokens": 0,
            "prior_task_tokens": 0,
            "design_brief_tokens": 0,
            "reasoning_chars": 0,
            "tool_calls": 0,
            "cuts": 0,
            "first_tool_ms": None,
        })
        ctx = row.get("context") or {}
        entry["rounds"] += 1
        entry["context_tokens"] += int(ctx.get("total", 0))
        entry["prior_task_tokens"] += int(ctx.get("prior_task_total", 0))
        entry["design_brief_tokens"] = max(
            entry["design_brief_tokens"], int(ctx.get("design_brief", 0))
        )
        entry["reasoning_chars"] += int(row.get("reasoning_chars", 0))
        calls = row.get("tool_calls") or []
        entry["tool_calls"] += len(calls)
        if calls and entry["first_tool_ms"] is None:
            entry["first_tool_ms"] = row.get("generation_ms")
        if row.get("outcome") == "cut":
            entry["cuts"] += 1
    return {"tasks": [by_task[k] for k in order]}
