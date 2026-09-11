"""Multi-provider LLM client with task-based routing and real per-model context windows.

Wraps litellm so the app can route across NVIDIA NIM, Groq, Google Gemini, and z.ai (GLM). Two
things live here on purpose:

  * A model registry with each model's REAL documented context window and a capability tier
    (heavy / balanced / light).
  * A routing layer keyed off task type — high-stakes work (architecture, graph, reasoning) goes to
    the heavy tier (GLM 5.x); low-stakes work (docs, summaries) goes to a light tier — so we don't
    default everything to the most expensive model.

A model is only offered if the provider's API key is configured.
"""

from __future__ import annotations

import collections
import json
import logging
import os
import threading
import time
from typing import Any, Callable, Iterator

import litellm

from backend.agents.usage import UsageTracker

logger = logging.getLogger(__name__)
litellm.suppress_debug_info = True
litellm.drop_params = True

ZAI_API_BASE = "https://api.z.ai/api/paas/v4"
TOKENROUTER_API_BASE = "https://api.tokenrouter.com/v1"

# id -> (label, context_window, tier, provider). Context windows are the models' documented limits.
#
# Groq's llama-3.1-8b-instant / llama-3.3-70b-versatile shut down 2026-08-16 (Groq's own
# deprecation notice) — replaced below with their recommended successors, not just supplemented,
# so nothing here silently breaks in a week. NVIDIA NIM's catalog churns even faster: several
# listed models (deepseek-ai/deepseek-v4-pro, qwen/qwen3-coder-480b-a35b-instruct,
# nemotron-4-340b-instruct, llama-3.1-405b-instruct) turned out to be EOL'd or undeployed when
# actually called, despite still appearing in the catalog — every entry below was verified with a
# real completion call, not taken from docs alone.
MODEL_REGISTRY: dict[str, tuple[str, int, str, str]] = {
    # Heavy tier
    "gemini/gemini-3.8-flash": ("Gemini 3.8 Flash", 1048576, "heavy", "gemini"),
    "nvidia_nim/deepseek-ai/deepseek-v4-pro-0813": ("DeepSeek V4 Pro", 128000, "heavy", "nvidia"),
    "nvidia_nim/nvidia/nemotron-3-super-120b-a12b": ("Nemotron 3 Super 120B", 1000000, "heavy", "nvidia"),
    "groq/openai/gpt-oss-120b": ("GPT-OSS 120B (Groq)", 131072, "heavy", "groq"),
    # Balanced tier
    "gemini/gemini-3.7-flash": ("Gemini 3.7 Flash", 1048576, "balanced", "gemini"),
    "groq/qwen/qwen3.6-27b": ("Qwen3.6 27B (Groq)", 131072, "balanced", "groq"),
    # Not in litellm's static model catalog (too new) — verified directly against Cerebras's own
    # /v1/models endpoint, same "trust a real call over the docs" rule this registry already
    # follows for NVIDIA NIM's fast-churning catalog.
    "cerebras/qwen-3.8-27b": ("Qwen 3.8 27B (Cerebras)", 128000, "balanced", "cerebras"),
    "nvidia_nim/mistralai/mistral-nemotron": ("Mistral Nemotron", 128000, "balanced", "nvidia"),
    # Verified against Mistral's own /v1/models (mistral-large-latest isn't on the free tier —
    # "tier_not_allowed" — this one is, confirmed by a real call reaching a rate-limit response
    # rather than an access-denied one).
    "mistral/mistral-medium-latest": ("Mistral Medium (free)", 128000, "balanced", "mistral"),
    # Light tier
    # Verified 2026-09-11 with a real call on all four configured keys (~2s each). Google's own 404
    # for 2.5-flash on newer keys ("no longer available to new users") names this as the successor.
    "gemini/gemini-3.6-flash": ("Gemini 3.6 Flash", 1048576, "light", "gemini"),
    "groq/openai/gpt-oss-20b": ("GPT-OSS 20B (Groq)", 131072, "light", "groq"),
    "gemini/gemini-2.5-flash": ("Gemini 2.5 Flash", 1048576, "light", "gemini"),
    "openrouter/nvidia/nemotron-3.5-lightning:free": ("Nemotron 3.5 Lightning (free)", 1000000, "light", "openrouter"),
    # Tier is "ultra_heavy", not "balanced": tier_of() is what jobs.py's run_round uses to pick the
    # failover ring for a rate-limited orchestrator. Left as "balanced" it resolved the balanced
    # ring and walked GLM straight onto Gemini — spending the exact quota its delegated workers run
    # on. It still appears in the heavy/balanced _TIER_ORDER lists (those are "who can serve this
    # task", a separate question) so nothing loses GLM as a fallback option.
    "tokenrouter/z-ai/glm-5.3-free": ("GLM 5.3 (free, TokenRouter)", 128000, "ultra_heavy", "tokenrouter"),
    # Real function-calling support (unlike several free/light entries above) — a solid default
    # for tool-orchestration test runs. "global." is this account's actual cross-region inference
    # profile for Haiku 4.5 (confirmed in the Bedrock console under ap-south-2 — the generic
    # "apac." profile ID from litellm's own catalog came back "invalid" for this account/region).
    "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0": ("Claude Haiku 4.5 (Bedrock)", 200000, "light", "bedrock"),
    # Local, no API key, no network egress — this machine's own Ollama daemon. Tag confirmed live
    # via GET localhost:11434/api/tags (not guessed): "josiefied-qwen3:latest", an abliterated
    # Qwen3 8B GGUF build, capabilities include "tools" so real function-calling works. ollama_chat
    # (not bare ollama) is litellm's chat-template-aware route — required for tool-calling to work
    # correctly. Context window is the model's own reported context_length, not a spec-sheet guess.
    "ollama_chat/josiefied-qwen3:latest": ("Qwen3 8B (Ollama, local)", 40960, "light", "ollama"),
    # "content" tier - deliberately NOT in _TIER_ORDER below, so model_for_task/models_for_tier can
    # NEVER select this as a job's orchestrating model. qwen-plus-character has function/tool-calling
    # explicitly UNSUPPORTED in every region (confirmed via Alibaba's own docs) - using it to drive
    # jobs.py's tool-calling loop would break on the very first tool call. It's only reachable
    # directly by model name from backend/agents/tools.py's generate_with_qwen tool, which calls
    # llm.complete() (no tools=) to get pure generated text/code, leaving actual tool execution
    # (write_file etc.) to whatever tool-calling model is running the job. UNVERIFIED by a real
    # completion call, unlike every other entry here - see the .env comment for why.
    "dashscope/qwen-plus-character": ("Qwen Plus Character (DashScope, content-only)", 32768, "content", "dashscope"),
}

