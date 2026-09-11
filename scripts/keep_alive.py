"""Keep the backend and the frontend up, and record why they went down.

The backend has died mid-run more than once — twice observed as a bare `exited with code 1` with
nothing in the captured output explaining it, which is the worst possible shape for this particular
failure: a job that was in flight stops making progress, and the only evidence is that the port
stopped answering. Jobs checkpoint and resume, so nothing is lost permanently, but a measurement
run that loses ten minutes to an unnoticed death produces a dataset with a hole in it.

This supervisor does two things:

  * restarts a server whose port has stopped answering, with backoff, and
  * captures that server's full stdout and stderr to a file, so the NEXT death has a cause.

The second is the more valuable half. A watchdog that silently resurrects a process that keeps
crashing hides the bug; the log is what turns "it died again" into something fixable.

Run it in the background and leave it:

    python scripts/keep_alive.py

Deliberate non-goals: it never restarts a server that is answering (a slow round is not a death —
the backend generating a large file can be quiet for many minutes while perfectly healthy), and it
never kills anything. It only starts what is already gone.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / ".codexa" / "keepalive"

# One entry per supervised server. `probe` must be a URL that answers only when the server is
# genuinely serving — the backend's bare "/" returns 404, which is a perfectly healthy response and
# would make a naive check believe a live server was broken.
SERVERS = [
    {
        "name": "backend",
        "probe": "http://127.0.0.1:8090/openapi.json",
        "args": [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", "8090"],
        # uvicorn needs a moment before it binds; probing sooner produces a false death and a
        # second launch that then fails on the port the first one is about to take.
        "grace": 20.0,
    },
    {
        "name": "graph-viz",
        "probe": "http://127.0.0.1:3000/chat",
        "args": ["npm.cmd" if os.name == "nt" else "npm",
                 "--prefix", "graph-viz", "run", "dev"],
        # Next's dev server compiles the route on first request; the first probe after a start can
        # take a while, and killing it for that would loop forever.
        "grace": 60.0,
    },
]

POLL_SECONDS = 15.0
# Backoff so a server that cannot start (a syntax error, a taken port) is not relaunched in a tight
# loop for hours. Doubles on each consecutive failure to come back, resets once it answers.
MIN_BACKOFF = 10.0
MAX_BACKOFF = 300.0


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _say(message: str) -> None:
    line = f"[{_stamp()}] {message}"
    print(line, flush=True)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LOG_DIR / "supervisor.log").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def alive(url: str, timeout: float = 5.0) -> bool:
    """True if the port answers at all. Any HTTP status counts — the question is whether something
    is listening and serving, not whether this particular path exists."""
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def launch(server: dict) -> subprocess.Popen | None:
    """Start a server detached, with its output captured to a per-server log.

    Detached on purpose: the point is that it outlives this supervisor, the terminal it was started
    from, and any tooling that reclaims child processes. That reclamation is one of the ways the
    backend has gone down before.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{server['name']}.log"
    try:
        handle = log_path.open("a", encoding="utf-8", errors="replace")
        handle.write(f"\n===== started {_stamp()} =====\n")
        handle.flush()
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(
            server["args"], cwd=str(ROOT), stdout=handle, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=flags,
        )
        _say(f"{server['name']}: started pid {process.pid} (log: {log_path})")
        return process
    except Exception as exc:  # noqa: BLE001 - a failed launch is reported and retried, never fatal
        _say(f"{server['name']}: launch failed: {exc}")
        return None


def main() -> int:
    state = {s["name"]: {"backoff": MIN_BACKOFF, "next_try": 0.0, "was_up": None} for s in SERVERS}
    _say("supervisor started; watching " + ", ".join(s["name"] for s in SERVERS))

    while True:
        for server in SERVERS:
            name = server["name"]
            entry = state[name]
            up = alive(server["probe"])

            if up:
                if entry["was_up"] is not True:
                    _say(f"{name}: up")
                entry["was_up"] = True
                entry["backoff"] = MIN_BACKOFF
                continue

            if entry["was_up"] is not False:
                _say(f"{name}: DOWN (probe {server['probe']} not answering)")
            entry["was_up"] = False

            now = time.monotonic()
            if now < entry["next_try"]:
                continue

            launch(server)
            time.sleep(server["grace"])
            if alive(server["probe"]):
                _say(f"{name}: recovered")
                entry["backoff"] = MIN_BACKOFF
                entry["was_up"] = True
            else:
                _say(f"{name}: did not come back; retrying in {entry['backoff']:.0f}s "
                     f"(see {LOG_DIR / (name + '.log')} for why)")
                entry["next_try"] = time.monotonic() + entry["backoff"]
                entry["backoff"] = min(MAX_BACKOFF, entry["backoff"] * 2)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        _say("supervisor stopped")
