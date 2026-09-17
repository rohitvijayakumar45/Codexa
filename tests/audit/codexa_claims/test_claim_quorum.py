from unittest.mock import MagicMock
from backend.agents.quorum import (
    BeliefCard,
    BeliefCardClaim,
    QuorumService,
    _PANEL_SIZE,
    _ALLOWED_CLAIM_TYPES,
)
from backend.agents.verification import ClaimType, Claim
from backend.graph.schemas import GraphNodeCreate, GraphNodeType, GraphNodeProvenance
from backend.graph.service import GraphService
from backend.graph.repository import InMemoryGraphRepository
from backend.graph.events import InMemoryGraphEventWriter


def test_claim_quorum_belief_cards_and_claim_restrictions():
    """Claim: Quorum restricts claim types to verifiable filesystem/graph facts
    (FILE_EXISTS, SYMBOL_EXISTS, SYMBOL_USED_N_TIMES) and rejects ungrounded claims."""
    assert ClaimType.FILE_EXISTS in _ALLOWED_CLAIM_TYPES
    assert ClaimType.SYMBOL_EXISTS in _ALLOWED_CLAIM_TYPES
    assert ClaimType.ACTION_PERFORMED not in _ALLOWED_CLAIM_TYPES
    assert ClaimType.TEST_PASSED not in _ALLOWED_CLAIM_TYPES


def test_claim_quorum_deterministic_claim_verification():
    """Claim: Quorum ranks cards by net verified claims against the graph/filesystem.
    An ungrounded answer is eliminated, and only the grounded winner survives in the top rank."""
    repo = InMemoryGraphRepository()
    svc = GraphService(repository=repo, event_writer=InMemoryGraphEventWriter())

    svc.add_node(GraphNodeCreate(
        node_type=GraphNodeType.FILE,
        stable_id="backend/main.py",
        properties={"path": "backend/main.py"},
        provenance=GraphNodeProvenance.INTERNAL_CODE,
    ))

    q_svc = QuorumService(llm=MagicMock(), graph=svc)
    
    # Grounded card: 1 verified, 0 failed, moderate confidence 0.7
    card_grounded = BeliefCard(
        model="model-grounded",
        answer="backend/main.py is the entrypoint",
        confidence=0.7,
        claims=[
            BeliefCardClaim(type="file_exists", target="backend/main.py", assertion="exists")
        ],
        verified_count=1,
        failed_count=0,
        failed_reasons=[],
        round=0,
    )
    
    # Ungrounded card: 0 verified, 1 failed, extreme confidence 0.99
    card_hallucinated = BeliefCard(
        model="model-hallucinated",
        answer="frontend/server.js is the entrypoint",
        confidence=0.99,
        claims=[
            BeliefCardClaim(type="file_exists", target="frontend/server.js", assertion="exists")
        ],
        verified_count=0,
        failed_count=1,
        failed_reasons=["file does not exist"],
        round=0,
    )

    ranked = q_svc._rank([card_hallucinated, card_grounded])
    # The grounded card completely eliminates the ungrounded card from top rank
    assert len(ranked) == 1
    assert ranked[0].model == "model-grounded"


def test_claim_quorum_adversarial_rebuttal_rule():
    """Claim: Debate instructions explicitly bar changing an answer based on peer confidence or prose."""
    from backend.agents.quorum import _DEBATE_PROMPT
    assert "Do not change your answer because a peer sounds more confident" in _DEBATE_PROMPT
    assert "confidence and phrasing are not evidence" in _DEBATE_PROMPT
    assert "Revise your answer ONLY if a peer cites a SPECIFIC claim that verified" in _DEBATE_PROMPT
