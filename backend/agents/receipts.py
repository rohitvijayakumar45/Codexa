"""Hash-chained action receipts for the agent's mutating tool calls.

Every effectful tool call (write_file, edit_file, delete_file, ...) gets a receipt recording a hash
of its arguments and a hash of its result, linked to the previous receipt in the same job by hash —
a tamper-evident chain, not just a plain log: altering or removing an entry breaks the chain for
every receipt after it, since each one's `prev_receipt_hash` commits to the one before.

This is deliberately minimal (no signing, no external witness) — it answers "what did this job
actually do, in what order, unmodified since" for audit/debugging, and gives `resume` a way to
recognize a mutating call it already performed (see `already_performed`) rather than repeating it.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

_GENESIS = "genesis"


def _hash_args(args: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _hash_result(result: str) -> str:
    return hashlib.sha256(result.encode("utf-8")).hexdigest()


@dataclass
class ActionReceipt:
    action_id: str
    tool: str
    args_hash: str
    result_hash: str
    prev_receipt_hash: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ActionReceipt":
        return cls(**data)


def record_receipt(receipts: list[ActionReceipt], *, tool: str, args: dict[str, Any], result: str) -> ActionReceipt:
    """Appends a new receipt to the chain and returns it. `receipts` is mutated in place (the
    caller's `Job.receipts` list) so the chain persists with the rest of the job's checkpoint."""
    prev_hash = receipts[-1].result_hash if receipts else _GENESIS
    receipt = ActionReceipt(
        action_id=str(uuid4()),
        tool=tool,
        args_hash=_hash_args(args),
        result_hash=_hash_result(result),
        prev_receipt_hash=prev_hash,
    )
    receipts.append(receipt)
    return receipt


def verify_chain(receipts: list[ActionReceipt]) -> bool:
    """True if every receipt's prev_receipt_hash correctly links to the result_hash before it —
    i.e. the chain hasn't been reordered, truncated from the middle, or had an entry edited."""
    expected_prev = _GENESIS
    for r in receipts:
        if r.prev_receipt_hash != expected_prev:
            return False
        expected_prev = r.result_hash
    return True


def already_performed(receipts: list[ActionReceipt], *, tool: str, args: dict[str, Any]) -> ActionReceipt | None:
    """Returns the existing receipt if this exact (tool, args) pair already has one — lets a resumed
    round recognize a mutating call it already made rather than repeating it. Matches on args hash
    only (not result), since the point is "would this call be identical," not "did it succeed"."""
    target = _hash_args(args)
    for r in receipts:
        if r.tool == tool and r.args_hash == target:
            return r
    return None
