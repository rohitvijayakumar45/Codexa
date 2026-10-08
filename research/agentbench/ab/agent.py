"""A minimal, transparent tool-calling agent for RQ4 (no hidden prompting tricks).

Tools are structured (no arbitrary shell): list_files, read_file, replace_in_file, search (ripgrep,
the lexical baseline every condition has), run_program (the repository's own run/compile command),
finish — plus, depending on the condition, `find_callers`, backed by a NavBench adapter (language
server, Codexa graph, routing policy …), whose native output text is returned verbatim, exactly as
NavBench measures it.

Everything is logged: every tool call with output size, LLM usage per step, wall time. The LLM is
called through litellm; `llm` can be swapped for a fake in tests.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SYSTEM = ("You are a careful software engineer working in a small repository. Use the tools to inspect and "
          "edit files. Make exactly the requested change and nothing else. Call `finish` when done.")
MAX_OUTPUT_CHARS = 12000


def _tool(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props, "required": required}}}


BASE_TOOLS = [
    _tool("list_files", "List files under a directory of the repository.", {"path": {"type": "string"}}, []),
    _tool("read_file", "Read a file with line numbers (optionally a line range).",
          {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, ["path"]),
    _tool("replace_in_file", "Replace an exact text snippet in a file (must match exactly once).",
          {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, ["path", "old", "new"]),
    _tool("search", "Search the repository for a whole word (ripgrep -w). Returns file:line:col:text lines.",
          {"word": {"type": "string"}}, ["word"]),
    _tool("run_program", "Run the repository's own program/compile check and return its output.", {}, []),
    _tool("finish", "Declare the task complete.", {}, []),
]
FIND_CALLERS = _tool("find_callers", "Ask the code-navigation tool for the callers of a function or method.",
                     {"symbol": {"type": "string"}}, ["symbol"])


@dataclass
class RunLog:
    steps: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_calls: dict = field(default_factory=dict)
    tool_output_chars: dict = field(default_factory=dict)
    finished: bool = False
    error: str = ""
    wall_s: float = 0.0
    transcript: list = field(default_factory=list)


class Workspace:
    def __init__(self, root: Path, lang: str, run_cmd: list[str], rg: str = "rg"):
        self.root, self.lang, self.run_cmd, self.rg = Path(root), lang, run_cmd, rg

    def _safe(self, rel: str) -> Path:
        p = (self.root / (rel or ".")).resolve()
        if self.root.resolve() not in (p, *p.parents):
            raise ValueError("path escapes the repository")
        return p

    def list_files(self, path: str = ".") -> str:
        base = self._safe(path)
        files = [p.relative_to(self.root).as_posix() for p in sorted(base.rglob("*"))
                 if p.is_file() and "__pycache__" not in p.parts and "node_modules" not in p.parts]
        return "\n".join(files[:300]) or "(empty)"

    def read_file(self, path: str, start: int | None = None, end: int | None = None) -> str:
        lines = self._safe(path).read_text(encoding="utf-8", errors="replace").splitlines()
        s, e = max(1, start or 1), min(len(lines), end or len(lines))
        return "\n".join(f"{i}: {lines[i - 1]}" for i in range(s, e + 1)) or "(empty)"

    def replace_in_file(self, path: str, old: str, new: str) -> str:
        p = self._safe(path)
        text = p.read_text(encoding="utf-8")
        n = text.count(old)
        if n != 1:
            return f"ERROR: snippet found {n} times; it must match exactly once."
        p.write_text(text.replace(old, new, 1), encoding="utf-8")
        return "OK"

    def search(self, word: str) -> str:
        globs = ["*.py"] if self.lang == "py" else ["*.ts", "*.tsx", "*.js"]
        args = [self.rg, "-n", "--column", "--no-heading", "--color", "never", "-w", "-F", word]
        for g in globs:
            args += ["-g", g]
        p = subprocess.run(args + ["."], cwd=self.root, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return p.stdout.replace("\\", "/") or "(no matches)"

    def run_program(self) -> str:
        p = subprocess.run(self.run_cmd, cwd=self.root, capture_output=True, text=True, timeout=120)
        return f"exit code {p.returncode}\n{(p.stdout + p.stderr)[-4000:]}"


def run_agent(task_prompt: str, ws: Workspace, llm: Callable, *, find_callers: Callable[[str], str] | None = None,
              max_steps: int = 30) -> RunLog:
    log = RunLog()
    tools = BASE_TOOLS + ([FIND_CALLERS] if find_callers else [])
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task_prompt}]
    t0 = time.perf_counter()
    try:
        for _ in range(max_steps):
            log.steps += 1
            msg, usage = llm(messages, tools)
            log.prompt_tokens += usage.get("prompt_tokens", 0)
            log.completion_tokens += usage.get("completion_tokens", 0)
            calls = msg.get("tool_calls") or []
            messages.append({"role": "assistant", "content": msg.get("content") or "", **({"tool_calls": calls} if calls else {})})
            if not calls:
                messages.append({"role": "user", "content": "Use the tools to continue, or call `finish` if you are done."})
                continue
            for c in calls:
                name = c["function"]["name"]
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                log.tool_calls[name] = log.tool_calls.get(name, 0) + 1
                if name == "finish":
                    out = "Finished."
                    log.finished = True
                else:
                    try:
                        if name == "find_callers" and find_callers:
                            out = find_callers(str(args.get("symbol", "")))
                        else:
                            fn = getattr(ws, name)
                            out = fn(**args)
                    except Exception as e:  # noqa: BLE001 - tool errors are reported back to the model
                        out = f"ERROR: {type(e).__name__}: {e}"
                out = str(out)
                if len(out) > MAX_OUTPUT_CHARS:
                    out = out[:MAX_OUTPUT_CHARS] + "\n[output truncated]"
                log.tool_output_chars[name] = log.tool_output_chars.get(name, 0) + len(out)
                messages.append({"role": "tool", "tool_call_id": c.get("id", name), "content": out})
            if log.finished:
                break
    except Exception as e:  # noqa: BLE001
        log.error = f"{type(e).__name__}: {e}"[:500]
    log.wall_s = time.perf_counter() - t0
    log.transcript = messages
    return log


def litellm_llm(model: str, temperature: float = 0.0, timeout: int = 120, retries: int = 8,
                min_interval: float = 0.0) -> Callable:
    """`min_interval` spaces consecutive requests (seconds) to stay under a provider's rate limit.
    Rate-limit errors back off longer than other errors (up to ~2 min per attempt)."""
    import litellm
    state = {"last": 0.0}

    def call(messages, tools):
        last = None
        for attempt in range(retries):
            wait = state["last"] + min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            state["last"] = time.monotonic()
            try:
                r = litellm.completion(model=model, messages=messages, tools=tools, tool_choice="auto",
                                       temperature=temperature, timeout=timeout)
                m = r.choices[0].message
                calls = [{"id": tc.id, "type": "function", "function": {"name": tc.function.name,
                                                                         "arguments": tc.function.arguments or "{}"}}
                         for tc in (m.tool_calls or [])]
                u = r.usage or {}
                return ({"content": m.content, "tool_calls": calls},
                        {"prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                         "completion_tokens": getattr(u, "completion_tokens", 0) or 0})
            except Exception as e:  # noqa: BLE001 - provider hiccups: back off and retry
                last = e
                limited = "ratelimit" in type(e).__name__.lower() or "429" in str(e)[:200]
                time.sleep(min(120, 2 ** attempt * (15 if limited else 3)))
        raise last
    return call
