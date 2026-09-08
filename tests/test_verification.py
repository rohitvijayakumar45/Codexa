"""Tests for claim extraction and graph/tool-grounded verification
(backend/agents/verification.py)."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from backend.agents.verification import (
    Claim,
    ClaimType,
    extract_claims,
    verify_claims,
)


def _make_llm(raw_response: str | None = None, *, raises: Exception | None = None) -> MagicMock:
    llm = MagicMock()
    llm.models_for_tier.return_value = ["light-model"]
    if raises is not None:
        llm.complete.side_effect = raises
    else:
        llm.complete.return_value = raw_response
    return llm


# ── extract_claims ───────────────────────────────────────────────────────────

class TestExtractClaims:
    def test_parses_valid_json_and_drops_unknown_claim_types(self):
        raw = json.dumps({
            "claims": [
                {"type": "file_exists", "target": "backend/agents/receipts.py", "assertion": "created"},
                {"type": "symbol_exists", "target": "record_receipt", "assertion": "defined"},
                {"type": "not_a_real_claim_type", "target": "whatever", "assertion": "x"},
            ]
        })
        llm = _make_llm(raw)

        claims = extract_claims("I created the file and added a function.", llm)

        assert claims == [
            Claim(type=ClaimType.FILE_EXISTS, target="backend/agents/receipts.py", assertion="created"),
            Claim(type=ClaimType.SYMBOL_EXISTS, target="record_receipt", assertion="defined"),
        ]

    def test_returns_empty_list_on_invalid_json(self):
        llm = _make_llm("{ this is not valid json }")

        assert extract_claims("some answer", llm) == []

    def test_returns_empty_list_when_response_has_no_json_block(self):
        llm = _make_llm("sorry, I cannot help with that")

        assert extract_claims("some answer", llm) == []

    def test_llm_complete_raising_never_propagates_and_returns_empty(self):
        llm = _make_llm(raises=RuntimeError("provider is down"))

        assert extract_claims("some answer", llm) == []

    def test_empty_answer_text_returns_empty_without_calling_llm(self):
        llm = _make_llm()

        assert extract_claims("", llm) == []
        llm.models_for_tier.assert_not_called()
        llm.complete.assert_not_called()

    def test_whitespace_only_answer_text_returns_empty_without_calling_llm(self):
        llm = _make_llm()

        assert extract_claims("   \n\t  ", llm) == []
        llm.models_for_tier.assert_not_called()
        llm.complete.assert_not_called()


# ── Fakes for verify_claims (graph + edges) ─────────────────────────────────
# No existing fake-graph fixture pattern was found elsewhere in tests/ or backend/, so these use
# plain SimpleNamespace objects shaped like backend/graph/schemas.py's real Node/Edge (node_type,
# properties dict, id / from_node_id, to_node_id, edge_type) — the minimal duck type verify_claims
# actually reads.

def _node(node_type: str, **properties) -> SimpleNamespace:
    return SimpleNamespace(id=str(uuid4()), node_type=node_type, properties=properties)


def _edge(from_node_id: str, to_node_id: str, edge_type: str) -> SimpleNamespace:
    return SimpleNamespace(from_node_id=from_node_id, to_node_id=to_node_id, edge_type=edge_type)


class FakeGraph:
    def __init__(self, nodes=None, edges=None):
        self._nodes = nodes or []
        self._edges = edges or []

    def list_nodes(self):
        return self._nodes

    def list_edges_at(self):
        return self._edges


REPO = "codexa-os"


# ── verify_claims: FILE_EXISTS / SYMBOL_EXISTS / SYMBOL_USED_N_TIMES ────────

class TestVerifyClaimsGraphResolved:
    def test_file_exists_true_when_file_node_present(self):
        graph = FakeGraph(nodes=[_node("File", path="backend/agents/receipts.py")])
        claim = Claim(type=ClaimType.FILE_EXISTS, target="backend/agents/receipts.py", assertion="created")

        failed = verify_claims([claim], graph=graph, messages=[], tool_exit_codes={}, repository=REPO)

        assert failed == []

    def test_file_exists_false_when_file_node_absent(self):
        graph = FakeGraph(nodes=[])
        claim = Claim(type=ClaimType.FILE_EXISTS, target="backend/agents/missing.py", assertion="created")

        failed = verify_claims([claim], graph=graph, messages=[], tool_exit_codes={}, repository=REPO)

        assert len(failed) == 1
        assert failed[0][0] == claim

    def test_symbol_exists_true_when_symbol_node_present(self):
        graph = FakeGraph(nodes=[_node("CodeSymbol", name="record_receipt")])
        claim = Claim(type=ClaimType.SYMBOL_EXISTS, target="record_receipt", assertion="defined")

        failed = verify_claims([claim], graph=graph, messages=[], tool_exit_codes={}, repository=REPO)

        assert failed == []

    def test_symbol_exists_false_when_symbol_node_absent(self):
        graph = FakeGraph(nodes=[])
        claim = Claim(type=ClaimType.SYMBOL_EXISTS, target="does_not_exist", assertion="defined")

        failed = verify_claims([claim], graph=graph, messages=[], tool_exit_codes={}, repository=REPO)

        assert len(failed) == 1
        assert failed[0][0] == claim

    def test_symbol_used_n_times_matching_count(self):
        symbol = _node("CodeSymbol", name="record_receipt")
        edges = [
            _edge("caller-1", symbol.id, "calls"),
            _edge("caller-2", symbol.id, "calls"),
            _edge("caller-3", symbol.id, "imports"),
        ]
        graph = FakeGraph(nodes=[symbol], edges=edges)
        claim = Claim(type=ClaimType.SYMBOL_USED_N_TIMES, target="record_receipt", assertion="3 times")

        failed = verify_claims([claim], graph=graph, messages=[], tool_exit_codes={}, repository=REPO)

        assert failed == []

    def test_symbol_used_n_times_mismatching_count(self):
        symbol = _node("CodeSymbol", name="record_receipt")
        edges = [_edge("caller-1", symbol.id, "calls")]
        graph = FakeGraph(nodes=[symbol], edges=edges)
        claim = Claim(type=ClaimType.SYMBOL_USED_N_TIMES, target="record_receipt", assertion="3 times")

        failed = verify_claims([claim], graph=graph, messages=[], tool_exit_codes={}, repository=REPO)

        assert len(failed) == 1
        assert failed[0][0] == claim


# ── verify_claims: TEST_PASSED / ACTION_PERFORMED (tool-log resolved) ───────

class TestVerifyClaimsToolResolved:
    def test_test_passed_true_when_a_test_tool_exited_zero(self):
        messages = [{"role": "tool", "name": "run_tests", "tool_call_id": "call-1"}]
        tool_exit_codes = {"call-1": 0}
        claim = Claim(type=ClaimType.TEST_PASSED, target="tests", assertion="passed")

        failed = verify_claims(
            [claim], graph=None, messages=messages, tool_exit_codes=tool_exit_codes, repository=REPO,
        )

        assert failed == []

    def test_test_passed_false_when_no_test_tool_exited_zero(self):
        messages = [{"role": "tool", "name": "run_tests", "tool_call_id": "call-1"}]
        tool_exit_codes = {"call-1": 1}
        claim = Claim(type=ClaimType.TEST_PASSED, target="tests", assertion="passed")

        failed = verify_claims(
            [claim], graph=None, messages=messages, tool_exit_codes=tool_exit_codes, repository=REPO,
        )

        assert len(failed) == 1
        assert failed[0][0] == claim

    def test_action_performed_true_when_known_tool_was_called(self):
        messages = [{"role": "tool", "name": "write_file", "tool_call_id": "call-1"}]
        claim = Claim(type=ClaimType.ACTION_PERFORMED, target="write_file", assertion="created the file")

        failed = verify_claims(
            [claim], graph=None, messages=messages, tool_exit_codes={}, repository=REPO,
        )

        assert failed == []

    def test_action_performed_false_when_known_tool_was_not_called(self):
        messages: list[dict] = []
        claim = Claim(type=ClaimType.ACTION_PERFORMED, target="write_file", assertion="created the file")

        failed = verify_claims(
            [claim], graph=None, messages=messages, tool_exit_codes={}, repository=REPO,
        )

        assert len(failed) == 1
        assert failed[0][0] == claim

    def test_action_performed_unknown_target_is_silently_skipped_not_failed(self):
        messages: list[dict] = []
        claim = Claim(type=ClaimType.ACTION_PERFORMED, target="deploy_to_prod", assertion="done")

        failed = verify_claims(
            [claim], graph=None, messages=messages, tool_exit_codes={}, repository=REPO,
        )

        assert failed == []
