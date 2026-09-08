"""Did anything actually happen? — repository-state diffing for the execution controller.

Why this exists
---------------
Every guard the job loop had before this one measured *activity*, and activity is exactly what a
stuck model produces in abundance. A round that emits 30,478 reasoning tokens to produce 131 tokens
of output is maximally active and completely unproductive. The reasoning-char cut in
backend/agents/jobs.py stops the pathological single round, and the round budget stops the
pathological job, but neither can answer the question the plan state machine actually needs
answered every round: *did this round change anything?*

This module answers it from the filesystem, because the filesystem is the one participant in the
loop with no incentive to be optimistic. Take a snapshot before a round, take one after, diff them.
A model can describe a file it did not write; it cannot make `st_size` change by describing it.

Deliberately narrow
-------------------
Reasoning is NOT an input here, and there is intentionally no parameter for it. The single most
tempting mistake in a progress check is to count "the model thought hard" as partial credit — that
is the precise failure this whole subsystem exists to catch, and admitting it here would launder it
back in. Text produced is not progress. Files changed is progress. Information genuinely retrieved
(a screenshot, a test run, a file read) is progress. Nothing else is.

This module has no LLM, graph or job dependency and holds no mutable state, so it stays cheap to
call every round and trivial to test.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from fastapi import HTTPException

from backend.agents.tools import GRAPH_DIRTYING_TOOLS
from backend.files.api import repo_root

# Directories that are never the agent's work product. node_modules and .venv are the ones that
# actually matter for cost — a single `npm install` drops ~30,000 files into the tree, and without
# pruning that one command would (a) make every snapshot take longer than the model round it is
# measuring, and (b) register as the largest "progress" any round ever made, which is the opposite
# of true: installing dependencies is setup, not the deliverable. .next/dist/build are generated
# output that changes on every build for reasons unrelated to whether the model wrote anything.
_SKIP_DIR_NAMES = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".pytest_cache",
})

# Hard ceiling on files visited per snapshot. Two snapshots are taken per round, so an unbounded
# walk of a large monorepo would put the progress check on the critical path of every round —
# a guard that costs more than the thing it guards gets disabled, and then nothing is guarded.
# 20k is far above any repository the agent realistically authors (a large scaffolded app is low
# hundreds of files) while still bounding the pathological case.
_MAX_FILES_WALKED = 20_000

# Tools that legitimately produce no disk change and whose entire purpose is to return information
# the task cannot proceed without. A round that only ran one of these has genuinely advanced: the
# model now knows something it did not know, which is a real state change even though `git status`
# is unmoved. Excluding these would make "read the file before editing it" — correct behaviour —
# look identical to stalling, and the controller would intervene against good work.
_INFORMATIVE_TOOLS = frozenset({
    "screenshot",
    "run_tests",
    "run_command",
    "browser_console",
    "read_file",
    "search_code",
    "get_design_guidance",
    "list_directory",
    "inspect_element",
    "run_python",
})


def _is_skipped_dir(name: str) -> bool:
    """Named skip-list, plus every dotfile directory. The blanket dot rule catches the long tail
    (.mypy_cache, .turbo, .ruff_cache, .idea, .vercel …) that would otherwise need adding one
    incident at a time — none of them are ever the artifact a task is judged on."""
    return name in _SKIP_DIR_NAMES or name.startswith(".")


@dataclass(frozen=True)
class RepoSnapshot:
    """What the repository looked like at one instant.

    Identity is (size, mtime_ns) rather than a content hash on purpose: hashing every file in a
    repository twice per round is real I/O for a check that only needs to answer "different or
    not". The trade is that a same-size edit within one filesystem mtime tick is invisible. That
    tick is 100ns on NTFS, which is orders of magnitude shorter than any round, so in practice the
    only way to lose an edit here is to rewrite a file with byte-identical length in the same
    instant — which is not a change worth crediting anyway.
    """

    #: repo-relative POSIX path -> (size_bytes, mtime_ns). Keys are always forward-slashed, even
    #: on Windows (the dev platform), so a snapshot is comparable across machines and log lines.
    files: dict[str, tuple[int, int]] = field(default_factory=dict)
    taken_at: float = 0.0

    @property
    def is_empty(self) -> bool:
        return not self.files


def snapshot(repository: str, *, max_files: int = _MAX_FILES_WALKED) -> RepoSnapshot:
    """Walk `repository` and record every non-skipped file's size and mtime.

    Never raises. A snapshot that fails — the repository is not loaded (repo_root raises
    HTTPException 404), a directory vanished mid-walk, a permission error — returns empty, which
    the comparison below reads as "can't tell" rather than "nothing happened". That degradation is
    the whole point: this is a diagnostic, and a diagnostic that can kill the job it is diagnosing
    is worse than no diagnostic at all. Every caller here is inside a running job thread.
    """
    taken_at = time.time()
    try:
        root = repo_root(repository)
    except (HTTPException, OSError, ValueError):
        return RepoSnapshot(files={}, taken_at=taken_at)

    files: dict[str, tuple[int, int]] = {}
    root_str = str(root)
    try:
        # followlinks stays False (the default): a symlink pointing at a parent directory would
        # otherwise walk forever, and a link into node_modules would defeat the pruning above.
        for dirpath, dirnames, filenames in os.walk(root_str):
            dirnames[:] = [d for d in dirnames if not _is_skipped_dir(d)]
            rel_dir = os.path.relpath(dirpath, root_str)
            prefix = "" if rel_dir == "." else rel_dir.replace(os.sep, "/").replace("\\", "/") + "/"
            for name in filenames:
                if len(files) >= max_files:
                    # Truncated rather than partial-and-silent: the cap applies identically to the
                    # before and after snapshot, so the compared prefix is the same set of files in
                    # the same os.walk order. A file created beyond the cap is simply invisible to
                    # the check, which reads as "no progress" — conservative in the safe direction,
                    # since it can only ever under-credit, never invent progress that did not occur.
                    return RepoSnapshot(files=files, taken_at=taken_at)
                try:
                    st = os.stat(os.path.join(dirpath, name))
                except OSError:
                    # Raced against the agent's own write, or an unreadable file. Skipping one entry
                    # is right; abandoning the snapshot over it is not.
                    continue
                files[prefix + name] = (st.st_size, st.st_mtime_ns)
    except OSError:
        return RepoSnapshot(files=files, taken_at=taken_at)
    return RepoSnapshot(files=files, taken_at=taken_at)


@dataclass(frozen=True)
class ProgressSignal:
    """The verdict for one interval — normally one round, sometimes one whole task."""

    created: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    #: Tool names executed in the interval, in call order, duplicates preserved. The duplicates
    #: matter: `is_thrashing` reads repetition, and de-duplicating here would erase the evidence.
    tools_ran: list[str] = field(default_factory=list)
    #: Subset of tools_ran that can change what is on disk (tools.GRAPH_DIRTYING_TOOLS). A round
    #: with mutating tools but no created/modified/deleted is its own distinct smell: the write
    #: was attempted and did not land (refused, failed, or written to a path nobody looks at).
    mutating_tools_ran: list[str] = field(default_factory=list)

    @property
    def changed_paths(self) -> list[str]:
        return [*self.created, *self.modified, *self.deleted]

    @property
    def made_progress(self) -> bool:
        """The load-bearing judgement of this whole feature.

        Disk changed -> progress, unconditionally. Otherwise, progress only if an informative tool
        ran: a screenshot taken, a test run, a file read. Zero tools is always False no matter how
        much text or reasoning the interval produced — that is not an oversight, it is the rule.
        The observed failure this exists for is a round that produced tens of thousands of
        reasoning characters, designed three complete products, discarded two, and wrote nothing.
        By any activity measure that round was the busiest of the run. It made no progress.
        """
        if self.created or self.modified or self.deleted:
            return True
        return any(tool in _INFORMATIVE_TOOLS for tool in self.tools_ran)

    def describe(self) -> str:
        """One short factual line, suitable for Task.progress_note and for the UI.

        Kept under ~120 chars deliberately: these accumulate on the task and are re-sent to the
        model every round of that task (see plan.Task.note), so a verbose note here becomes a
        per-round context cost for the rest of the task's life.
        """
        parts: list[str] = []
        if self.created:
            parts.append(_count_phrase("wrote", self.created))
        if self.modified:
            parts.append(_count_phrase("edited", self.modified))
        if self.deleted:
            parts.append(_count_phrase("deleted", self.deleted))
        if parts:
            line = ", ".join(parts)
        elif self.tools_ran:
            # Naming the tools is what makes the thrashing pattern legible to a human reading the
            # notes later: three consecutive "no file change; ran screenshot" lines say what
            # happened far more directly than three identical "no repository change" lines.
            seen: list[str] = []
            for tool in self.tools_ran:
                if tool not in seen:
                    seen.append(tool)
            line = "no file change; ran " + ", ".join(seen[:3])
        else:
            line = "no repository change"
        return line if len(line) <= 120 else line[:117] + "..."


def _count_phrase(verb: str, paths: Sequence[str]) -> str:
    """`wrote index.html` / `wrote index.html (+2 files)` — leads with a real path rather than a
    bare count, because "wrote 3 files" is not something a reader can check and a filename is."""
    head = paths[0]
    if len(paths) == 1:
        return f"{verb} {head}"
    return f"{verb} {head} (+{len(paths) - 1} files)"


def compare(
    before: RepoSnapshot,
    after: RepoSnapshot,
    *,
    tools_ran: Iterable[str],
) -> ProgressSignal:
    """Diff two snapshots into a verdict.

    Note the degenerate case: if `before` came back empty because the snapshot failed (see
    `snapshot`), every file in `after` reads as created. In practice both snapshots fail together —
    the usual cause is the repository not being loaded, which does not fix itself mid-round — so
    both sides are empty and the result is honestly "nothing observed". The asymmetric case is left
    un-special-cased on purpose: RepoSnapshot cannot distinguish "empty repo" from "failed walk"
    without a flag the consumers of this API do not have, and inventing a heuristic here would make
    a real first-file-in-an-empty-repo write (the single most important event in a scaffold task)
    the thing most likely to be misreported.
    """
    tools = list(tools_ran)
    created = sorted(set(after.files) - set(before.files))
    deleted = sorted(set(before.files) - set(after.files))
    modified = sorted(
        path for path, stat in after.files.items()
        if path in before.files and before.files[path] != stat
    )
    return ProgressSignal(
        created=created,
        modified=modified,
        deleted=deleted,
        tools_ran=tools,
        mutating_tools_ran=[t for t in tools if t in GRAPH_DIRTYING_TOOLS],
    )


def is_thrashing(recent: Sequence[ProgressSignal], *, window: int = 3) -> bool:
    """True when the last `window` intervals changed nothing on disk and introduced no new tool.

    The real incident this exists for
    --------------------------------
    A round was cut by the reasoning-char budget in jobs.py and retried with
    tool_choice="required", which makes prose an illegal response. The model satisfied the
    constraint with the cheapest calls available rather than the ones the task needed: it called
    `screenshot` against a URL serving nothing (ERR_CONNECTION_REFUSED), then `list_directory` on
    an empty repository, and then went straight back to planning. Every one of those rounds passes
    an activity check. Every one passes `made_progress`, because `screenshot` and `list_directory`
    are both in _INFORMATIVE_TOOLS — and they have to be, since taking a screenshot and listing a
    directory are exactly what legitimate work looks like too.

    The distinguishing feature is not any single round, it is the *shape across rounds*: the same
    small handful of tools recycled with the repository never moving. So this is the second-order
    check that `made_progress` structurally cannot be. A caller seeing True should escalate — force
    the task's own required tool, or fail the task — not merely nudge, since being told to call a
    tool is what produced this pattern in the first place.

    Needs at least `window` signals before it can fire: two identical quiet rounds are ordinary
    (read a file, then read another), three with nothing new is a pattern.

    Deliberately no cap on how many distinct tools count as "the same small set": the condition
    that carries the meaning is *no new tool name appearing*, and adding a size limit would only
    hand a stuck model a way out of the check by cycling five tools instead of three.
    """
    if window < 1 or len(recent) < window:
        return False
    tail = recent[-window:]
    if any(sig.created or sig.modified or sig.deleted for sig in tail):
        return False
    # The vocabulary of the first interval in the window is the baseline; every later interval must
    # stay inside it. A genuinely progressing task reaches for a tool it has not used yet, so a new
    # name appearing is the cheapest available evidence that something is still moving.
    #
    # The degenerate case — every interval in the window ran zero tools — satisfies this trivially
    # and is reported as thrashing, which is correct and is the more severe form of it: rounds
    # producing only text, which is precisely the 48-minute no-byte-written failure described in
    # backend/agents/plan.py.
    vocabulary = set(tail[0].tools_ran)
    return all(set(sig.tools_ran) <= vocabulary for sig in tail[1:])
