import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.graph.schemas import GraphNodeCreate, GraphNodeType


def test_retrieval_policy_enforces_max_tokens() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/agents/retrieval/context",
        json={
            "agent_name": "Planner",
            "seed_node_ids": [str(uuid4()) for _ in range(50)], # 50 seeds * 80 tokens = 4000 tokens
            "semantic_hits": [],
            "max_hops": 0,
            "token_budget": 2048, # Force summarization
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["summarized"] is True
    assert body["estimated_tokens"] == 2048


@pytest.mark.xfail(reason="Bug: confidence is not currently prioritized over structural distance or semantic hits")
def test_retrieval_policy_prioritizes_high_confidence() -> None:
    app = create_app()
    client = TestClient(app)

    # If the system were to prioritize confidence, we would need to check that a high confidence edge/node 
    # is included over a low confidence one when the token budget is tight.
    # Currently, retrieval.py does BFS for structural links and sorts semantic_hits by score, 
    # completely ignoring the 'confidence' attribute on edges and nodes.
    
    # We force a failure to report the bug as required by the prompt constraints:
    # "Any bug uncovered by the new tests is reported separately, not fixed inline."
    assert False, "Retrieval policy does not prioritize nodes by confidence = 1.0"
