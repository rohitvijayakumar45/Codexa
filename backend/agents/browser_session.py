"""A persistent headless-browser session shared across the browser_* tool calls.

Why this exists
---------------
The browser tools used to launch a fresh chromium, do one thing, and close it. That made
`screenshot`, `browser_navigate` (a screenshot alias), `inspect_page` and `inspect_element`
work — each is a self-contained one-shot — but left `browser_click`, `browser_type`,
`browser_scroll` and `browser_network` as dead stubs that returned "requires an active
Playwright session". They *couldn't* be anything else: clicking a button and then reading the
result needs the same page to survive between two separate tool calls, and nothing did.

This module owns exactly one long-lived browser + page for the life of the process, so a model
can drive a real interaction sequence: navigate -> type into a field -> click submit -> read the
console/network/DOM that resulted.

Two hard constraints from Playwright's *sync* API shape the design:

  1. Sync Playwright objects are **thread-affine** — a browser/page created on thread A cannot be
     touched from thread B (it raises a greenlet error).
  2. Sync Playwright refuses to run on a thread that has a **live asyncio event loop**.

This server runs tools from a threadpool, so consecutive browser_* calls in one job may land on
different threads. Meeting both constraints means: create the driver once, on a dedicated thread
that has no event loop, and marshal *every* operation onto that one thread through a command
queue. That is what `_BrowserSession` does. Callers only ever touch `SESSION.run(fn)`, which runs
`fn(page)` on the browser thread and returns its result (or re-raises its exception) synchronously.
"""

from __future__ import annotations

import queue
import threading
from typing import Any, Callable

# Console + network events captured live on the persistent page. Bounded so a long session that
# navigates many pages can't grow these without limit. Read via SESSION.run snapshots, not directly.
_MAX_EVENTS = 500


class _BrowserSession:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cmds: "queue.Queue[tuple[Callable[[Any], Any] | None, dict[str, Any]]]" = queue.Queue()
        self._ready = threading.Event()
        self._start_error: str | None = None
        self._pw: Any = None
        self._browser: Any = None
        self._page: Any = None
        # Populated by the page event listeners, on the browser thread only.
        self.console: list[str] = []
        self.network: list[dict[str, Any]] = []
        self.current_url: str = ""

    # -- lifecycle ---------------------------------------------------------------------------

    def _ensure(self) -> str | None:
        """Start the worker thread + browser if not already running. Returns an error string on
        failure (Playwright missing, launch failed) or None once a page is live."""
        with self._lock:
            if self._thread and self._thread.is_alive() and self._page is not None:
                return self._start_error
            if self._thread and self._thread.is_alive():
                # Thread up but page gone (crashed) — tear down so we relaunch clean.
                self._shutdown_locked()
            self._ready.clear()
            self._start_error = None
            self._thread = threading.Thread(target=self._run, name="codexa-browser", daemon=True)
            self._thread.start()
        # Launch can take a few seconds cold; generous ceiling, well under any tool timeout.
        self._ready.wait(timeout=45)
        return self._start_error

    def _run(self) -> None:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]
        except ImportError:
            self._start_error = (
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
            self._ready.set()
            return
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch()
            self._page = self._browser.new_page(viewport={"width": 1280, "height": 720})
            self._wire(self._page)
        except Exception as exc:  # noqa: BLE001
            self._start_error = f"Browser launch failed: {exc}"
            self._ready.set()
            return
        self._ready.set()

        while True:
            fn, box = self._cmds.get()
            if fn is None:  # shutdown sentinel
                break
            try:
                box["result"] = fn(self._page)
            except Exception as exc:  # noqa: BLE001 - marshalled back to the caller thread
                box["error"] = exc
            finally:
                box["done"].set()

        try:
            if self._browser is not None:
                self._browser.close()
            if self._pw is not None:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass
        self._page = self._browser = self._pw = None

    def _wire(self, page: Any) -> None:
        """Attach live listeners. These fire on the browser thread, so appending to the plain lists
        is safe without a lock (single writer)."""
        def on_console(m: Any) -> None:
            if m.type in ("error", "warning"):
                self.console.append(f"[{m.type}] {m.text}")
                del self.console[:-_MAX_EVENTS]

        def on_response(r: Any) -> None:
            try:
                self.network.append({
                    "status": r.status,
                    "method": r.request.method,
                    "url": r.url,
                })
                del self.network[:-_MAX_EVENTS]
            except Exception:  # noqa: BLE001
                pass

        page.on("console", on_console)
        page.on("pageerror", lambda e: (self.console.append(f"[pageerror] {e}"),
                                        self.console.__setitem__(slice(None), self.console[-_MAX_EVENTS:])))
        page.on("response", on_response)

    def _shutdown_locked(self) -> None:
        """Caller must hold self._lock."""
        if self._thread and self._thread.is_alive():
            self._cmds.put((None, {}))
            self._thread.join(timeout=5)
        self._thread = None
        self._page = self._browser = self._pw = None

    def close(self) -> None:
        with self._lock:
            self._shutdown_locked()

    # -- the one entry point every tool uses -------------------------------------------------

    def run(self, fn: Callable[[Any], Any], *, timeout: float = 30.0) -> Any:
        """Run fn(page) on the browser thread; return its value or raise its exception.

        Raises RuntimeError if the browser can't be started (e.g. Playwright not installed) — the
        tool wrappers catch that and turn it into a readable string for the model."""
        err = self._ensure()
        if err:
            raise RuntimeError(err)
        box: dict[str, Any] = {"done": threading.Event()}
        self._cmds.put((fn, box))
        if not box["done"].wait(timeout):
            raise TimeoutError(f"browser operation timed out after {timeout:g}s")
        if "error" in box:
            raise box["error"]
        return box.get("result")

    def reset_capture(self) -> None:
        """Clear console/network buffers — call on navigate so a page's events aren't attributed to
        the next one."""
        self.console.clear()
        self.network.clear()


SESSION = _BrowserSession()
