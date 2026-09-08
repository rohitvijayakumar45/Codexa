"""Session-wide test isolation from the developer's local .env.

backend/main.py calls load_dotenv() unconditionally at import time, and CODEXA_SEED=1 is a
reasonable thing to have in a local dev .env (it's what makes the frontend show real data instead
of an empty graph — see the fix in backend/main.py for why it used to silently never fire at all).
But tests build backend.main.app (a module-level singleton created once at import time) or call
create_app() directly, expecting a pristine empty graph to assert exact node/trend/edge counts
against. Once seed_graph actually runs (as it now correctly does), its synthetic "codexa-os" data
mixes into those counts and several tests fail — not because the app is broken, but because the
test run is no longer hermetic against whatever's in the machine's own .env.

This has to happen here, at collection time (before any test file's `from backend.main import
app`/`create_app()` triggers backend.main's own load_dotenv() call), and as an explicit "0" rather
than deleting the var outright — load_dotenv()'s default override=False means an already-set env
var (even "0") survives it, whereas popping it would just let .env repopulate it on next import.
"""

import os

os.environ["CODEXA_SEED"] = "0"

# Same class of leak, second source. create_app() also rebuilds the graph for every repo present in
# `.codexa/repos/` on the host's real disk, so a developer who has loaded a few projects gets ~1600
# real graph events injected into tests that assert on exact node/edge/event counts. That produced
# eight failures which read as unrelated product bugs across perception/graph/memory/architecture/
# research, and were in fact one environment leak — the tests were right and the app was reaching
# outside the test sandbox. A suite whose result depends on which repos the developer happens to
# have open is not a suite you can trust to gate anything.
os.environ["CODEXA_REHYDRATE"] = "0"

# Pinned so the suite cannot be hung by a future change to the production default. Several tests
# drive _run with a model that fails on every call and rely on auto-continue exhausting to
# terminate; raising the default without this makes those loops run essentially forever rather than
# fail, which is a far worse failure mode than a red test — it looks like an infrastructure problem.
# Verified: setting this unbounded is exactly what happened, and it took the suite from 17s to
# past 400s with no output.
os.environ["CODEXA_MAX_AUTO_CONTINUES"] = "20"


# Third source of the same leak, and the one that writes rather than reads. JobManager checkpoints
# every job to backend/data/jobs/<id>.json, and tests drive real JobManager loops — so a test run
# scatters checkpoints named "force-tool", "status-round" and the like through the developer's
# actual job history, where they show up as real jobs in the UI and in any "what was running?"
# check. It also raced the live server: a checkpoint write during one run failed with
# "[WinError 5] Access is denied" because the running backend held the same file.
#
# Redirected per-session to a temp directory. Patched as the module attribute rather than via an env
# var because JOBS_DIR is computed at import time from __file__, so there is nothing to configure —
# and mkdir'd here because JobManager.__init__ only creates the directory it captured at import.
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _isolate_job_checkpoints():
    from backend.agents import jobs

    with tempfile.TemporaryDirectory(prefix="codexa-test-jobs-") as tmp:
        original, jobs.JOBS_DIR = jobs.JOBS_DIR, Path(tmp)
        jobs.JOBS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            yield
        finally:
            jobs.JOBS_DIR = original