_PROVIDER_ENV = {
    "nvidia": "NVIDIA_API_KEY",
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "zai": "ZAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "tokenrouter": "TOKENROUTER_API_KEY",
    # litellm's own env var name for Bedrock's newer bearer-token auth (not the traditional
    # AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY SigV4 flow) — see base_aws_llm.py's
    # get_secret_str("AWS_BEARER_TOKEN_BEDROCK") in the installed litellm package.
    "bedrock": "AWS_BEARER_TOKEN_BEDROCK",
    "cerebras": "CEREBRAS_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    # No real API key - local daemon, no auth. Availability is gated on OLLAMA_API_BASE like every
    # other provider here (truthy env var = offered); __init__ defaults it to localhost so it's on
    # unless explicitly unset, since there's no "key" a user would otherwise paste into .env.
    "ollama": "OLLAMA_API_BASE",
    "dashscope": "DASHSCOPE_API_KEY",
}

# Preference order within each tier (only verified live endpoints).
_TIER_ORDER: dict[str, list[str]] = {
    # Orchestrator tier. GLM sits alone here on purpose: its N configured keys (TOKENROUTER_API_KEY,
    # _2, _3, _4) are N independent quota buckets that _active_key_index round-robins between, so
    # "four GLMs" is one model id backed by four separate limits. The point of separating this from
    # "heavy" is quota isolation — an ultra_heavy orchestrator never touches Gemini, which leaves
    # Gemini's entire budget for the delegated workers (_WORKER_RING) instead of making the
    # orchestrator and its own workers compete for the same buckets.
    "ultra_heavy": [
        "tokenrouter/z-ai/glm-5.3-free",
    ],
    "heavy": [
        "gemini/gemini-3.8-flash",
        # 3.7 sits right behind 3.8 now too — same key pool, so this isn't extra quota, but a
        # 3.8 rate limit (all keys exhausted) still leaves 3.7 genuinely reachable moments later
        # once the window rolls, and it's a stronger fallback than jumping straight to GLM.
        "gemini/gemini-3.7-flash",
        # Kimi K3 used to sit here — removed: when a gemini-3.8-flash job hit its rate limit and
        # fell back into this list, Kimi's slow/verbose non-tool-calling style meant the job just
        # stalled and timed out instead of recovering. GLM 5.3 (already verified working, already
        # praised for output quality in this session's own model comparisons) takes its slot.
        "tokenrouter/z-ai/glm-5.3-free",
        "nvidia_nim/nvidia/nemotron-3-super-120b-a12b",
        "groq/openai/gpt-oss-120b",
    ],
    "balanced": [
        "gemini/gemini-3.7-flash",
        "gemini/gemini-3.8-flash",
        "groq/qwen/qwen3.6-27b",
        "cerebras/qwen-3.8-27b",
        "groq/openai/gpt-oss-120b",
        "tokenrouter/z-ai/glm-5.3-free",
        "mistral/mistral-medium-latest",
    ],
    "light": [
        # First choice: this is also the model backend/agents/tools.py's delegate_task hands
        # mechanical file-writing to (llm.models_for_tier("light")[0]) — fast, reliable, real
        # function-calling, so a heavy/slow-reasoning orchestrator model can plan once and let this
        # one do the actual write_file/verification legwork instead of burning its own slow
        # reasoning pass on every single tool round of a multi-file build.
        # 3.6 leads: the only Gemini model answering on every configured key (2.5 is gone for newer
        # keys, 3.7 regularly returns 503 "high demand"), and the fastest. Planning takes its
        # candidates from the front of this list, so this is also what makes the planner use Gemini.
        "gemini/gemini-3.6-flash",
        "gemini/gemini-3.7-flash",
        "groq/openai/gpt-oss-20b",
        "gemini/gemini-2.5-flash",
        "openrouter/nvidia/nemotron-3.5-lightning:free",
        "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0",
        # Last resort in this tier: local model, no rate limit and no cost, but an 8B quant is the
        # weakest reasoner here - only reached if every hosted light-tier option is unavailable.
        "ollama_chat/josiefied-qwen3:latest",
    ],
}

