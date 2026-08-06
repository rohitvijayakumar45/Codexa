"""Agent tools — the real capabilities the chat agent can invoke.

File tools operate on the actual repository (reusing the Phase-2 file service). Web search hits
DuckDuckGo (no key). run_python executes in a short-lived subprocess with a timeout. Each tool has an
OpenAI-style schema so litellm can offer them to any provider that supports function calling.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from typing import Any

from backend.files.api import build_tree, read_file, repo_root, search_files, write_file

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a file in the current repository.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Repo-relative file path."}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and folders under a directory in the repository (empty path = root).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Repo-relative directory path."}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search the repository for a string and return matching file:line results.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file in the repository with new contents. Use for edits.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the public web for current information. Returns top results.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute a short Python snippet and return its stdout/stderr. No network, 10s limit.",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        },
    },
]


def _truncate(text: str, limit: int = 6000) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n… [truncated, {len(text)} chars total]"


def _web_search(query: str) -> str:
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Codexa agent)"})
        html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        return f"Web search unavailable: {exc}"
    results: list[str] = []
    titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html)
    for i, title in enumerate(titles[:5]):
        clean_t = re.sub(r"<[^>]+>", "", title).strip()
        clean_s = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
        results.append(f"- {clean_t}: {clean_s}")
    return "\n".join(results) if results else "No results found."


def _run_python(code: str) -> str:
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=10,
        )
        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        return _truncate(out.strip() or "(no output)")
    except subprocess.TimeoutExpired:
        return "Execution timed out (10s limit)."
    except Exception as exc:  # noqa: BLE001
        return f"Execution error: {exc}"


def execute_tool(name: str, args: dict[str, Any], repository: str) -> str:
    """Run a tool by name and return a text result for the model."""
    try:
        if name == "read_file":
            return _truncate(read_file(repo_root(repository), args["path"]).content)
        if name == "list_directory":
            path = args.get("path", "")
            root = repo_root(repository)
            target = root / path if path else root
            entries = sorted(
                f"{p.name}/" if p.is_dir() else p.name
                for p in target.iterdir()
                if not p.name.startswith(".git") and p.name not in {"node_modules", "__pycache__", ".git"}
            )
            return "\n".join(entries) or "(empty)"
        if name == "search_code":
            hits = search_files(repo_root(repository), args["query"])
            return "\n".join(f"{h.path}:{h.line}: {h.text}" for h in hits[:40]) or "No matches."
        if name == "write_file":
            write_file(repo_root(repository), args["path"], args["content"])
            return f"Wrote {len(args['content'])} bytes to {args['path']}."
        if name == "web_search":
            return _web_search(args["query"])
        if name == "run_python":
            return _run_python(args["code"])
    except Exception as exc:  # noqa: BLE001 - report failures back to the model
        return f"Tool '{name}' failed: {exc}"
    return f"Unknown tool: {name}"


def parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
