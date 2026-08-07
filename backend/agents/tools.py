"""Agent tools — the real capabilities the chat agent can invoke.

File tools operate on the actual repository (reusing the Phase-2 file service). Web search hits the
Tavily API (needs TAVILY_API_KEY — built for LLM agents, no scraping/bot-block issues). run_python
executes in a short-lived subprocess with a timeout. Each tool has an OpenAI-style schema so litellm
can offer them to any provider that supports function calling.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

from backend.files.api import (
    create_directory,
    delete_path,
    edit_file,
    move_path,
    read_file,
    repo_root,
    search_files,
    write_file,
)

# The agent may freely scaffold/edit a loaded or newly-created repository, but must not mutate the
# live Codexa OS platform's own source through a chat message — read/search/list stay open on
# codexa-os (docs generation and "explain this platform" chats rely on that), only mutations are blocked.
_MUTATING_TOOLS = {"write_file", "create_directory", "delete_file", "move_file", "edit_file"}

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
            "name": "create_directory",
            "description": "Create a directory (and any missing parent directories) in the repository.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Repo-relative directory path."}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Make a small, targeted change to an existing file by replacing one exact, unique "
                "occurrence of old_text with new_text. Prefer this over write_file when only part of "
                "a file needs to change — safer than rewriting the whole file. old_text must match "
                "exactly once; include enough surrounding context to make it unique."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string", "description": "Exact existing text to replace."},
                    "new_text": {"type": "string", "description": "Text to replace it with."},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file, or an empty directory, from the repository.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Move or rename a file or directory within the repository.",
            "parameters": {
                "type": "object",
                "properties": {"from_path": {"type": "string"}, "to_path": {"type": "string"}},
                "required": ["from_path", "to_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_symbol",
            "description": (
                "Look up a function, class, hook, or component by name in the knowledge graph. Returns "
                "its file/line, an LLM-derived description of what it does (if already analyzed), and "
                "its direct callers/callees — grounded, precomputed context. Prefer this over "
                "read_file/search_code when you just need to know what a symbol does or is connected "
                "to; it's faster and doesn't require guessing which file it's in."
            ),
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "The symbol's exact name."}},
                "required": ["name"],
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
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return "Web search unavailable: TAVILY_API_KEY is not configured."
    body = json.dumps({
        "api_key": api_key, "query": query, "search_depth": "basic",
        "max_results": 5, "include_answer": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tavily.com/search", data=body,
        headers={"content-type": "application/json"}, method="POST",
    )
    try:
        raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return f"Web search failed: {exc.code} {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return f"Web search unavailable: {exc}"
    data = json.loads(raw)
    lines: list[str] = []
    if data.get("answer"):
        lines.append(f"Answer: {data['answer']}")
    for r in data.get("results", [])[:5]:
        lines.append(f"- {r.get('title', '')}: {r.get('content', '')[:300]} ({r.get('url', '')})")
    return "\n".join(lines) if lines else "No results found."


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


def _lookup_symbol(name: str, repository: str, *, graph: Any, store: Any) -> str:
    if graph is None:
        return "Symbol lookup unavailable in this context."
    nodes = graph.list_nodes()

    def in_repo(node: Any) -> bool:
        repo_prop = node.properties.get("repository")
        return (not repo_prop) if repository == "codexa-os" else repo_prop == repository

    matches = [
        n for n in nodes
        if n.node_type == "CodeSymbol" and in_repo(n) and n.properties.get("name") == name
    ]
    if not matches:
        return f"No symbol named '{name}' found in the graph for this repository."

    lines: list[str] = []
    annotations: dict[str, dict] = {}
    if store is not None:
        for rec in store.list(repository=repository, memory_type="semantic"):
            if rec.metadata.get("source") == "symbol_annotations":
                try:
                    annotations = json.loads(rec.content)
                except json.JSONDecodeError:
                    annotations = {}
                break

    by_id = {n.id: n for n in nodes}
    edges = [e for e in graph.list_edges_at() if e.edge_type in ("calls", "imports")]
    for node in matches[:5]:
        file_ = node.properties.get("file")
        line = node.properties.get("line")
        kind = node.properties.get("kind", "symbol")
        lines.append(f"{kind} `{name}` — {file_}:{line}")
        entry = annotations.get(f"symbol://{repository}/{file_}#{name}")
        if entry:
            lines.append(f"  what it does: {entry['summary']}")
        callers = [by_id[e.from_node_id].properties.get("name") for e in edges
                   if e.to_node_id == node.id and e.from_node_id in by_id]
        callees = [by_id[e.to_node_id].properties.get("name") for e in edges
                   if e.from_node_id == node.id and e.to_node_id in by_id]
        if callers:
            lines.append(f"  called by: {', '.join(str(c) for c in callers[:10])}")
        if callees:
            lines.append(f"  calls: {', '.join(str(c) for c in callees[:10])}")
    return "\n".join(lines)


def execute_tool(
    name: str, args: dict[str, Any], repository: str, *, graph: Any = None, store: Any = None,
) -> str:
    """Run a tool by name and return a text result for the model."""
    if name in _MUTATING_TOOLS and repository == "codexa-os":
        return (
            f"Tool '{name}' refused: the chat agent may not modify the Codexa OS platform's own "
            "source. Load or create a separate repository to scaffold or edit code in."
        )
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
        if name == "create_directory":
            create_directory(repo_root(repository), args["path"])
            return f"Created directory {args['path']}."
        if name == "edit_file":
            edit_file(repo_root(repository), args["path"], args["old_text"], args["new_text"])
            return f"Edited {args['path']}."
        if name == "delete_file":
            delete_path(repo_root(repository), args["path"])
            return f"Deleted {args['path']}."
        if name == "move_file":
            move_path(repo_root(repository), args["from_path"], args["to_path"])
            return f"Moved {args['from_path']} -> {args['to_path']}."
        if name == "lookup_symbol":
            return _lookup_symbol(args["name"], repository, graph=graph, store=store)
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
