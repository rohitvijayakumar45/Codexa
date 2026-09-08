"""Deterministic memory conflict resolution — no LLM judgment call decides whether a contradicting
memory is true.

Prior art (LongMemEval / MemoryAgentBench's FC-SH benchmark) shows systems that hand conflict
resolution to an LLM prompt at ingestion time (e.g. "does this new fact contradict the old one, and
which is right?") score badly specifically on conflict-freshness tasks — the judgment is inconsistent
and unauditable. This resolves conflicts by a fixed formula over (trust, corroboration count,
recency) instead: reproducible, explainable, and testable in isolation from any model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ConflictAction = Literal["corroborate", "supersede", "reject"]


@dataclass
class ConflictResolution:
    action: ConflictAction
    reason: str


def resolve_conflict(
    *, existing_content: str, existing_trust: float, existing_corroboration_count: int,
    new_content: str, new_trust: float = 1.0,
) -> ConflictResolution:
    """Decides what happens when a new memory record's content would collide with an existing
    active record for the same (repository, memory_type, title) key.

    - `corroborate`: the new record repeats the existing one — no new record needed, just reinforce
      the existing one's trust/corroboration count.
    - `supersede`: the new record's evidence outweighs the existing one — the existing record is
      soft-invalidated (kept for history, not deleted) and the new record becomes the active one.
    - `reject`: the existing record still outweighs the new, contradicting one — the existing record
      stays active, and the new record is stored already-invalidated (so the contradiction itself is
      on the record, auditable, without being surfaced by ordinary retrieval).

    Score = trust * corroboration_count. The new record is, by construction, always the more RECENT
    one (it was just created) — a tie therefore favors the new record, folding recency in as the
    tie-breaker without needing a separate timestamp comparison.
    """
    if existing_content.strip() == new_content.strip():
        return ConflictResolution("corroborate", "identical content — reinforcing the existing record")

    existing_score = existing_trust * existing_corroboration_count
    new_score = new_trust * 1  # a brand-new record always starts at corroboration_count == 1

    if new_score >= existing_score:
        return ConflictResolution(
            "supersede",
            f"new record's score ({new_score:.2f}) meets or exceeds the existing record's ({existing_score:.2f})",
        )
    return ConflictResolution(
        "reject",
        f"existing record's score ({existing_score:.2f}) exceeds the new, contradicting record's ({new_score:.2f})",
    )
