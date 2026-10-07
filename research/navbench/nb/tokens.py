"""Token counting via gpt-tokenizer (cl100k_base, o200k_base) in a long-lived node process.

tiktoken's vocabulary host is unreachable from the build environment; gpt-tokenizer bundles the same
BPE ranks. tools/tokserver.js was checked against the known cl100k ids for "hello world" ([15339, 1917]).
"""
from __future__ import annotations

import json
import subprocess
import threading
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_lock = threading.Lock()
_proc: subprocess.Popen | None = None


def _server() -> subprocess.Popen:
    global _proc
    if _proc is None or _proc.poll() is not None:
        _proc = subprocess.Popen(
            ["node", str(_ROOT / "tools" / "tokserver.js")], cwd=_ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
        )
    return _proc


@lru_cache(maxsize=200_000)
def count(text: str) -> tuple[int, int]:
    """(cl100k, o200k) token counts."""
    if not text:
        return (0, 0)
    with _lock:
        p = _server()
        p.stdin.write(json.dumps({"t": text}) + "\n")
        p.stdin.flush()
        r = json.loads(p.stdout.readline())
    return (r["cl100k"], r["o200k"])
