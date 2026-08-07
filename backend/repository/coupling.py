"""Git-mined change coupling — files that historically change together, even with zero static
reference between them. This is the "hidden coupling" class of bug static analysis structurally
cannot see (CodeScene's core insight, validated in peer-reviewed research): two files with no import
or call relationship can still break together in production because they encode the same business
rule twice, or one is a schema and the other hand-written glue that has to track it. Adds
`CORRELATES_WITH` edges to the graph so blast radius surfaces this instead of missing it entirely.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

_MAX_COMMITS = 250
_MIN_SHARED_COMMITS = 3
_MIN_COUPLING = 0.3  # at least 30% of the time these two files change together
_MAX_FILES_PER_COMMIT = 20  # skip huge commits (mass renames, vendored dumps) — noise, not signal
_MAX_PAIRS = 150


@dataclass
class CouplingEdge:
    file_a: str
    file_b: str
    strength: float  # 0-1: shared commits / min(occurrences of either file)
    shared_commits: int


def mine_change_coupling(dest: Path, known_files: set[str]) -> list[CouplingEdge]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(dest), "log", f"-{_MAX_COMMITS}", "--name-only", "--pretty=format:__COMMIT__"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []

    commits: list[list[str]] = []
    current: list[str] = []
    for raw_line in proc.stdout.split("\n"):
        line = raw_line.strip()
        if line == "__COMMIT__":
            if current:
                commits.append(current)
            current = []
        elif line:
            rel = line.replace("\\", "/")
            if rel in known_files:
                current.append(rel)
    if current:
        commits.append(current)

    occurrence: Counter[str] = Counter()
    co_occurrence: Counter[tuple[str, str]] = Counter()
    for files in commits:
        uniq = sorted(set(files))
        if len(uniq) < 2 or len(uniq) > _MAX_FILES_PER_COMMIT:
            continue
        for f in uniq:
            occurrence[f] += 1
        for a, b in combinations(uniq, 2):
            co_occurrence[(a, b)] += 1

    edges: list[CouplingEdge] = []
    for (a, b), shared in co_occurrence.items():
        if shared < _MIN_SHARED_COMMITS:
            continue
        strength = shared / min(occurrence[a], occurrence[b])
        if strength >= _MIN_COUPLING:
            edges.append(CouplingEdge(file_a=a, file_b=b, strength=round(strength, 3), shared_commits=shared))

    edges.sort(key=lambda e: -e.strength)
    return edges[:_MAX_PAIRS]