# Bounded round-robin failover set, consulted by backend/agents/jobs.py's run_round when a rate
# limit exhausts a model's own key failover mid-round. Deliberately a curated SUBSET of a tier's
# full _TIER_ORDER: DeepSeek/Nemotron/GPT-OSS-120B stay in the heavy tier for manual selection
# (model_for_task/models_for_task still see them) but aren't looped into automatic failover -
# their catalog churn and inconsistent tool-calling make them a worse bet than cycling straight
# back to Gemini once real time has passed and a rate-limited window may have rolled. A tier with
# no entry here falls back to the old linear-until-exhausted behavior over its full _TIER_ORDER.
_FAILOVER_RING: dict[str, list[str]] = {
    # Deliberately GLM-only, with no Gemini tail: an ultra_heavy orchestrator that fell back to
    # Gemini would start eating the exact quota its own delegated workers depend on. When every GLM
    # key is spent the ring wraps back to the first one (jobs.py's run_round resets the key indices
    # on wrap, so a new lap genuinely retries each key after real time has passed) rather than
    # migrating the orchestrator onto the worker pool.
    "ultra_heavy": [
        "tokenrouter/z-ai/glm-5.3-free",
    ],
    "heavy": [
        "gemini/gemini-3.8-flash",
        "gemini/gemini-3.7-flash",
        "tokenrouter/z-ai/glm-5.3-free",
    ],
}

# Worker ring for delegated authoring — the models a heavy orchestrating model hands actual
# file-writing to (see tools.py's delegate_build). Gemini first: fast, real function calling, and
# critically each entry is an INDEPENDENT quota bucket. Google meters per model per key/project, and
# _active_key_index already rotates keys within a single model, so the effective worker budget is
# (models x keys) separate limits rather than one shared pool — exhausting gemini-3.7's keys leaves
# 3.8's and 2.5's completely untouched. The non-Gemini tail is a genuine last resort: without it a
# fully-rate-limited Gemini would dead-end delegation and push every write back onto the expensive
# orchestrator, which is the exact failure this whole path exists to avoid.
# Gemini-only, and that exclusion is the design rather than an oversight. An ultra_heavy (GLM)
# orchestrator never spends Gemini quota itself, so this ring owns the whole Gemini budget:
# every model here x its own configured keys is a separate bucket, and the ring ROUND-ROBINS
# (wraps, with the models' key indices reset each lap — see _WorkerSession) instead of walking
# once and dead-ending. Adding a non-Gemini tail would mean a worker silently drifting onto a
# different model family mid-build, which is how one codebase ended up with several mutually
# incompatible conventions; staying in-family keeps output style predictable.
# Order is 3.8, then 3.7, then 2.5 deliberately (strongest first). Combined with per-model key
# rotation this produces one cycle: 3.8[key1..keyN] -> 3.7[key1..keyN] -> 2.5[key1..keyN] -> wrap
# to 3.8[key1]. Level 1 (keys, inside _with_key_failover) exhausts every key of the current model
# before level 2 (this ring) advances the model. On Google's free tier each (model, key) bucket is
# 20 requests PER DAY (quota "GenerateRequestsPerDayPerProjectPerModel-FreeTier", seen live on
# 2026-09-11), not a per-minute window, so an exhausted bucket stays exhausted until midnight
# Pacific — the ring's value is breadth (models x keys), not waiting for a window to roll.
#
# Some keys can't serve some models at all: gemini-2.5-flash answers 404 "no longer available to
# new users" on every key except the first. _MODEL_KEY_LIMIT stops rotation from wasting calls there.
_MODEL_KEY_LIMIT: dict[str, int] = {
    "gemini/gemini-2.5-flash": 1,
}
#
# 2.5-flash used to be deliberately excluded ("the two-model rotation is the requested shape") —
# reversed after a real, observed failure: _WorkerSession.complete() used to only rotate on a
# CLASSIFIED rate limit, so a genuine (non-rate-limit) provider error from 3.8-flash mid-build hit
# _delegate_build's outer except, gave up immediately, and told the caller "write the files
# yourself" with 3.7 and every configured key still completely untouched — the two-model ring was
# never even the bottleneck that failure hit. complete() now rotates on ANY exception (see its
# docstring), which makes a wider ring actually pay off: a bad response from 3.8 now falls through
# to 3.7, then 2.5, before the whole worker pool is considered exhausted.
_WORKER_RING: list[str] = [
    "gemini/gemini-3.8-flash",
    "gemini/gemini-3.7-flash",
    "gemini/gemini-3.6-flash",
    "gemini/gemini-2.5-flash",
]

