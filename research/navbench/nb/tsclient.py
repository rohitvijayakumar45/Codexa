"""Client for tools/tsserver.js (TS/JS index + language-service references)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


class TsError(Exception):
    pass


class TsClient:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.proc = subprocess.Popen(
            ["node", "--max-old-space-size=8192", str(_ROOT / "tools" / "tsserver.js"), str(self.root)],
            cwd=_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8",
        )

    def _call(self, msg: dict):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise TsError("ts server exited")
        r = json.loads(line)
        if not r["ok"]:
            raise TsError(r["err"])
        return r["res"]

    def index(self) -> dict:
        return self._call({"cmd": "index"})

    def references(self, rel: str, line: int, col: int) -> list[tuple[str, int, int]]:
        return [tuple(x) for x in self._call({"cmd": "refs", "file": rel, "line": line, "col": col})]

    def definition(self, rel: str, line: int, col: int) -> list[tuple[str, int, int]]:
        return [tuple(x) for x in self._call({"cmd": "def", "file": rel, "line": line, "col": col})]

    def close(self) -> None:
        self.proc.kill()
