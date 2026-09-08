"""Smoke test for the /chat/agent/job/{job_id}/continue HTTP route (backend/chat/api.py).

The actual continue/resume logic is unit-tested thoroughly against JobManager directly in
tests/test_jobs_continue.py (mocking the LLM) — this just confirms the route is wired up and
returns the right status code for a job that doesn't exist, without needing a real agent job
(which would require a real LLM call) to stand up.
"""

from fastapi.testclient import TestClient

from backend.main import create_app


def test_continue_unknown_job_returns_404():
    app = create_app()
    client = TestClient(app)

    response = client.post("/chat/agent/job/does-not-exist/continue")

    assert response.status_code == 404
