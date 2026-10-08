"""Experiential memory: what an agent job actually did, written to memory when the job ends.

Before this module, episodic and procedural memory were written only by repository ingestion — a
static "Loaded into Codexa" event and the package.json scripts — so despite the four-type design no
agent ever learned anything from its own work. This records two things per finished job, both
derived from the job's real tool calls (never from the model's own summary of them):

  episodic    "Task <id>: <request>" — outcome, files modified, files read, verified commands.
              Anchored to the post-job bytes of the files it touched, so a later change to them
              flags the episode "(code changed since)" at retrieval instead of hiding it.
  procedural  "Verified command: <cmd>" — a shell command that exited 0 in this repository.
              Content is stable across jobs, so the same command verified again corroborates the
              existing record (trust rises) rather than duplicating it. Anchored to the repository
              manifests: a changed package.json/pyproject invalidates what "works here".

Exit codes come from the job's `tool_exit_codes` (captured from the real subprocess), not from the
command's text output — the same ground truth claim verification uses.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.memory.anchors import file_anchors
from backend.memory.store import MemoryStore

SOURCE = "job_experience"

_MAX_ANCHORED_FILES = 24
_MAX_LISTED_FILES = 12
_MAX_COMMAND_CHARS = 200

_WRITE_TOOLS = {"write_file", "edit_file"}
_READ_TOOLS = {"read_file"}
# Commands worth remembering as "how to build/test/run this repository". A bare `ls`/`cat`/`echo`
# exiting 0 teaches nothing about the project.
_PROCEDURAL_COMMAND = re.compile(
    r"^(?:cd\s+\S+\s*&&\s*)?(?:npm|pnpm|yarn|npx|bun|node|tsc|python3?|py|pytest|pip|uv|poetry|"
    r"make|cargo|go|mvn|gradle|\./gradlew|dotnet|docker|deno)\b",
)
_PATCH_PATH = re.compile(r"^\+\+\+\s+(?:b/)?(\S+)", re.MULTILINE)
_ARG_PATH = re.compile(r'"path"\s*:\s*"([^"]+)"')


@dataclass
class JobExperience:
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    read: list[str] = field(default_factory=list)
    commands: list[tuple[str, int | None]] = field(default_factory=list)  # (command, exit code)

    @property
    def verified_commands(self) -> list[str]:
        seen: list[str] = []
        for cmd, code in self.commands:
            if code == 0 and cmd not in seen:
                seen.append(cmd)
        return seen

    @property
    def failed_commands(self) -> list[str]:
        seen: list[str] = []
        for cmd, code in self.commands:
            if code not in (0, None) and cmd not in seen:
                seen.append(cmd)
        return seen


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, ValueError):
        # Compacted history (jobs.py _compact_stale_payloads) replaces huge arguments with a
        # stand-in that is no longer valid JSON; the path usually survives and is all we need.
        m = _ARG_PATH.search(raw)
        return {"path": m.group(1)} if m else {}


def _norm(path: Any) -> str:
    p = str(path).replace("\\", "/") if path else ""
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def _add(bucket: list[str], path: Any) -> None:
    p = _norm(path)
    if p and p not in bucket:
        bucket.append(p)


def extract_experience(messages: list[dict], tool_exit_codes: dict[str, int]) -> JobExperience:
    """Everything the job did, from its real tool calls in `messages`."""
    exp = JobExperience()
    for msg in messages or []:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args = _parse_args(fn.get("arguments"))
            if name in _WRITE_TOOLS:
                _add(exp.modified, args.get("path"))
            elif name == "create_files":
                for f in args.get("files") or []:
                    if isinstance(f, dict):
                        _add(exp.modified, f.get("path"))
            elif name == "apply_patch":
                for p in _PATCH_PATH.findall(str(args.get("patch", ""))):
                    if p != "/dev/null":
                        _add(exp.modified, p)
            elif name == "delete_file":
                _add(exp.deleted, args.get("path"))
            elif name == "move_file":
                _add(exp.deleted, args.get("from_path"))
                _add(exp.modified, args.get("to_path"))
            elif name in _READ_TOOLS:
                _add(exp.read, args.get("path"))
            elif name == "read_files":
                for p in args.get("paths") or []:
                    _add(exp.read, p)
            elif name == "run_command":
                cmd = str(args.get("command", "")).strip()
                if cmd:
                    exp.commands.append((cmd, tool_exit_codes.get(tc.get("id", ""))))
    exp.read = [p for p in exp.read if p not in exp.modified]
    return exp


def _task_title(job_id: str, task_text: str) -> str:
    first = " ".join((task_text or "").split())
    if len(first) > 70:
        first = first[:67].rstrip() + "..."
    return f"Task {job_id[:8]}: {first or '(no request text)'}"


def _listing(paths: list[str]) -> str:
    shown = ", ".join(paths[:_MAX_LISTED_FILES])
    return shown + (f" (+{len(paths) - _MAX_LISTED_FILES} more)" if len(paths) > _MAX_LISTED_FILES else "")


def record_job_experience(
    store: MemoryStore, *, repository: str, root: Path, job_id: str, status: str, task_text: str,
    messages: list[dict], tool_exit_codes: dict[str, int], error_reason: str | None = None,
) -> list[str]:
    """Write this job's episodic record (+ procedural records for verified commands). Returns the
    ids of records written/corroborated. Idempotent per job: re-recording the same job (a continued
    job finishing again) replaces its episodic record instead of adding a second one."""
    exp = extract_experience(messages, tool_exit_codes)
    if not (exp.modified or exp.deleted or exp.read or exp.commands):
        return []  # a pure conversation turn — nothing experiential to remember

    root = Path(root)
    touched = exp.modified + exp.deleted + exp.read
    anchors = file_anchors(root, touched[:_MAX_ANCHORED_FILES])

    outcome = status if not error_reason else f"{status} ({error_reason})"
    parts = [f"Outcome: {outcome}."]
    if exp.modified:
        parts.append(f"Modified: {_listing(exp.modified)}.")
    if exp.deleted:
        parts.append(f"Deleted: {_listing(exp.deleted)}.")
    if exp.read:
        parts.append(f"Read: {_listing(exp.read)}.")
    if exp.verified_commands:
        parts.append("Commands that exited 0: " + "; ".join(f"`{c}`" for c in exp.verified_commands[:6]) + ".")
    if exp.failed_commands:
        parts.append("Commands that failed: " + "; ".join(f"`{c}`" for c in exp.failed_commands[:6]) + ".")

    written: list[str] = []
    for prior in store.list(repository, "episodic"):
        if prior.metadata.get("source") == SOURCE and prior.metadata.get("job_id") == job_id:
            store.invalidate(prior.id, reason="replaced by a later completion of the same job")
    episode = store.add(
        repository=repository, memory_type="episodic", title=_task_title(job_id, task_text),
        content=" ".join(parts),
        metadata={"source": SOURCE, "job_id": job_id, "status": status,
                  "modified": exp.modified, "read": exp.read, "deleted": exp.deleted},
        anchors=anchors,
    )
    written.append(episode.id)

    if exp.verified_commands:
        from backend.repository.api import _manifest_paths  # lazy: api imports the memory package

        manifest_anchors = file_anchors(root, _manifest_paths(root))
        for cmd in exp.verified_commands:
            if len(cmd) > _MAX_COMMAND_CHARS or not _PROCEDURAL_COMMAND.match(cmd):
                continue
            record = store.add(
                repository=repository, memory_type="procedural", title=f"Verified command: {cmd}",
                content=f"`{cmd}` runs successfully (exit code 0) in this repository.",
                metadata={"source": SOURCE, "job_id": job_id, "command": cmd},
                anchors=manifest_anchors,
            )
            written.append(record.id)
    return written
