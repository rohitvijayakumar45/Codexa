import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.agents.jobs import Job, JobManager
from backend.agents.llm import CancellableStream, LLMClient


def test_claim_job_checkpoint_and_resume():
    """Claim: Agent jobs checkpoint to disk after rounds, enabling crash recovery
    to resume from the incomplete round rather than restarting from round 0."""
    with tempfile.TemporaryDirectory() as tmpdir:
        jobs_dir = Path(tmpdir)
        
        job = Job(
            id="test-job-123",
            repository="sample-repo",
            model="gemini/gemini-3.8-flash",
            messages=[
                {"role": "user", "content": "build page"},
                {"role": "assistant", "content": "I will write index.html"},
            ],
            round=2,
            status="running",
        )

        # Write checkpoint
        cp_file = jobs_dir / f"{job.id}.json"
        cp_file.write_text(json.dumps(job.to_disk()), encoding="utf-8")

        # Load checkpoint via Job.from_disk
        loaded = Job.from_disk(json.loads(cp_file.read_text(encoding="utf-8")))
        assert loaded.id == "test-job-123"
        assert loaded.round == 2
        assert len(loaded.messages) == 2


def test_claim_cancellable_stream_closes_provider():
    """Claim: CancellableStream wraps provider generator and allows safe out-of-thread
    termination, ensuring cancelled requests stop generating and billing."""
    mock_provider_stream = MagicMock()
    mock_provider_stream.close = MagicMock()

    live_box = {"stream": mock_provider_stream}
    
    def fake_gen():
        yield "chunk1"
        yield "chunk2"

    c_stream = CancellableStream(fake_gen(), live_box)
    chunk = next(c_stream)
    assert chunk == "chunk1"

    # Close from outside
    c_stream.close()
    assert mock_provider_stream.close.called


def test_claim_llm_multikey_advance():
    """Claim: LLMClient supports per-model multi-key rotation on 429 rate limit errors."""
    with patch.dict("os.environ", {
        "GEMINI_API_KEY": "key-1",
        "GEMINI_API_KEY_2": "key-2",
    }):
        client = LLMClient()
        model = "gemini/gemini-3.8-flash"

        # Initially key index is 0
        k0 = client._current_key(model)
        assert k0 == "key-1"

        # Advance key (simulating rate limit failover)
        advanced = client._advance_key(model)
        assert advanced is True
        k1 = client._current_key(model)
        assert k1 == "key-2"
