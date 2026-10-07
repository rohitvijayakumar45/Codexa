"""Minimal LSP client for pyright-langserver (reference provider for Python)."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

_ROOT = Path(__file__).resolve().parent.parent
PYRIGHT = _ROOT / "node_modules" / "pyright" / "langserver.index.js"


def uri(p: Path) -> str:
    return "file://" + quote(str(p))


def path_of(u: str) -> str:
    return unquote(urlparse(u).path)


class LspError(Exception):
    pass


class PyrightClient:
    def __init__(self, root: Path, python: str | None = None, timeout: float = 120.0):
        self.root = root.resolve()
        self.python = python
        self.timeout = timeout
        self.proc = subprocess.Popen(
            ["node", str(PYRIGHT), "--stdio"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, cwd=self.root,
        )
        self._id = 0
        self._opened: set[str] = set()
        self._pending: dict[int, queue.Queue] = {}
        self._lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        settings = {"python": {"analysis": {"diagnosticMode": "openFilesOnly", "typeCheckingMode": "off",
                                            "useLibraryCodeForTypes": True}}}
        if python:
            settings["python"]["pythonPath"] = python
        self._settings = settings
        self.request("initialize", {
            "processId": os.getpid(), "rootUri": uri(self.root),
            "workspaceFolders": [{"uri": uri(self.root), "name": self.root.name}],
            "capabilities": {"workspace": {"configuration": True},
                             "textDocument": {"references": {}, "definition": {}}},
        })
        self.notify("initialized", {})
        self.notify("workspace/didChangeConfiguration", {"settings": settings})

    # --- transport
    def _send(self, msg: dict) -> None:
        body = json.dumps(msg).encode("utf-8")
        with self._lock:
            self.proc.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
            self.proc.stdin.flush()

    def _read_loop(self) -> None:
        f = self.proc.stdout
        while True:
            headers = {}
            while True:
                line = f.readline()
                if not line:
                    return
                line = line.decode().strip()
                if not line:
                    break
                k, v = line.split(":", 1)
                headers[k.lower()] = v.strip()
            msg = json.loads(f.read(int(headers["content-length"])))
            if "id" in msg and "method" in msg:  # server -> client request
                result = None
                if msg["method"] == "workspace/configuration":
                    result = [self._settings.get("python", {}) if (it.get("section") or "").startswith("python")
                              else self._settings for it in msg["params"]["items"]]
                    # pyright asks for "python" and "python.analysis"; answer each precisely
                    out = []
                    for it in msg["params"]["items"]:
                        sec = it.get("section") or ""
                        node = self._settings
                        for part in [s for s in sec.split(".") if s]:
                            node = node.get(part, {}) if isinstance(node, dict) else {}
                        out.append(node)
                    result = out
                self._send({"jsonrpc": "2.0", "id": msg["id"], "result": result})
            elif "id" in msg:
                q = self._pending.pop(msg["id"], None)
                if q:
                    q.put(msg)

    def request(self, method: str, params: dict, timeout: float | None = None):
        self._id += 1
        rid = self._id
        q: queue.Queue = queue.Queue()
        self._pending[rid] = q
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            msg = q.get(timeout=timeout or self.timeout)
        except queue.Empty:
            raise LspError(f"timeout: {method}")
        if "error" in msg:
            raise LspError(str(msg["error"]))
        return msg.get("result")

    def notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    # --- queries (line 1-based, col 0-based in our coordinates)
    def open(self, rel: str) -> None:
        # pyright only answers position queries for opened documents; workspace files are still searched.
        if rel in self._opened:
            return
        self._opened.add(rel)
        text = (self.root / rel).read_text(encoding="utf-8", errors="replace")
        self.notify("textDocument/didOpen", {"textDocument": {
            "uri": uri(self.root / rel), "languageId": "python", "version": 1, "text": text}})

    def warm(self, files: list[str], probes: list[tuple[str, int, int]], max_wait: float = 300.0) -> dict:
        """Readiness: pyright answers before workspace analysis finishes, returning incomplete reference sets.
        Open every source file, then wait until repeated probe queries return identical, non-shrinking
        results twice in a row (2 s apart)."""
        t0 = time.time()
        for f in files:
            self.open(f)
        prev, stable_rounds, rounds = None, 0, 0
        while time.time() - t0 < max_wait:
            cur = [tuple(sorted(self._raw_refs(*p))) for p in probes]
            rounds += 1
            if prev is not None and cur == prev:
                stable_rounds += 1
                if stable_rounds >= 2:
                    break
            else:
                stable_rounds = 0
            prev = cur
            time.sleep(2)
        return {"warm_s": time.time() - t0, "probe_rounds": rounds, "stable": stable_rounds >= 2,
                "probe_ref_counts": [len(x) for x in (prev or [])]}

    def _raw_refs(self, rel, line, col):
        res = self.request("textDocument/references", {
            "textDocument": {"uri": uri(self.root / rel)}, "position": {"line": line - 1, "character": col},
            "context": {"includeDeclaration": False}}) or []
        return [self._loc(r) for r in res]

    def references(self, rel: str, line: int, col: int) -> list[tuple[str, int, int]]:
        self.open(rel)
        res = self.request("textDocument/references", {
            "textDocument": {"uri": uri(self.root / rel)}, "position": {"line": line - 1, "character": col},
            "context": {"includeDeclaration": False}}) or []
        return [self._loc(r) for r in res]

    def definition(self, rel: str, line: int, col: int) -> list[tuple[str, int, int]]:
        self.open(rel)
        res = self.request("textDocument/definition", {
            "textDocument": {"uri": uri(self.root / rel)}, "position": {"line": line - 1, "character": col}}) or []
        if isinstance(res, dict):
            res = [res]
        return [self._loc(r) for r in res]

    def _loc(self, r: dict) -> tuple[str, int, int]:
        u = r.get("uri") or r.get("targetUri")
        rng = r.get("range") or r.get("targetSelectionRange")
        p = Path(path_of(u))
        try:
            rel = p.resolve().relative_to(self.root).as_posix()
        except ValueError:
            rel = "<external>" + str(p)
        return (rel, rng["start"]["line"] + 1, rng["start"]["character"])

    def close(self) -> None:
        try:
            self.request("shutdown", {}, timeout=10)
            self.notify("exit", {})
        except Exception:  # noqa: BLE001
            pass
        self.proc.kill()
