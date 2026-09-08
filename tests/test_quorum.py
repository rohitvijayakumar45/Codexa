"""Tests for Quorum mode (backend/agents/quorum.py): multiple agents answer independently, their
claims are checked deterministically against the real graph before any of them sees a peer's
answer, and only a genuine tie the graph can't resolve falls back to a structured debate round."""

from backend.agents.quorum import QuorumRunRequest, QuorumService
from backend.graph.events import InMemoryGraphEventWriter
from backend.graph.repository import InMemoryGraphRepository
from backend.graph.schemas import GraphNodeCreate, GraphNodeType
from backend.graph.service import GraphService


class FakeLLM:
    """Scripted by (agent, model) -> raw JSON string, so each test controls exactly what each
    panel member says in each round without hitting a real provider."""

    def __init__(self, panel: list[str], scripts: dict[tuple[str, str], str]) -> None:
        self._panel = panel
        self._scripts = scripts

    def models_for_tier(self, tier: str) -> list[str]:
        return self._panel if tier == "balanced" else []

    def complete(self, messages, *, model=None, agent="generate", **kwargs) -> str:
        return self._scripts[(agent, model)]


def _graph_with_symbol(name: str, repository: str = "demo-repo") -> GraphService:
    graph = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())
    graph.add_node(GraphNodeCreate(
        node_type=GraphNodeType.CODE_SYMBOL, stable_id=f"symbol://{repository}/{name}",
        properties={"name": name, "kind": "function", "repository": repository},
    ))
    return graph


_PANEL = ["groq/modelA", "gemini/modelB", "nvidia_nim/modelC"]


def _card(answer: str, confidence: float, claim: str | None = None) -> str:
    claims = [{"type": "symbol_exists", "target": claim, "assertion": "exists"}] if claim else []
    import json
    return json.dumps({"answer": answer, "confidence": confidence, "claims": claims})


class TestPanelSelection:
    def test_panel_dedupes_by_provider(self):
        llm = FakeLLM(["groq/a", "groq/b", "gemini/c", "nvidia_nim/d"], {})
        service = QuorumService(llm=llm, graph=_graph_with_symbol("foo"))
        panel = service._panel_models(None)
        providers = [m.split("/", 1)[0] for m in panel]
        assert len(set(providers)) == len(providers)  # no provider repeated while alternatives exist

    def test_panel_fills_up_to_target_size_even_with_one_provider(self):
        llm = FakeLLM(["groq/a", "groq/b", "groq/c"], {})
        service = QuorumService(llm=llm, graph=_graph_with_symbol("foo"))
        panel = service._panel_models(None)
        assert len(panel) == 3

    def test_explicit_model_override_is_honored(self):
        llm = FakeLLM(["groq/a"], {})
        service = QuorumService(llm=llm, graph=_graph_with_symbol("foo"))
        assert service._panel_models(["custom/x", "custom/y"]) == ["custom/x", "custom/y"]


class TestQuorumResolvesWithoutDebate:
    def test_unanimous_verified_answer_resolves_immediately(self):
        graph = _graph_with_symbol("foo")
        scripts = {("quorum", m): _card("foo exists", 0.9, "foo") for m in _PANEL}
        service = QuorumService(llm=FakeLLM(_PANEL, scripts), graph=graph)

        result = service.run(QuorumRunRequest(repository="demo-repo", query="does foo exist?", models=_PANEL))

        assert result.resolved is True
        assert result.debated is False
        assert result.winning_answer == "foo exists"
        assert all(c.verified_count == 1 and c.failed_count == 0 for c in result.cards)

    def test_a_card_with_a_failed_claim_loses_to_a_verified_one_without_debate(self):
        graph = _graph_with_symbol("foo")
        scripts = {
            ("quorum", _PANEL[0]): _card("foo exists", 0.6, "foo"),       # verifies
            ("quorum", _PANEL[1]): _card("bar exists", 0.95, "bar"),      # confidently wrong, fails
            ("quorum", _PANEL[2]): _card("foo exists", 0.5, "foo"),       # verifies
        }
        service = QuorumService(llm=FakeLLM(_PANEL, scripts), graph=graph)

        result = service.run(QuorumRunRequest(repository="demo-repo", query="q", models=_PANEL))

        # The confidently-wrong card (highest raw confidence, but a failed claim) never wins - a
        # verified claim beats raw confidence outright, no debate round even needed here.
        assert result.resolved is True
        assert result.debated is False
        assert result.winning_answer == "foo exists"

    def test_graph_verification_beats_raw_confidence(self):
        graph = _graph_with_symbol("foo")
        scripts = {
            ("quorum", _PANEL[0]): _card("bar exists", 0.99, "bar"),  # very confident, wrong
            ("quorum", _PANEL[1]): _card("foo exists", 0.4, "foo"),   # unconfident, right
            ("quorum", _PANEL[2]): _card("bar exists", 0.9, "bar"),   # confident, wrong
        }
        service = QuorumService(llm=FakeLLM(_PANEL, scripts), graph=graph)

        result = service.run(QuorumRunRequest(repository="demo-repo", query="q", models=_PANEL))

        assert result.resolved is True
        assert result.debated is False
        assert result.winning_answer == "foo exists"


