"""Layer C: record runtime call sites with sys.monitoring (Python >= 3.12).

Usage: python -m nb.trace_run ROOT OUT.json -- <script.py | -m module> [args...]

CALL fires *before* invocation, so each record distinguishes an attempted invocation from a
confirmed entry: confirmation requires a later PY_START of the expected Python code object
(the invoked function, or the class's Python-level __init__/__new__) on the same thread, before
that thread's next CALL. Only call sites located in ROOT are recorded; callees outside ROOT are
dropped. Columns are recorded as UTF-8 byte offsets (as co_positions reports them) and converted
to character offsets by the analysis.
"""
from __future__ import annotations

import atexit
import inspect
import json
import os
import runpy
import signal
import sys
import threading
import types

mon = sys.monitoring
TOOL = mon.PROFILER_ID


def main() -> None:
    root = os.path.realpath(sys.argv[1])
    out = sys.argv[2]
    rest = sys.argv[sys.argv.index("--") + 1:]
    prefix = root + os.sep
    in_root_cache: dict[str, bool] = {}
    pos_cache: dict[types.CodeType, list] = {}
    records: dict[tuple, list[int]] = {}
    local = threading.local()
    stats = {"call_events": 0, "unmapped_callee": 0}

    def in_root(fn: str) -> bool:
        r = in_root_cache.get(fn)
        if r is None:
            rp = os.path.realpath(fn) if fn and not fn.startswith("<") else ""
            r = in_root_cache[fn] = rp.startswith(prefix) and "/site-packages/" not in rp
        return r

    def callee_info(c):
        f = getattr(c, "__func__", c)
        expected = None
        if isinstance(c, type):
            init = c.__dict__.get("__init__") or getattr(c, "__init__", None)
            expected = getattr(init, "__code__", None)
            if expected is None:
                new = getattr(c, "__new__", None)
                expected = getattr(new, "__code__", None)
            mod = sys.modules.get(c.__module__)
            file = getattr(mod, "__file__", None) or ""
            return ("class", file, 0, c.__qualname__), expected
        code = getattr(f, "__code__", None)
        if code is None:
            return None, None
        expected = code
        try:
            u = inspect.unwrap(f)
        except Exception:  # noqa: BLE001
            u = f
        ucode = getattr(u, "__code__", code)
        return ("function", ucode.co_filename, ucode.co_firstlineno, ucode.co_qualname), expected

    def on_call(code, offset, callable_, arg0):
        if not in_root(code.co_filename):
            return mon.DISABLE
        stats["call_events"] += 1
        info, expected = callee_info(callable_)
        if info is None or not in_root(info[1]):
            local.pending = None
            return None
        pos = pos_cache.get(code)
        if pos is None:
            pos = pos_cache[code] = list(code.co_positions())
        p = pos[offset // 2] if offset // 2 < len(pos) else (None, None, None, None)
        key = (os.path.realpath(code.co_filename)[len(prefix):], p[0], p[1], p[2], p[3]) + info[:1] + (
            os.path.realpath(info[1])[len(prefix):], info[2], info[3])
        rec = records.setdefault(key, [0, 0])
        rec[0] += 1
        local.pending = (key, expected)
        return None

    def on_start(code, offset):
        if not in_root(code.co_filename):
            return mon.DISABLE
        pend = getattr(local, "pending", None)
        if pend is not None and pend[1] is code:
            records[pend[0]][1] += 1
            local.pending = None
        return None

    dumped = []

    def dump():
        if dumped:
            return
        dumped.append(1)
        mon.set_events(TOOL, 0)
        rows = [{"site_file": k[0], "line": k[1], "end_line": k[2], "bcol": k[3], "end_bcol": k[4], "callee_kind": k[5],
                 "callee_file": k[6], "callee_firstline": k[7], "callee_qualname": k[8],
                 "attempted": v[0], "confirmed": v[1]} for k, v in records.items()]
        with open(out, "w") as fh:
            json.dump({"root": root, "stats": stats, "records": rows}, fh)

    mon.use_tool_id(TOOL, "navbench")
    mon.register_callback(TOOL, mon.events.CALL, on_call)
    mon.register_callback(TOOL, mon.events.PY_START, on_start)
    atexit.register(dump)

    def on_term(signum, frame):  # wall-clock budget reached: keep what was observed
        dump()
        os._exit(0)
    signal.signal(signal.SIGTERM, on_term)
    mon.set_events(TOOL, mon.events.CALL | mon.events.PY_START)
    sys.path.insert(0, root)
    os.chdir(root)
    if rest[0] == "-m":
        sys.argv = [rest[1]] + rest[2:]
        try:
            runpy.run_module(rest[1], run_name="__main__", alter_sys=True)
        except SystemExit:
            pass
    else:
        sys.argv = rest
        try:
            runpy.run_path(rest[0], run_name="__main__")
        except SystemExit:
            pass


if __name__ == "__main__":
    main()
