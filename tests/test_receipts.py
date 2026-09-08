"""Tests for hash-chained action receipts (backend/agents/receipts.py)."""

from backend.agents.receipts import (
    ActionReceipt,
    already_performed,
    record_receipt,
    verify_chain,
)


# ── Recording & chain validity ──────────────────────────────────────────────

class TestRecordAndVerifyChain:
    def test_empty_chain_is_vacuously_valid(self):
        assert verify_chain([]) is True

    def test_recording_multiple_receipts_produces_a_valid_chain(self):
        receipts: list[ActionReceipt] = []
        record_receipt(receipts, tool="write_file", args={"path": "a.py"}, result="ok-1")
        record_receipt(receipts, tool="edit_file", args={"path": "b.py"}, result="ok-2")
        record_receipt(receipts, tool="delete_file", args={"path": "c.py"}, result="ok-3")

        assert len(receipts) == 3
        assert verify_chain(receipts) is True

    def test_first_receipt_links_to_genesis(self):
        receipts: list[ActionReceipt] = []
        first = record_receipt(receipts, tool="write_file", args={"path": "a.py"}, result="ok")
        assert first.prev_receipt_hash == "genesis"

    def test_each_receipt_links_to_the_previous_result_hash(self):
        receipts: list[ActionReceipt] = []
        first = record_receipt(receipts, tool="write_file", args={"path": "a.py"}, result="ok-1")
        second = record_receipt(receipts, tool="edit_file", args={"path": "b.py"}, result="ok-2")
        assert second.prev_receipt_hash == first.result_hash


# ── Tamper detection ────────────────────────────────────────────────────────

class TestTamperDetection:
    def test_tampering_the_middle_receipts_result_hash_breaks_the_chain(self):
        receipts: list[ActionReceipt] = []
        record_receipt(receipts, tool="write_file", args={"path": "a.py"}, result="ok-1")
        record_receipt(receipts, tool="edit_file", args={"path": "b.py"}, result="ok-2")
        record_receipt(receipts, tool="delete_file", args={"path": "c.py"}, result="ok-3")
        assert verify_chain(receipts) is True

        receipts[1].result_hash = "tampered-hash"
        assert verify_chain(receipts) is False

    def test_tampering_the_first_receipts_result_hash_breaks_the_chain(self):
        receipts: list[ActionReceipt] = []
        record_receipt(receipts, tool="write_file", args={"path": "a.py"}, result="ok-1")
        record_receipt(receipts, tool="edit_file", args={"path": "b.py"}, result="ok-2")

        receipts[0].result_hash = "tampered-hash"
        assert verify_chain(receipts) is False

    def test_tampering_only_the_last_receipt_is_not_detectable(self):
        # Documents expected (not buggy) behavior: a hash chain only commits *forward* — a
        # receipt's result_hash is only ever checked by the *next* receipt's prev_receipt_hash.
        # Nothing has been recorded after the last receipt yet, so nothing in the chain references
        # its result_hash, and tampering it in place can't be caught by verify_chain() alone. This
        # mirrors how a blockchain's latest block is only confirmed once another is appended after it.
        receipts: list[ActionReceipt] = []
        record_receipt(receipts, tool="write_file", args={"path": "a.py"}, result="ok-1")
        record_receipt(receipts, tool="edit_file", args={"path": "b.py"}, result="ok-2")

        receipts[-1].result_hash = "tampered-hash"
        assert verify_chain(receipts) is True


# ── already_performed ────────────────────────────────────────────────────────

class TestAlreadyPerformed:
    def test_matches_identical_tool_and_args(self):
        receipts: list[ActionReceipt] = []
        recorded = record_receipt(
            receipts, tool="write_file", args={"path": "a.py", "content": "x"}, result="ok",
        )
        found = already_performed(receipts, tool="write_file", args={"path": "a.py", "content": "x"})
        assert found is recorded

    def test_does_not_match_same_tool_with_different_args(self):
        receipts: list[ActionReceipt] = []
        record_receipt(receipts, tool="write_file", args={"path": "a.py", "content": "x"}, result="ok")
        found = already_performed(receipts, tool="write_file", args={"path": "a.py", "content": "y"})
        assert found is None

    def test_does_not_match_different_tool_with_same_args(self):
        receipts: list[ActionReceipt] = []
        record_receipt(receipts, tool="write_file", args={"path": "a.py"}, result="ok")
        found = already_performed(receipts, tool="edit_file", args={"path": "a.py"})
        assert found is None

    def test_returns_none_for_empty_receipts(self):
        assert already_performed([], tool="write_file", args={"path": "a.py"}) is None


# ── Serialization round-tripping ────────────────────────────────────────────

class TestSerializationRoundTrip:
    def test_to_dict_from_dict_round_trips_exactly(self):
        receipts: list[ActionReceipt] = []
        original = record_receipt(receipts, tool="write_file", args={"path": "a.py"}, result="ok")

        restored = ActionReceipt.from_dict(original.to_dict())

        assert restored == original

    def test_to_dict_contains_the_expected_fields(self):
        receipts: list[ActionReceipt] = []
        receipt = record_receipt(receipts, tool="write_file", args={"path": "a.py"}, result="ok")

        d = receipt.to_dict()
        assert set(d.keys()) == {
            "action_id", "tool", "args_hash", "result_hash", "prev_receipt_hash", "timestamp",
        }