class TestQuorumDebateRound:
    def test_genuine_tie_triggers_debate_and_confidence_breaks_it_after(self):
        graph = _graph_with_symbol("foo")
        scripts = {
            ("quorum", _PANEL[0]): _card("A's answer", 0.8, "foo"),
            ("quorum", _PANEL[1]): _card("B's answer", 0.8, "foo"),
            ("quorum", _PANEL[2]): _card("C's answer", 0.3, None),  # no claims, clearly behind
            ("quorum_debate", _PANEL[0]): _card("A revises upward", 0.9, "foo"),
            ("quorum_debate", _PANEL[1]): _card("B's answer", 0.8, "foo"),
        }
        service = QuorumService(llm=FakeLLM(_PANEL, scripts), graph=graph)

        result = service.run(QuorumRunRequest(repository="demo-repo", query="q", models=_PANEL))

        assert result.debated is True
        assert result.resolved is True
        assert result.winning_answer == "A revises upward"
        assert all(c.round == (2 if c.model in (_PANEL[0], _PANEL[1]) else 1) for c in result.cards)

    def test_unresolvable_tie_surfaces_disagreement_instead_of_faking_a_winner(self):
        graph = _graph_with_symbol("foo")
        scripts = {
            ("quorum", _PANEL[0]): _card("A's opinion", 0.5, None),
            ("quorum", _PANEL[1]): _card("B's opinion", 0.5, None),
            ("quorum", _PANEL[2]): _card("A's opinion", 0.5, None),  # ties 3-way
            ("quorum_debate", _PANEL[0]): _card("A's opinion", 0.5, None),  # nobody revises
            ("quorum_debate", _PANEL[1]): _card("B's opinion", 0.5, None),
            ("quorum_debate", _PANEL[2]): _card("A's opinion", 0.5, None),
        }
        service = QuorumService(llm=FakeLLM(_PANEL, scripts), graph=graph)

        result = service.run(QuorumRunRequest(repository="demo-repo", query="q", models=_PANEL))

        assert result.debated is True
        assert result.resolved is False
        assert result.winning_answer is None
        assert len(result.cards) == 3  # every agent's final position still surfaced to the user


class TestQuorumAuditTrail:
    def test_every_run_is_recorded_as_a_graph_node(self):
        graph = _graph_with_symbol("foo")
        scripts = {("quorum", m): _card("foo exists", 0.9, "foo") for m in _PANEL}
        service = QuorumService(llm=FakeLLM(_PANEL, scripts), graph=graph)

        result = service.run(QuorumRunRequest(repository="demo-repo", query="does foo exist?", models=_PANEL))

        nodes = [n for n in graph.list_nodes() if n.node_type == GraphNodeType.QUORUM_DECISION]
        assert len(nodes) == 1
        assert nodes[0].id == result.decision_node_id
        assert nodes[0].properties["resolved"] is True
        assert nodes[0].properties["winning_answer"] == "foo exists"
        assert len(nodes[0].properties["cards"]) == 3
        assert nodes[0].provenance == "trusted_user"