# High-stakes generation routes to heavy (GLM); low-stakes to light.
TASK_TIER: dict[str, str] = {
    # The orchestrating roles route to ultra_heavy (GLM) rather than heavy (Gemini-first) so the
    # orchestrator and its own delegated workers draw from disjoint quota. A Gemini orchestrator
    # delegating to Gemini workers competes with itself for the same buckets — the more it
    # delegates, the faster it rate-limits the very pool doing the work. model_for_task already
    # falls through to heavy/balanced/light if no GLM key is configured, so this is a preference,
    # not a hard dependency.
    "architecture": "ultra_heavy",
    "graph": "ultra_heavy",
    "reasoning": "ultra_heavy",
    "planner": "ultra_heavy",
    "research": "heavy",
    "coder": "ultra_heavy",
    "docs": "light",
    "summary": "light",
    "retrieval": "light",
    # "chat" decides default_model, which is what the UI model picker starts on — and the picker's
    # value is what /chat/agent actually runs a job with, overriding tier routing entirely. So while
    # architecture/coder/planner all said ultra_heavy, every real job still ran on Gemini, because
    # the picker defaulted here. Pointing chat at ultra_heavy is what makes GLM the orchestrator in
    # practice rather than only on paper, and it restores the intended split: GLM orchestrates,
    # Gemini's separate quota serves the delegated workers (_WORKER_RING).
    "chat": "ultra_heavy",
}

DEFAULT_CONTEXT = 32768

# Per-model (calls, window_seconds) caps for providers with a hard rate limit — sleep to stay under
# it instead of eating a 429. Model not listed here means unthrottled.
_RATE_LIMITS: dict[str, tuple[int, float]] = {
    "tokenrouter/z-ai/glm-5.3-free": (8, 60.0),
    # Gemini free tier meters ~5 requests/min PER MODEL PER PROJECT. Throttling proactively here is
    # strictly better than discovering the limit as a 429: the 429 costs a full network round-trip
    # and burns a rotation step, whereas waiting ~12s reuses the same bucket. Crucially these
    # buckets are per (model, key) — see _RateLimiter.wait — because four keys are four separate
    # projects; metering them as one model-wide bucket would throw away 75% of the configured
    # capacity to enforce a limit that does not actually exist.
    "gemini/gemini-3.8-flash": (5, 60.0),
    "gemini/gemini-3.7-flash": (5, 60.0),
    "gemini/gemini-2.5-flash": (5, 60.0),
}


def is_rate_limit_error(exc: BaseException) -> bool:
    """True for a genuine rate limit - whether raised directly as litellm.RateLimitError, or
    wrapped in litellm.MidStreamFallbackError. The latter is a REAL, observed failure mode: a 429
    that surfaces after streaming has already started gets wrapped by litellm as
    MidStreamFallbackError, which subclasses ServiceUnavailableError, NOT RateLimitError - so a
    bare `except litellm.RateLimitError` never catches it, silently skipping key failover entirely
    (this is exactly why a real Gemini rate limit hit didn't fail over to GEMINI_API_KEY_2: the
    wrapped exception type didn't match). Access the wrapper's `.original_exception` defensively
    (getattr, not an isinstance import of the wrapper class itself) so a future litellm version
    renaming or restructuring that class degrades to "no failover" instead of an ImportError/crash."""
    if isinstance(exc, litellm.RateLimitError):
        return True
    original = getattr(exc, "original_exception", None)
    return isinstance(original, litellm.RateLimitError)


