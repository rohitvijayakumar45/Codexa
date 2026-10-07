"""Minimal MCP stdio client (newline-delimited JSON-RPC), used for codebase-memory-mcp sessions."""
from __future__ import annotations

import json
import subprocess
import threading
import queue


class McpError(Exception):
    pass


class McpClient:
    def __init__(self, cmd: list[str], env: dict, timeout: float = 600.0):
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     env=env, text=True, encoding="utf-8", errors="replace", bufsize=1)
        self.timeout = timeout
        self._id = 0
        self._q: dict[int, queue.Queue] = {}
        threading.Thread(target=self._reader, daemon=True).start()
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "navbench", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def _reader(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in msg and msg["id"] in self._q:
                self._q.pop(msg["id"]).put(msg)

    def request(self, method, params, timeout=None):
        self._id += 1
        q = queue.Queue()
        self._q[self._id] = q
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})
        try:
            msg = q.get(timeout=timeout or self.timeout)
        except queue.Empty:
            raise McpError(f"timeout {method}")
        if "error" in msg:
            raise McpError(str(msg["error"])[:300])
        return msg["result"]

    def call(self, tool: str, args: dict, timeout=None) -> tuple[str, bool]:
        res = self.request("tools/call", {"name": tool, "arguments": args}, timeout=timeout)
        text = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        return text, bool(res.get("isError"))

    def close(self):
        try:
            self.proc.kill()
        except Exception:  # noqa: BLE001
            pass