class TestSelfCalibratingConfidence:
    def test_model_with_poor_track_record_loses_a_confidence_tie(self):
        from backend.graph.schemas import GraphNodeCreate, GraphNodeType

        graph = _graph_with_symbol("foo")
        # A prior run's belief cards, already persisted in the graph exactly as QuorumService writes
        # them — _PANEL[0] has mostly been wrong, _PANEL[1] mostly right.
        graph.add_node(GraphNodeCreate(
            node_type=GraphNodeType.QUORUM_DECISION, stable_id="quorum://history",
            properties={"cards": [
                {"model": _PANEL[0], "verified_count": 1, "failed_count": 9},
                {"model": _PANEL[1], "verified_count": 9, "failed_count": 1},
            ]},
        ))
        # This run: both agents state the SAME raw confidence with no checkable claims either way -
        # a pure confidence tie that only their calibration history can break.
        scripts = {
            ("quorum", _PANEL[0]): _card("A's answer", 0.9, None),
            ("quorum", _PANEL[1]): _card("B's answer", 0.9, None),
            ("quorum", _PANEL[2]): _card("C's answer", 0.1, None),
        }
        service = QuorumService(llm=FakeLLM(_PANEL, scripts), graph=graph)

        result = service.run(QuorumRunRequest(repository="demo-repo", query="q", models=_PANEL))

        assert result.debated is False  # calibration alone broke the tie, no debate round needed
        assert result.resolved is True
        assert result.winning_answer == "B's answer"

    def test_cold_start_model_gets_neutral_calibration(self):
        graph = _graph_with_symbol("foo")  # no prior QuorumDecision history at all
        service = QuorumService(llm=FakeLLM(_PANEL, {}), graph=graph)

        assert service._model_calibration(_PANEL[0]) == 1.0

    def test_calibration_ignores_other_models_history(self):
        from backend.graph.schemas import GraphNodeCreate, GraphNodeType

        graph = _graph_with_symbol("foo")
        graph.add_node(GraphNodeCreate(
            node_type=GraphNodeType.QUORUM_DECISION, stable_id="quorum://history",
            properties={"cards": [{"model": _PANEL[1], "verified_count": 0, "failed_count": 10}]},
        ))
        service = QuorumService(llm=FakeLLM(_PANEL, {}), graph=graph)

        assert service._model_calibration(_PANEL[0]) == 1.0  # unrelated model's bad history doesn't leak


class TestThinkingModelOutput:
    def test_think_block_is_stripped_before_json_extraction(self):
        # A reasoning-capable model can inline its chain-of-thought in <think> tags rather than a
        # separate reasoning field - including one that itself contains stray {braces}, which would
        # otherwise confuse the greedy JSON-block regex into grabbing the wrong span.
        graph = _graph_with_symbol("foo")
        raw = (
            "<think>Let me consider this. Maybe the answer is {something}? "
            "I should check symbol_exists claims.</think>\n"
            + _card("foo exists", 0.8, "foo")
        )
        service = QuorumService(llm=FakeLLM(_PANEL, {}), graph=graph)

        answer, confidence, claims = service._parse(raw)

        assert answer == "foo exists"
        assert confidence == 0.8
        assert len(claims) == 1

    def test_response_that_never_exits_thinking_falls_back_gracefully_not_with_raw_cot(self):
        graph = _graph_with_symbol("foo")
        raw = "<think>Still reasoning and reasoning, ran out of budget before answering...</think>"
        service = QuorumService(llm=FakeLLM(_PANEL, {}), graph=graph)

        answer, confidence, claims = service._parse(raw)

        assert "<think>" not in answer
        assert claims == []


class TestMalformedResponses:
    def test_non_json_response_falls_back_to_raw_text_with_no_claims(self):
        graph = _graph_with_symbol("foo")
        scripts = {
            ("quorum", _PANEL[0]): "I think foo probably exists but I'm not fully sure.",
            ("quorum", _PANEL[1]): _card("foo exists", 0.6, "foo"),
            ("quorum", _PANEL[2]): _card("foo exists", 0.6, "foo"),
        }
        service = QuorumService(llm=FakeLLM(_PANEL, scripts), graph=graph)

        result = service.run(QuorumRunRequest(repository="demo-repo", query="q", models=_PANEL))

        # Malformed card has 0 verified claims and loses outright to the two verified ones.
        assert result.winning_answer == "foo exists"

    def test_disallowed_claim_type_is_dropped_not_crashed_on(self):
        import json
        graph = _graph_with_symbol("foo")
        raw = json.dumps({
            "answer": "tests passed", "confidence": 0.9,
            "claims": [{"type": "test_passed", "target": "run_tests", "assertion": "passed"}],
        })
        scripts = {("quorum", m): raw for m in _PANEL}
        service = QuorumService(llm=FakeLLM(_PANEL, scripts), graph=graph)

        result = service.run(QuorumRunRequest(repository="demo-repo", query="q", models=_PANEL))

        # test_passed isn't in _ALLOWED_CLAIM_TYPES for quorum (no tools ran) - claim is dropped
        # without crashing; every card ends up with zero claims, and since all three panel members
        # say the same thing anyway this is unanimous agreement, not a tie needing debate.
        assert result.debated is False
        assert result.resolved is True
        assert all(c.verified_count == 0 and c.failed_count == 0 for c in result.cards)