class _RateLimiter:
    """Sliding-window token bucket, one deque of call timestamps per (model, key).

    Bucketing by key as well as model is what makes multi-key rotation worth anything under a
    per-project quota: four Gemini keys are four separate projects, each with its own 5/min
    allowance. A single model-wide bucket would serialise all four behind one limit and discard
    three quarters of the configured capacity while enforcing a ceiling that no provider imposes.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: dict[str, collections.deque] = {}

    def wait(self, model: str, key_index: int = 0) -> None:
        limit = _RATE_LIMITS.get(model)
        if limit is None:
            return
        bucket = f"{model}#{key_index}"
        max_calls, window = limit
        while True:
            with self._lock:
                dq = self._calls.setdefault(bucket, collections.deque())
                now = time.monotonic()
                while dq and now - dq[0] >= window:
                    dq.popleft()
                if len(dq) < max_calls:
                    dq.append(now)
                    return
                sleep_for = window - (now - dq[0])
            time.sleep(max(sleep_for, 0.05))


class CancellableStream:
    """A provider stream that can actually be stopped from another thread.

    The consumer of a stream runs on the job thread; the producer that pulls from it runs on a
    watchdog thread (backend/agents/jobs.py `_stream_with_watchdog`). When a round is cut — a
    generation budget, the wall clock, a user cancel — the consumer needs to stop the provider, and
    it is not the thread inside the iteration.

    Calling `close()` on the generator itself does not work, and failed silently. Python raises
    `ValueError: generator already executing` when a generator is closed while another thread is
    inside it, and that was swallowed by a best-effort `except Exception`. So every cut left the
    producer blocked on a live HTTP response with the provider still generating and still billing,
    until it happened to finish on its own. Orphaned generation was the normal case, not an edge.

    What can be closed safely from another thread is litellm's own stream wrapper. This holds a
    reference to whichever one is currently live — it changes on key failover — and closes that.
    """

    __slots__ = ("_gen", "_live")

    def __init__(self, gen, live: dict):
        self._gen = gen
        self._live = live

    def __iter__(self):
        return self._gen

    def __next__(self):
        return next(self._gen)

    def close(self) -> None:
        """Tear down the underlying provider response. Safe to call from any thread, more than
        once, and while the producer is mid-iteration — which is the only situation it is ever
        called in."""
        stream = self._live.get("stream")
        if stream is None:
            return
        for method in ("close", "cancel"):
            fn = getattr(stream, method, None)
            if callable(fn):
                try:
                    fn()
                    return
                except Exception:  # noqa: BLE001 - already finished, or the provider dislikes it
                    continue
        # No teardown method: drop the reference so the socket is collected rather than pinned for
        # the lifetime of the process.
        self._live["stream"] = None


class LLMClient:
    def __init__(self) -> None:
        overrides_env = os.getenv("AGENT_MODEL_OVERRIDES", "{}")
        try:
            self.agent_overrides: dict[str, str] = json.loads(overrides_env)
        except json.JSONDecodeError:
            self.agent_overrides = {}

        # litellm reads GROQ_API_KEY / GEMINI_API_KEY from env; NVIDIA needs NVIDIA_NIM_API_KEY.
        if os.getenv("NVIDIA_API_KEY"):
            os.environ.setdefault("NVIDIA_NIM_API_KEY", os.environ["NVIDIA_API_KEY"])
        # Ollama has no API key - default to the local daemon so it's available out of the box.
        # Set OLLAMA_API_BASE="" (empty, not unset) in .env to disable it on a machine without one.
        os.environ.setdefault("OLLAMA_API_BASE", "http://localhost:11434")

        self.available: list[str] = [
            model
            for model, (_l, _c, _t, provider) in MODEL_REGISTRY.items()
            if os.getenv(_PROVIDER_ENV[provider])
        ]

        configured = os.getenv("LLM_DEFAULT_MODEL") or os.getenv("NVIDIA_NIM_DEFAULT_MODEL")
        if configured and configured in MODEL_REGISTRY and configured in self.available:
            self.default_model = configured
        else:
            self.default_model = self.model_for_task("chat")

        self.provider = MODEL_REGISTRY.get(self.default_model, (None, None, None, "nvidia"))[3]
        self.usage = UsageTracker()
        self._limiter = _RateLimiter()
        # Set by whoever owns an event stream (backend/agents/jobs.py per job) to surface key
        # rotations to the UI. Left None outside a job so nothing depends on it being installed.
        self._on_key_switch: Callable[[str, str], None] | None = None

        # Per-provider key failover: PROVIDER_ENV_VAR_2, _3, ... are independent accounts (their
        # own separate quota, not a pool split from the primary) — a rate limit on the active key
        # fails over to the next one, sticky (stays there; a quota that's exhausted for the rest
        # of the window won't magically un-exhaust by flipping back). Only providers with more
        # than one key configured actually use this — everyone else keeps today's behavior
        # (litellm reads its usual single env var itself, _kwargs never overrides api_key).
        #
        # The rotation index is keyed by MODEL, not provider, even though the key list itself is
        # shared per provider — Google (and most providers) track rate-limit quota per model per
        # key/project, not pooled across a provider's models. Keying the index by provider would
        # mean a gemini-3.8-flash rate limit advances the shared index, so a later gemini-3.7-flash
        # attempt starts on key 2 too — skipping key 1's entirely separate 3.7 quota. Per-model
        # indices (each starting fresh at key 0 via .get(model, 0)) give the real intended order:
        # key1/3.8 → key2/3.8 → key1/3.7 → key2/3.7 → ... before ever falling to another provider.
        self._provider_keys: dict[str, list[str]] = {}
        self._active_key_index: dict[str, int] = {}
        for provider, env_var in _PROVIDER_ENV.items():
            keys = [v for v in [os.getenv(env_var)] if v]
            n = 2
            while True:
                extra = os.getenv(f"{env_var}_{n}")
                if not extra:
                    break
                keys.append(extra)
                n += 1
            if len(keys) > 1:
                self._provider_keys[provider] = keys

        logger.info("LLM ready: default=%s available=%s", self.default_model, self.available)

    # --- routing ------------------------------------------------------------
    def model_for_task(self, task: str) -> str:
        tier = TASK_TIER.get(task, "balanced")
        for candidate in _TIER_ORDER.get(tier, []):
            if candidate in self.available:
                return candidate
        for tier_order in ("balanced", "light", "heavy"):
            for candidate in _TIER_ORDER[tier_order]:
                if candidate in self.available:
                    return candidate
        # Last resort: never hand back a "content" tier model here (e.g. qwen-plus-character) even
        # if it's the only thing left in self.available - it has no function/tool-calling support,
        # so using it as a job's orchestrating model would break on the first tool call.
        orchestrator_candidates = [
            m for m in self.available if self.tier_of(m) in ("ultra_heavy", "heavy", "balanced", "light")
        ]
        return orchestrator_candidates[0] if orchestrator_candidates else "nvidia_nim/meta/llama-3.1-8b-instruct"

    def models_for_task(self, task: str) -> list[str]:
        """All available models for a task's tier, in priority order — for callers that want to
        retry against the next candidate on a runtime failure (e.g. a rate-limited provider)."""
        tier = TASK_TIER.get(task, "balanced")
        return [c for c in _TIER_ORDER.get(tier, []) if c in self.available]

    def tier_of(self, model: str) -> str | None:
        entry = MODEL_REGISTRY.get(model)
        return entry[2] if entry else None

    def models_for_tier(self, tier: str) -> list[str]:
        """Like models_for_task, but keyed directly off a tier name — for a caller that already
        knows which model just failed and wants its peers, not a task->tier lookup."""
        return [c for c in _TIER_ORDER.get(tier, []) if c in self.available]

    def reset_keys(self, models: list[str]) -> None:
        """Clear the sticky key rotation for `models`, so the next call starts again at key 1.

        Only meaningful when a ROUND-ROBIN ring wraps to a new lap. Sticky rotation is correct
        within a lap (a bucket that just returned 429 will still be exhausted a second later), but a
        full lap of a multi-model ring takes real network time, and without this a wrapped ring
        would retry only each model's LAST key forever while its earlier keys — separate buckets
        that may well have refilled — were never touched again for the life of the job."""
        for model in models:
            self._active_key_index.pop(model, None)

    def describe_active(self, model: str) -> str:
        """Human label for the model AND which of its keys is live — e.g. 'Gemini 3.8 Flash #2'.

        Exists because a bare model id is ambiguous once multi-key rotation is in play: four keys on
        one model are four independent quota buckets, so 'switched to Gemini 3.8' is unactionable
        when the interesting fact is which of the four it moved to. The '#n' suffix only appears
        when more than one key is configured, so single-key setups stay uncluttered."""
        label = MODEL_REGISTRY.get(model, (model,))[0]
        keys = self._provider_keys.get(self._provider_of(model))
        if not keys or len(keys) < 2:
            return label
        return f"{label} #{self._active_key_index.get(model, 0) + 1}"

    def worker_ring(self) -> list[str]:
        """Ordered, availability-filtered worker models for delegated authoring (see _WORKER_RING).
        The caller rotates to the next entry when the current one's own per-key rotation is
        exhausted, giving delegation a (models x keys) budget instead of a single model's."""
        return [m for m in _WORKER_RING if m in self.available]

    def failover_ring(self, tier: str) -> list[str]:
        """Bounded round-robin failover candidates for a tier (see _FAILOVER_RING) — a curated
        subset of models_for_tier's full list. Empty for a tier with no ring defined; the caller
        (jobs.py's run_round) treats that as "use the old linear-until-exhausted behavior over the
        full tier instead"."""
        return [c for c in _FAILOVER_RING.get(tier, []) if c in self.available]

    def context_window(self, model: str) -> int:
        return MODEL_REGISTRY.get(model, ("", DEFAULT_CONTEXT, "", ""))[1]

    def available_models(self) -> list[dict[str, Any]]:
        out = []
        for model in self.available:
            label, ctx, tier, provider = MODEL_REGISTRY[model]
            out.append({
                "id": model,
                "label": label,
                "provider": provider,
                "context_window": ctx,
                "tier": tier,
                "default": model == self.default_model,
            })
        return out

    # --- calling ------------------------------------------------------------
    def _provider_of(self, model: str) -> str:
        entry = MODEL_REGISTRY.get(model)
        if entry:
            return entry[3]
        # Not in the registry — derive from the id's own prefix (e.g. a zai/ model reachable only
        # by name) so key rotation still resolves that provider's real key list instead of silently
        # falling back to nvidia's and handing out the wrong key.
        prefix = model.split("/", 1)[0]
        return prefix if prefix in _PROVIDER_ENV else "nvidia"

    def _current_key(self, model: str) -> str | None:
        keys = self._provider_keys.get(self._provider_of(model))
        if not keys:
            return None
        return keys[self._active_key_index.get(model, 0)]

    def _advance_key(self, model: str) -> bool:
        """Sticky failover to this MODEL's next configured key (see __init__ for why the index is
        per-model, not per-provider, despite the key list itself being shared per provider).
        Returns False (nothing left to try) once every configured key has been exhausted for this
        specific model — the caller re-raises at that point so backend/agents/jobs.py's own
        model-switch fallback becomes the next resort."""
        keys = self._provider_keys.get(self._provider_of(model))
        if not keys:
            return False
        idx = self._active_key_index.get(model, 0)
        if idx + 1 >= min(len(keys), _MODEL_KEY_LIMIT.get(model, len(keys))):
            return False
        self._active_key_index[model] = idx + 1
        logger.warning("model %s: key %d rate-limited, failing over to key %d", model, idx + 1, idx + 2)
        # Key rotation happens deep inside a streaming call, far from anything holding a job handle,
        # so a callback is the only way it can reach the event stream. Without this a switch from
        # key 1 to key 2 is completely invisible: the model id never changes, so the UI shows the
        # same thing while an entirely different quota bucket is doing the work — exactly the
        # ambiguity that makes "why did it slow down at round 40?" unanswerable after the fact.
        if self._on_key_switch is not None:
            try:
                self._on_key_switch(model, self.describe_active(model))
            except Exception:  # noqa: BLE001 - telemetry must never break a live failover
                pass
        return True

    def _kwargs(self, model: str) -> dict[str, Any]:
        # z.ai and TokenRouter are OpenAI-compatible; route them through litellm's openai provider
        # with their own base URL. The api_key still goes through _current_key so multi-key rotation
        # (TOKENROUTER_API_KEY_2, _3, ... — independent accounts, independent quota) works for them
        # exactly like every other provider. These two branches used to hardcode os.getenv(...) and
        # return early, silently bypassing the entire rotation mechanism: adding a second GLM key
        # did literally nothing, and a single key's quota was the hard ceiling for every GLM call.
        if model.startswith("zai/") or model.startswith("tokenrouter/"):
            is_zai = model.startswith("zai/")
            provider = "zai" if is_zai else "tokenrouter"
            return {
                "model": "openai/" + model.split("/", 1)[1],
                "api_base": ZAI_API_BASE if is_zai else TOKENROUTER_API_BASE,
                "api_key": self._current_key(model) or os.getenv(_PROVIDER_ENV[provider], ""),
            }
        kwargs: dict[str, Any] = {"model": model}
        key = self._current_key(model)
        if key:  # only set for providers with more than one key configured — see __init__
            kwargs["api_key"] = key
        return kwargs

    def _record_usage(self, agent: str, model: str, response: Any, *, task_intent: str | None = None) -> dict[str, int]:
        usage_obj = getattr(response, "usage", None)
        prompt = int(getattr(usage_obj, "prompt_tokens", 0) or 0) if usage_obj else 0
        completion = int(getattr(usage_obj, "completion_tokens", 0) or 0) if usage_obj else 0
        # Reasoning-capable models (Gemini 2.5, GLM thinking mode) bill internal "thinking" tokens
        # as part of completion_tokens with no visible text — break it out so a tiny visible answer
        # doesn't look like a mystery 500-token response.
        details = getattr(usage_obj, "completion_tokens_details", None) if usage_obj else None
        reasoning = int(getattr(details, "reasoning_tokens", 0) or 0) if details else 0
        provider = MODEL_REGISTRY.get(model, ("", 0, "", "unknown"))[3]
        self.usage.record(
            agent=agent, model=model, provider=provider,
            prompt_tokens=prompt, completion_tokens=completion, reasoning_tokens=reasoning,
            task_intent=task_intent,
        )
        return {"prompt_tokens": prompt, "completion_tokens": completion}

    def _with_key_failover(self, model: str, call: Callable[[], Any]) -> Any:
        """Runs `call()` — a thunk that makes the actual litellm request using today's active key
        for model's provider. On a rate limit (see is_rate_limit_error — covers both a bare
        RateLimitError and one wrapped in MidStreamFallbackError), fails over to the next
        configured key (see __init__) and retries the SAME call from scratch — safe here because
        this path is only for non-streaming calls, where "from scratch" and "the original attempt"
        are identical from the caller's point of view (no partial output could have escaped already)."""
        while True:
            try:
                return call()
            except Exception as exc:
                if not is_rate_limit_error(exc) or not self._advance_key(model):
                    raise

    def complete(self, messages: list[dict], *, model: str | None = None, agent: str = "generate", **kwargs: Any) -> str:
        model = model or self.default_model
        self._limiter.wait(model, self._active_key_index.get(model, 0))
        response = self._with_key_failover(
            model, lambda: litellm.completion(messages=messages, **self._kwargs(model), **kwargs),
        )
        self._record_usage(agent, model, response)
        return response.choices[0].message.content or ""

    def stream(self, model: str, messages: list[dict], **kwargs: Any) -> Iterator[Any]:
        model = model or self.default_model
        self._limiter.wait(model, self._active_key_index.get(model, 0))
        # `live` is shared with the generator below, which records whichever provider stream is
        # currently open into it. That is what makes cancellation reach the provider instead of
        # stopping at a generator that cannot be closed from another thread.
        live: dict[str, Any] = {"stream": None}
        return CancellableStream(
            self._stream_with_key_failover(model, messages, _live=live, **kwargs), live)

    def _stream_with_key_failover(
        self, model: str, messages: list[dict], _live: dict | None = None, **kwargs: Any,
    ) -> Iterator[Any]:
        """Same idea as _with_key_failover, but a stream can't be silently retried once the caller
        has already seen real output from it — that would hand back duplicated/garbled content.
        So the rule here is: rate-limited before a single chunk went out → nothing was lost, retry
        transparently on the next key, the caller never even sees an exception. Rate-limited after
        chunks were already yielded → re-raise instead of swallowing it; backend/agents/jobs.py's
        own stall-recovery already preserves that partial content and asks the model to continue,
        which is the correct way to hand off "half-finished work," not a second layer of it here.
        Catches Exception broadly (not just litellm.RateLimitError) and filters with
        is_rate_limit_error — a REAL observed rate limit arrived wrapped in
        litellm.MidStreamFallbackError, a different class the narrower except silently let through
        with zero failover."""
        while True:
            emitted = False
            try:
                provider_stream = litellm.completion(
                    messages=messages, stream=True, **self._kwargs(model), **kwargs)
                if _live is not None:
                    # Publish the live wrapper so CancellableStream.close() can tear it down. Set on
                    # every attempt, because key failover replaces it.
                    _live["stream"] = provider_stream
                for chunk in provider_stream:
                    emitted = True
                    yield chunk
                return
            except Exception as exc:
                if not is_rate_limit_error(exc) or emitted or not self._advance_key(model):
                    raise

    def record_usage(self, agent: str, model: str, response: Any, *, task_intent: str | None = None) -> dict[str, int]:
        """Public entry point for callers that assembled their own response (e.g. from raw stream
        chunks via litellm.stream_chunk_builder) and need it logged the same way as complete()."""
        return self._record_usage(agent, model, response, task_intent=task_intent)

    def complete_message(
        self, messages: list[dict], *, model: str | None = None, tools: list | None = None, agent: str = "chat",
    ) -> tuple[Any, dict[str, int]]:
        """Non-streaming completion returning (raw message [may carry tool_calls], real usage dict)."""
        model = model or self.default_model
        extra: dict[str, Any] = {}
        if tools:
            extra = {"tools": tools, "tool_choice": "auto"}
        self._limiter.wait(model, self._active_key_index.get(model, 0))
        response = self._with_key_failover(
            model, lambda: litellm.completion(messages=messages, **self._kwargs(model), **extra),
        )
        usage = self._record_usage(agent, model, response)
        return response.choices[0].message, usage

    def generate(self, agent_role: str, prompt: str, *, task: str | None = None, **kwargs: Any) -> str:
        """Back-compat single-prompt call. Routes by agent_role/task unless overridden."""
        model = self.agent_overrides.get(agent_role) or self.model_for_task(task or agent_role)
        return self.complete([{"role": "user", "content": prompt}], model=model, agent=agent_role, **kwargs)
