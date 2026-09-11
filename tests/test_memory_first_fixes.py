"""Fixes found by an A/B run of the agent on encode/httpx, with and without Codexa's memory context.

1. A correct answer about `Client.send` was rejected by claim verification ("no symbol named
   'Client.send'") because the graph stores methods by bare name — a wasted correction round.
2. Symbol meanings were written in file order under an 80-per-run cap, so `Client` and `send` —
   what the first question was about — had none, and the agent read the file instead.
"""

from types import SimpleNamespace
from uuid import uuid4

from backend.agents.verification import Claim, ClaimType, _bare_symbol, _resolve_claim
from backend.repository.analyze import Symbol, analyze_repo, symbol_key
from backend.repository.semantic import _priority

_TWO_CLIENTS = '''
class Client:
    def send(self, request):
        self._set_timeout(request)
        return self._send_handling_auth(request)

    def _send_handling_auth(self, request):
        return request

    def _set_timeout(self, request):
        return request


class AsyncClient:
    async def send(self, request):
        return await self._send_handling_auth(request)

    async def _send_handling_auth(self, request):
        def nested():
            return 1
        return nested()


def helper():
    return Client().send(None)
'''


class TestSameNamedMethodsStayApart:
    """httpx: Client.send, AsyncClient.send and the ASGI send shared one graph node and one memory
    entry, so the injected context said `send --calls (incoming)--> _send_handling_auth`."""

    def _analysis(self, tmp_path):
        (tmp_path / "client.py").write_text(_TWO_CLIENTS, encoding="utf-8")
        return analyze_repo(tmp_path)

    def test_methods_are_keyed_by_their_class(self, tmp_path):
        keys = {symbol_key(s) for s in self._analysis(tmp_path).symbols}
        assert {"client.py#Client.send", "client.py#AsyncClient.send",
                "client.py#Client._send_handling_auth", "client.py#AsyncClient._send_handling_auth"} <= keys

    def test_a_nested_helper_is_not_mistaken_for_a_method(self, tmp_path):
        nested = next(s for s in self._analysis(tmp_path).symbols if s.name == "nested")
        assert nested.qualname == ""

    def test_calls_resolve_within_the_callers_own_class(self, tmp_path):
        calls = set(self._analysis(tmp_path).calls)
        assert ("client.py#Client.send", "client.py#Client._send_handling_auth") in calls
        assert ("client.py#AsyncClient.send", "client.py#AsyncClient._send_handling_auth") in calls
        assert ("client.py#Client.send", "client.py#AsyncClient._send_handling_auth") not in calls
        assert ("client.py#AsyncClient.send", "client.py#Client._send_handling_auth") not in calls

    def test_an_ambiguous_call_from_outside_any_class_is_left_unresolved(self, tmp_path):
        # helper() calls .send — two classes define it; guessing one would be an invented edge.
        assert not any(src == "client.py#helper" and dst.endswith(".send") for src, dst in self._analysis(tmp_path).calls)


class TestQualifiedSymbolNames:
    def test_qualifiers_are_stripped_to_the_graph_name(self):
        assert _bare_symbol("Client.send") == "send"
        assert _bare_symbol("Client::send") == "send"
        assert _bare_symbol("`send()`") == "send"
        assert _bare_symbol("httpx._client.Client.send") == "send"
        assert _bare_symbol("httpx/_auth.py:DigestAuth") == "DigestAuth"
        assert _bare_symbol("httpx\\_auth.py:DigestAuth.auth_flow") == "auth_flow"
        assert _bare_symbol("send") == "send"

    def test_a_qualified_method_claim_holds_when_the_method_exists(self):
        node = SimpleNamespace(id=uuid4(), node_type="CodeSymbol", properties={"name": "send", "repository": "httpx"})
        graph = SimpleNamespace(list_nodes=lambda: [node], list_edges_at=lambda: [])
        holds, _ = _resolve_claim(Claim(ClaimType.SYMBOL_EXISTS, "Client.send", "exists"), graph=graph, repository="httpx")
        assert holds

    def test_a_missing_method_is_still_rejected(self):
        node = SimpleNamespace(id=uuid4(), node_type="CodeSymbol", properties={"name": "send", "repository": "httpx"})
        graph = SimpleNamespace(list_nodes=lambda: [node], list_edges_at=lambda: [])
        holds, _ = _resolve_claim(Claim(ClaimType.SYMBOL_EXISTS, "Client.teleport", "exists"), graph=graph, repository="httpx")
        assert not holds


class TestAnnotationPriority:
    def _sym(self, name, kind="function"):
        return Symbol(name=name, kind=kind, file="httpx/_client.py", line=1)

    def test_classes_then_public_then_most_called_come_first(self):
        symbols = [self._sym("__init__"), self._sym("_set_timeout"), self._sym("send"),
                   self._sym("request"), self._sym("Client", kind="class")]
        calls = [("a#x", "httpx/_client.py#send"), ("a#y", "httpx/_client.py#send"),
                 ("a#z", "httpx/_client.py#request")]
        order = [s.name for s in _priority(symbols, calls)]
        assert order[0] == "Client"
        assert order[1:3] == ["send", "request"]
        assert set(order[3:]) == {"__init__", "_set_timeout"}

    def test_no_call_data_still_orders_by_kind_and_visibility(self):
        symbols = [self._sym("_helper"), self._sym("Public", kind="class"), self._sym("run")]
        assert [s.name for s in _priority(symbols, None)] == ["Public", "run", "_helper"]

    def test_a_heavily_called_method_outranks_an_uncalled_class(self):
        # httpx: 87 classes ranked strictly first used the whole budget and `send` never got a meaning.
        symbols = [self._sym("UnsetType", kind="class"), self._sym("send")]
        calls = [(f"a#{i}", "httpx/_client.py#send") for i in range(5)]
        assert [s.name for s in _priority(symbols, calls)] == ["send", "UnsetType"]

    def test_test_fixtures_come_after_library_code(self):
        fixture = Symbol(name="DigestApp", kind="class", file="tests/client/test_auth.py", line=1)
        library = self._sym("_private_helper")
        assert [s.name for s in _priority([fixture, library], None)] == ["_private_helper", "DigestApp"]
