"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Paperclip, ArrowUp, ChevronDown, Square, X, GitBranch, Plus, Trash2, Wrench, BrainCircuit, Copy, Check, RotateCcw, Users, ArrowLeftRight } from "lucide-react";
import {
  api,
  cancelAgentJob,
  continueAgentJob,
  startAgentJob,
  streamChat,
  subscribeAgentJob,
  type ChatMessage,
  type ChatModel,
  type ImpactResult,
  type PlanSnapshot,
  type QuorumRunResult,
  type StreamHandlers,
} from "@/lib/api";
import { Mark } from "@/components/shell/Mark";
import { EASE_OUT } from "@/components/ui/primitives";
import { ImpactCard } from "@/components/chat/ImpactCard";
import { TaskPlanCard } from "@/components/chat/TaskPlanCard";
import { RepoDialog } from "@/components/chat/RepoDialog";
import { DotsLoader } from "@/components/ui/DotsLoader";
import { ThinkingLoader } from "@/components/ui/ThinkingLoader";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { useRepoStore } from "@/lib/repo-store";
import { useChatStore, type Conversation, type StoredTurn } from "@/lib/chat-store";

interface Attachment {
  name: string;
  content: string;
}
// Local turn adds the transient `analyzing` flag that is never persisted.
type Turn = StoredTurn & { analyzing?: boolean };

const approxTokens = (s: string) => Math.max(0, Math.ceil(s.length / 4));

function formatTokenCount(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

// Sliding-window cap on how much prior conversation gets resent to the model on every message —
// see docs/token_usage_investigation.md. Turn-count cap (not token-budget) per the second opinion's
// recommendation to start simple; the full untrimmed history still lives in the local store/UI,
// this only bounds what's sent to the API.
const MAX_HISTORY_MESSAGES = 20;

// --- Smart routing: only true greetings/acks skip tools + repo context ---
// Tool-calling patterns: file/code ops, project creation, debugging, web search, design work.
// prettier-ignore
const _TOOL_TRIGGERS = /\b(create|build|scaffold|generate|write|make|set.?up|implement|edit|modify|update|change|fix|refactor|rename|delete|remove|drop|replace|patch|migrate|read|open|show|list|find|search|grep|cat|deploy|run|execute|test|lint|npm|pip|yarn|pnpm|docker|debug|trace|investigate|profile|design|redesign|ui|ux|landing|page|component|layout|style|css|tailwind|animation|google|look.?up|tavily|project|app|website|tool|cli|api|server|endpoint|route|function|class|module|hook|util|tree|dependency|dependencies|import|depend|symbol|shell|bash|command|screenshot|browser|git|commit|branch|diff|status|patch|convention|metadata|outline|reference|hierarchy|accessibility|visual|consistency|token|server|dev.?server)\b/i;
// Pure social/ack messages with no code-question intent — matched against the WHOLE trimmed
// message (not just a prefix), so a real question that happens to start with "thanks" or "ok"
// ("thanks, but why is the retry logic broken?") isn't misclassified as small talk.
// prettier-ignore
const _GREETING_ONLY = /^\s*(hi|hello|hey|yo|sup|thanks|thank.?you|ok|okay|yes|no|sure|cool|nice|bye|good.?bye|good\s+(morning|afternoon|evening)|got.?it|sounds.?good|perfect|great|awesome)[!.,\s]*$/i;

/** True if the message needs tool-calling (file ops, code changes, project creation, etc.).
 *
 *  False only for pure greetings/acks and near-empty fragments — routed through /chat/stream to
 *  avoid paying for tool schemas (~1.25K tokens) and repo context (~5K tokens). Everything else,
 *  INCLUDING plain questions ("why does the login page look broken", "what does the auth
 *  middleware do", "is there a bug in the retry logic"), defaults to tools now. The previous
 *  version short-circuited to false for any message starting with a question word (what/how/why/
 *  is there/...) before ever checking for a concrete trigger — which routed exactly the questions
 *  that most need the model to go check the real code to the endpoint structurally incapable of
 *  doing so. A false negative here (skipping tools when the answer needed the real code) is worse
 *  than the extra tokens a generic question's unused tool schemas cost. */
function needsTools(text: string, history: ChatMessage[]): boolean {
  const trimmed = text.trim().toLowerCase();
  // Any tool-relevant keyword anywhere in the message → tools. Checked first so a question that
  // opens with why/what/how but names something concrete isn't short-circuited below before this
  // ever runs.
  if (_TOOL_TRIGGERS.test(trimmed)) return true;
  // Pure greeting/ack (the whole message, not just a prefix) → no tools.
  if (_GREETING_ONLY.test(trimmed)) return false;
  // One or two content-free words with no trigger ("nope", "maybe later") → no tools.
  if (trimmed.split(/\s+/).length <= 2) return false;
  // Follow-up to a tool-using turn → tools, even if this message alone looks conversational.
  const recentRoles = history.slice(-4).map((m) => m.role);
  if (recentRoles.includes("assistant") && history.some((m) => m.role === "user" && _TOOL_TRIGGERS.test(m.content.toLowerCase()))) return true;
  // Default: a substantive message that isn't a greeting — ground it in the real repo rather than
  // let the model answer from assumption.
  return true;
}

const DESIGN_TOOL_HINT =
  "Before writing or redesigning any frontend/UI code (HTML, CSS, React, Tailwind), call the " +
  "get_design_guidance tool first to load a real design system's rules — do not freestyle a look.";

// A change request is where the blast radius must run before anything else.
const CHANGE_INTENT =
  /\b(change|modify|refactor|add|remove|delete|rename|update|rewrite|replace|migrat\w*|introduce|drop|edit|implement|extend|patch|deprecate)\b/i;

function greeting() {
  const h = new Date().getHours();
  const part = h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
  return `Good ${part}, Rohit.`;
}

export default function ChatPage() {
  const qc = useQueryClient();
  const activeRepo = useRepoStore((s) => s.activeRepo);
  const setActiveRepo = useRepoStore((s) => s.setActiveRepo);
  const [repoDialogOpen, setRepoDialogOpen] = useState(false);

  const modelsQuery = useQuery({ queryKey: ["chat-models"], queryFn: api.chatModels });
  const activityQuery = useQuery({ queryKey: ["events", "recent"], queryFn: () => api.events(6) });

  // Graph-anchored grounding: resolves the actual question to specific symbols/files and their
  // immediate neighbors (falling back to generic repo-digest facts only when nothing resolves),
  // instead of dumping the same flat top-12 memory records into every turn regardless of relevance.
  async function buildRepoContext(query: string): Promise<string> {
    let items: Awaited<ReturnType<typeof api.contextFor>> = [];
    try {
      items = await api.contextFor(activeRepo, query);
    } catch {
      return "";
    }
    if (items.length === 0) return "";
    const lines = items
      .map((it) => (it.content ? `- [${it.kind}] ${it.title}: ${it.content}` : `- ${it.title}`))
      .join("\n");
    return (
      `You are working on the repository '${activeRepo}'. The facts below are a snapshot from when ` +
      `the repo was last analyzed — they can be stale (files/directories may have been added, ` +
      `moved, or deleted since). Do NOT invent features, modules, or use-cases these facts don't ` +
      `support. But for anything about CURRENT file/directory existence or structure — especially ` +
      `before reading, editing, or deleting something — call list_directory or search_code to check ` +
      `the live filesystem instead of trusting this snapshot; don't answer "it doesn't exist" from ` +
      `memory alone.\n${lines}`
    );
  }
  // Persistent conversations — survive tab switches and reloads.
  const activeId = useChatStore((s) => s.activeId);
  const conversations = useChatStore((s) => s.conversations);
  const order = useChatStore((s) => s.order);
  const ensureActive = useChatStore((s) => s.ensureActive);
  const setActiveConv = useChatStore((s) => s.setActive);
  const newConversation = useChatStore((s) => s.newConversation);
  const removeConv = useChatStore((s) => s.remove);
  const storeSetTurns = useChatStore((s) => s.setTurns);
  const storeSetModel = useChatStore((s) => s.setModel);
  const storeSetTitle = useChatStore((s) => s.setTitle);
  const storeAddTokens = useChatStore((s) => s.addTokens);
  const storeSetJobId = useChatStore((s) => s.setJobId);
  const jobIdRef = useRef<string | null>(null);

  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [model, setModel] = useState<ChatModel | null>(null);
  const [quorumMode, setQuorumMode] = useState(false);
  const [liveImpact, setLiveImpact] = useState<ImpactResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const turnsRef = useRef<Turn[]>(turns);
  turnsRef.current = turns;
  const skipSaveRef = useRef(false);

  useEffect(() => {
    ensureActive();
  }, [ensureActive]);

  // Live blast-radius preview: the existing /agents/impact check only ever ran after send, gated
  // behind CHANGE_INTENT — the user found out how risky a change was only after already committing
  // to sending it. Debounced so it doesn't fire on every keystroke; cleared whenever the draft no
  // longer looks like a change request or drops below a length worth bothering the backend for.
  useEffect(() => {
    const text = input.trim();
    if (!text || text.length < 12 || !CHANGE_INTENT.test(text)) {
      setLiveImpact(null);
      return;
    }
    let cancelled = false;
    const handle = setTimeout(async () => {
      try {
        const res = await api.impact(text, activeRepo);
        // Same rule as the send-time gate below: show the live preview only when there is a real
        // consequence to preview. "0 downstream affected" is not information worth a banner.
        if (!cancelled) setLiveImpact(res.resolved && res.affected_count > 0 ? res : null);
      } catch {
        if (!cancelled) setLiveImpact(null);
      }
    }, 600);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [input, activeRepo]);

  // Load a conversation's turns when it becomes active.
  useEffect(() => {
    if (!activeId) return;
    const conv = useChatStore.getState().conversations[activeId];
    skipSaveRef.current = true;
    setTurns((conv?.turns as Turn[]) ?? []);
  }, [activeId]);

  // Reattach to an agent job that was left running when this conversation was last visited — the
  // job keeps working on the backend regardless of tab switches, navigation, or even a backend
  // restart (checkpointed to disk), so reopening the conversation should catch up on it rather than
  // silently showing a stale, incomplete response.
  useEffect(() => {
    if (!activeId || streaming) return;
    const jobId = useChatStore.getState().conversations[activeId]?.pendingJobId;
    if (!jobId) return;
    // Own controller per effect run (not the shared abortRef) so React StrictMode's dev-mode
    // double-invoke of this effect can't open two concurrent subscriptions to the same job: the
    // first run's cleanup aborts its controller before the second run starts its own.
    const controller = new AbortController();
    attachToJob(jobId, controller);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  // Persist turns when idle (not mid-stream), skipping the write right after hydration.
  useEffect(() => {
    if (streaming || !activeId) return;
    if (skipSaveRef.current) {
      skipSaveRef.current = false;
      return;
    }
    storeSetTurns(activeId, turns as StoredTurn[]);
  }, [turns, streaming, activeId, storeSetTurns]);

  // Persist on unmount (tab switch), even mid-stream. Never overwrite with empty — that would
  // clobber the stored conversation during React StrictMode's dev mount/unmount/remount.
  //
  // Also abort the local subscription reader here. Without this, navigating to a different
  // top-level page (Knowledge graph, Usage, ...) unmounts ChatPage but the in-flight
  // subscribeAgentJob/streamChat call keeps running as a "zombie" — its onDelta/onDone callbacks
  // still fire, but they update an unmounted component's dead state, so nothing ever gets
  // persisted, AND once it reaches onDone it clears the conversation's pendingJobId (thinking the
  // UI legitimately saw the result). That erases the exact signal the reattachment effect needs to
  // know there's a finished response to catch up on. Aborting here instead makes the backend job
  // (which is unaffected — it's detached, per jobs.py) the sole source of truth: pendingJobId stays
  // set until a live subscription actually finishes attached to a mounted component, and returning
  // to the conversation replays the full event log fresh via attachToJob.
  useEffect(
    () => () => {
      abortRef.current?.abort();
      const id = useChatStore.getState().activeId;
      if (id && turnsRef.current.length > 0) {
        useChatStore.getState().setTurns(id, turnsRef.current as StoredTurn[]);
      }
    },
    [],
  );

  // Resolve the selected model per conversation, else the default.
  useEffect(() => {
    const models = modelsQuery.data;
    if (!models?.length) return;
    const conv = activeId ? conversations[activeId] : null;
    const resolved =
      (conv?.modelId && models.find((m) => m.id === conv.modelId)) ||
      models.find((m) => m.default) ||
      models[0];
    setModel(resolved);
  }, [activeId, conversations, modelsQuery.data]);

  const started = turns.length > 0;
  const contextWindow = model?.context_window ?? 8192;
  const usedTokens = useMemo(
    () => turns.reduce((n, t) => n + approxTokens(t.content ?? ""), 0) + approxTokens(input),
    [turns, input],
  );
  const usedPct = Math.min(100, (usedTokens / contextWindow) * 100);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  function handleModel(m: ChatModel) {
    setModel(m);
    if (activeId) storeSetModel(activeId, m.id);
  }

  // A stream left running after the user navigates away (new chat / switch conversation) used to
  // keep delivering tool-call/delta events into whatever conversation happened to be active by the
  // time they arrived — corrupting an unrelated later conversation with the old request's leftover
  // work. Cancel it outright instead of letting it complete in the background.
  function abortActiveStream() {
    abortRef.current?.abort();
    abortRef.current = null;
    // Deliberately NOT cancelling the backend job here — it's left running detached so it can be
    // reattached later via pendingJobId. Just stop tracking it locally so a subsequent Stop press
    // (now on a different, job-less conversation) can't reach back and cancel someone else's job.
    jobIdRef.current = null;
    setStreaming(false);
  }

  // Everything that reflects the active repository must refresh — used both when a repo is
  // explicitly loaded/created via the dialog, and when the agent creates a new project mid-chat
  // (create_project tool) and the backend tells the frontend to follow along via onRepoSwitched.
  function switchRepo(name: string) {
    setActiveRepo(name);
    for (const key of [
      ["memory-records"], ["memory-repos"], ["nodes"], ["edges", "all"],
      ["arch-trends"], ["repo-docs"], ["events", "recent"],
    ]) {
      qc.invalidateQueries({ queryKey: key });
    }
  }

  function startNewChat() {
    abortActiveStream();
    setInput("");
    setAttachments([]);
    newConversation(model?.id ?? null);
  }

  function selectConversation(id: string) {
    abortActiveStream();
    setActiveConv(id);
  }

  function buildHistory(outgoing: string): ChatMessage[] {
    const prior = turns
      .filter((t) => !t.error && !t.impact && !t.analyzing && typeof t.content === "string" && t.content)
      .map((t) => ({ role: t.role, content: t.content as string }))
      .slice(-MAX_HISTORY_MESSAGES); // sliding window — see token_usage_investigation.md
    return [...prior, { role: "user", content: outgoing }];
  }

  // Real jobs.py behavior: hitting the round budget emits an "error" event, then (usually within
  // microseconds, same background thread) auto-continues right past it — the SSE relay used to cut
  // the stream at that first "error" event regardless, which is the bug this whole feature fixes.
  // Now that continuation events DO reach the frontend, they must never get spliced/appended into
  // the stale error turn that onError already wrote (that turn's `content` is the error blurb, not
  // real output — mutating it would glue continued output onto the end of that message). Any
  // handler about to touch "the current turn" calls this first: if the trailing turn is an error,
  // it's stale — start a fresh one instead of resuscitating it.
  function startFreshIfErrored(prev: StoredTurn[]): StoredTurn[] {
    const next = [...prev];
    if (next.length && next[next.length - 1].error) next.push({ role: "assistant" });
    return next;
  }

  // Shared stream handlers (both /chat/stream and /chat/agent use the base set; the agent path
  // adds tool/repo/model-switch handlers on top). Factored out so a reattached subscription (job
  // kept running on the backend while this page was elsewhere) can reuse exactly the same wiring
  // a fresh send uses.
  function baseHandlers(controller: AbortController): StreamHandlers {
    return {
      signal: controller.signal,
      onThinking: (chunk: string) =>
        setTurns((prev) => {
          if (controller.signal.aborted) return prev;
          const next = startFreshIfErrored(prev);
          const last = next[next.length - 1];
          // Clear a stale error flag from an earlier failed attempt on this same turn (e.g. a
          // reattach whose first race lost to a transient error) — real data arriving means this
          // subscription is the one that matters now.
          next[next.length - 1] = { ...last, role: "assistant", error: false, thinking: (last.thinking ?? "") + chunk };
          return next;
        }),
      onStatus: (text: string) =>
        setTurns((prev) => {
          if (controller.signal.aborted) return prev;
          const next = startFreshIfErrored(prev);
          // A rotation is a durable fact about the run, not a transient progress label: it must
          // survive into the transcript so you can scroll back and see which model/key was live at
          // any point. Everything else stays as the ephemeral loader caption it should be.
          if (text.startsWith("Switched to")) {
            next.splice(next.length - 1, 0, { role: "assistant", notice: text });
            return next;
          }
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, role: "assistant", error: false, status: text };
          return next;
        }),
      onDelta: (delta: string) =>
        setTurns((prev) => {
          if (controller.signal.aborted) return prev;
          const next = startFreshIfErrored(prev);
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, role: "assistant", error: false, content: (last.content ?? "") + delta };
          return next;
        }),
      onError: (message: string, continuable?: boolean) =>
        setTurns((prev) => {
          if (controller.signal.aborted) return prev;
          const next = [...prev];
          next[next.length - 1] = {
            role: "assistant",
            error: true,
            continuable,
            jobId: jobIdRef.current ?? undefined,
            content: continuable
              ? `${message} It's still got everything it figured out so far — Continue picks up right where it left off instead of starting over.`
              : `The model endpoint didn't respond. ${message}\n\n` +
                `Chat routes to \`${model?.id ?? "?"}\` via the ${model?.provider ?? "local"} provider.`,
          };
          return next;
        }),
      onDone: (usage: { prompt_tokens: number; completion_tokens: number } | null) => {
        if (!usage) return;
        const total = usage.prompt_tokens + usage.completion_tokens;
        if (activeId) storeAddTokens(activeId, total);
        setTurns((prev) => {
          if (controller.signal.aborted) return prev;
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === "assistant" && !last.error) next[next.length - 1] = { ...last, tokens: total };
          return next;
        });
      },
    };
  }

  function agentHandlers(controller: AbortController): StreamHandlers {
    return {
      ...baseHandlers(controller),
      onRepoSwitched: (repository: string) => {
        if (!controller.signal.aborted) switchRepo(repository);
      },
      onModelSwitched: (modelId: string) => {
        if (controller.signal.aborted) return;
        const next = modelsQuery.data?.find((m) => m.id === modelId);
        if (next) handleModel(next);
      },
      // Execution-plan snapshot. Stored on the turn exactly like `status` — each event is complete
      // in itself and simply replaces the last, so there is nothing to merge.
      onPlan: (plan: PlanSnapshot) =>
        setTurns((prev) => {
          if (controller.signal.aborted) return prev;
          const next = startFreshIfErrored(prev);
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, role: "assistant", error: false, plan };
          return next;
        }),
      onToolCall: ({ name, args }: { name: string; args: Record<string, unknown> }) =>
        setTurns((prev) => {
          if (controller.signal.aborted) return prev;
          const next = startFreshIfErrored(prev);
          next.splice(next.length - 1, 0, { role: "assistant", tool: { name, args } });
          return next;
        }),
      onToolResult: ({ name, result }: { name: string; result: string }) =>
        setTurns((prev) => {
          if (controller.signal.aborted) return prev;
          const next = [...prev];
          for (let i = next.length - 2; i >= 0; i--) {
            if (next[i].tool?.name === name && next[i].tool && !next[i].tool!.result) {
              next[i] = { ...next[i], tool: { ...next[i].tool!, result } };
              break;
            }
          }
          return next;
        }),
    };
  }

  // Reattaches to a job that's still running (or finished) on the backend, from a fresh
  // subscription — used both right after starting a new job and when returning to a conversation
  // whose job kept working while this page was elsewhere (different tab, reload, backend restart).
  // Trims any partial turns left over from a previous, now-stale local view of that same response
  // before rebuilding it purely from the job's replayed event log, so nothing gets duplicated.
  async function attachToJob(jobId: string, controller: AbortController) {
    setTurns((prev) => {
      let lastUserIdx = -1;
      prev.forEach((t, i) => {
        if (t.role === "user") lastUserIdx = i;
      });
      return [...prev.slice(0, lastUserIdx + 1), { role: "assistant", content: "" }];
    });
    setStreaming(true);
    abortRef.current = controller;
    jobIdRef.current = jobId;

    await subscribeAgentJob(jobId, agentHandlers(controller));

    if (!controller.signal.aborted && activeId) storeSetJobId(activeId, null);
    if (!controller.signal.aborted) {
      setStreaming(false);
      abortRef.current = null;
      jobIdRef.current = null;
    }
  }

  async function runCompletion(history: ChatMessage[], systemNote?: string) {
    setTurns((prev) => [...prev, { role: "assistant", content: "" }]);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const lastUserText = [...history].reverse().find((m) => m.role === "user")?.content ?? "";

    // --- route: simple → /chat/stream (no tools), complex → /chat/agent (full tools) ---
    const useAgent = needsTools(lastUserText, history);

    if (!useAgent) {
      // Simple message: skip repo context + DESIGN_TOOL_HINT → saves ~6K tokens.
      const systemParts = [systemNote].filter(Boolean) as string[];
      const messages: ChatMessage[] = systemParts.length
        ? [{ role: "system", content: systemParts.join("\n\n") }, ...history]
        : history;

      if (controller.signal.aborted) return;

      await streamChat(messages, model?.id ?? null, baseHandlers(controller));
      setStreaming(false);
      abortRef.current = null;
      return;
    }

    // Complex message: full agent flow with tools + repo context. The job starts detached on the
    // backend — it keeps running even if this subscription gets aborted (new chat, switch
    // conversation, tab close), so the store's pendingJobId is what lets a later visit reattach.
    const repoContext = await buildRepoContext(lastUserText);
    const systemParts = [DESIGN_TOOL_HINT, repoContext, systemNote].filter(Boolean) as string[];
    const messages: ChatMessage[] = systemParts.length
      ? [{ role: "system", content: systemParts.join("\n\n") }, ...history]
      : history;

    if (controller.signal.aborted) return;

    let jobId: string;
    try {
      jobId = await startAgentJob(messages, model?.id ?? null, activeRepo);
    } catch (err) {
      baseHandlers(controller).onError(err instanceof Error ? err.message : String(err));
      setStreaming(false);
      abortRef.current = null;
      return;
    }
    if (activeId) storeSetJobId(activeId, jobId);
    jobIdRef.current = jobId;

    if (controller.signal.aborted) return;

    await subscribeAgentJob(jobId, agentHandlers(controller));

    if (!controller.signal.aborted && activeId) storeSetJobId(activeId, null);
    setStreaming(false);
    abortRef.current = null;
    jobIdRef.current = null;
  }

  // Every change request runs the blast radius FIRST, then waits for the user to approve.
  async function send() {
    const text = input.trim();
    if (!text || streaming) return;

    // Name the conversation from its first message.
    if (activeId) {
      const conv = useChatStore.getState().conversations[activeId];
      if (conv && conv.title === "New chat") storeSetTitle(activeId, text.slice(0, 44));
    }

    const prefix = attachments.map((a) => `Attached file ${a.name}:\n${a.content}`).join("\n\n");
    const outgoing = prefix ? `${prefix}\n\n${text}` : text;
    const history = buildHistory(outgoing);

    setTurns((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setAttachments([]);

    if (quorumMode) {
      setTurns((prev) => [...prev, { role: "assistant", analyzing: true }]);
      setStreaming(true);
      try {
        const result = await api.runQuorum(activeRepo, text);
        setTurns((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: "assistant", quorum: result };
          return next;
        });
      } catch {
        setTurns((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            role: "assistant", error: true,
            content: "Quorum run failed — couldn't reach the backend or the panel errored out.",
          };
          return next;
        });
      } finally {
        setStreaming(false);
      }
      return;
    }

    if (CHANGE_INTENT.test(text)) {
      setTurns((prev) => [...prev, { role: "assistant", analyzing: true }]);
      let res: ImpactResult | null = null;
      try {
        res = await api.impact(text, activeRepo);
      } catch {
        res = null;
      }
      // A blast radius of nothing is not a decision worth stopping someone for. Asking a brand-new
      // repository to "build an index.html" produced a full go/no-go card reading "0 downstream
      // affected — None risk", which the user has to read and approve before any work can begin:
      // pure ceremony in front of a change that cannot break anything, on a project with nothing
      // to break. Gate on there being an actual consequence to weigh, and otherwise just build.
      if (res && (!res.resolved || res.affected_count === 0)) {
        setTurns((prev) => prev.slice(0, -1)); // drop the "analyzing" placeholder
        res = null;
      }
      if (res) {
        const resolved = res;
        setTurns((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: "assistant", impact: resolved, pending: true, history };
          return next;
        });
        return; // hold for the user's go / no-go
      }
      setTurns((prev) => prev.slice(0, -1)); // completely failed (e.g. 500 error) — answer normally
    }

    await runCompletion(history);
  }

  async function retryFrom(index: number) {
    if (streaming) return;
    const trimmed = turns.slice(0, index);
    const history: ChatMessage[] = trimmed
      .filter((t) => !t.error && !t.impact && !t.analyzing && typeof t.content === "string" && t.content)
      .map((t) => ({ role: t.role, content: t.content as string }))
      .slice(-MAX_HISTORY_MESSAGES);
    setTurns(trimmed);
    await runCompletion(history);
  }

  // Resumes a job that ran out of tool-calling rounds — same job id, full message/tool-call
  // history intact server-side, just a bigger round budget. Unlike retryFrom, this does NOT
  // rebuild history from a condensed text summary, so none of the reasoning or tool calls already
  // done gets thrown away.
  async function continueJob(index: number) {
    if (streaming) return;
    const turn = turns[index];
    if (!turn?.jobId) return;
    const jobId = turn.jobId;

    setTurns((prev) => {
      const next = [...prev];
      next[index] = { role: "assistant", content: "", thinking: turn.thinking };
      return next;
    });
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    jobIdRef.current = jobId;

    try {
      await continueAgentJob(jobId);
    } catch (err) {
      baseHandlers(controller).onError(err instanceof Error ? err.message : String(err));
      setStreaming(false);
      abortRef.current = null;
      jobIdRef.current = null;
      return;
    }
    if (activeId) storeSetJobId(activeId, jobId);

    await subscribeAgentJob(jobId, agentHandlers(controller));

    if (!controller.signal.aborted && activeId) storeSetJobId(activeId, null);
    setStreaming(false);
    abortRef.current = null;
    jobIdRef.current = null;
  }

  async function proceedImpact(index: number) {
    const turn = turns[index];
    if (!turn?.impact || !turn.history) return;
    const imp = turn.impact;
    setTurns((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], pending: false };
      return next;
    });
    const note =
      `The user reviewed the change's blast radius and approved proceeding. ` +
      `Targets: ${imp.targets.map((t) => t.label).join(", ")}. ` +
      `Blast radius: ${imp.affected_count} downstream component(s) — ${imp.affected.map((a) => a.label).slice(0, 8).join(", ")}. ` +
      `Risk level: ${imp.risk_level}. Give a concrete, ordered implementation plan that protects each affected component and ends with a verification step.`;
    await runCompletion(turn.history, note);
  }

  function cancelImpact(index: number) {
    setTurns((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], pending: false };
      next.push({
        role: "assistant",
        content: "Held off — no changes planned. Tell me how you'd like to adjust the approach.",
      });
      return next;
    });
  }

  function stop() {
    if (jobIdRef.current) cancelAgentJob(jobIdRef.current);
    abortRef.current?.abort();
    setStreaming(false);
  }

  async function onFiles(files: FileList | null) {
    if (!files) return;
    const read = await Promise.all(
      Array.from(files)
        .slice(0, 4)
        .map(async (f) => ({ name: f.name, content: (await f.text()).slice(0, 12000) })),
    );
    setAttachments((prev) => [...prev, ...read].slice(0, 4));
  }

  const composer = (
    <Composer
      input={input}
      setInput={setInput}
      onSend={send}
      onStop={stop}
      streaming={streaming}
      attachments={attachments}
      removeAttachment={(n) => setAttachments((p) => p.filter((a) => a.name !== n))}
      onAttachClick={() => fileRef.current?.click()}
      activeRepo={activeRepo}
      onOpenRepo={() => setRepoDialogOpen(true)}
      model={model}
      models={modelsQuery.data ?? []}
      onModel={handleModel}
      usedTokens={usedTokens}
      contextWindow={contextWindow}
      usedPct={usedPct}
      quorumMode={quorumMode}
      onToggleQuorum={() => setQuorumMode((v) => !v)}
      liveImpact={liveImpact}
    />
  );

  return (
    <div className="flex h-full">
      <ChatHistory
        conversations={order.map((id) => conversations[id]).filter(Boolean) as Conversation[]}
        activeId={activeId}
        onSelect={selectConversation}
        onNew={startNewChat}
        onDelete={removeConv}
      />
      <div className="flex min-w-0 flex-1 flex-col">
      {!started ? (
        // Home: greeting and composer sit centered in the viewport, activity below.
        <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto">
          <motion.div
            initial="hidden"
            animate="show"
            variants={{ hidden: {}, show: { transition: { staggerChildren: 0.08 } } }}
            className="w-full max-w-2xl px-6 py-10"
          >
            <motion.div
              variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
              transition={{ duration: 0.45, ease: EASE_OUT }}
              className="mb-8 text-center"
            >
              <h1 className="display text-4xl font-semibold tracking-tight text-ink">{greeting()}</h1>
              <p className="mt-3 text-sm text-muted">Ask the engineering brain anything about your codebase.</p>
            </motion.div>
            <motion.div
              variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
              transition={{ duration: 0.45, ease: EASE_OUT }}
            >
              {composer}
            </motion.div>
            <motion.div
              variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
              transition={{ duration: 0.45, ease: EASE_OUT }}
            >
              <RecentActivity events={activityQuery.data ?? []} />
            </motion.div>
          </motion.div>
        </div>
      ) : (
        <>
          <div ref={threadRef} className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto max-w-2xl px-6 py-8">
              {turns.map((turn, i) =>
                turn.impact ? (
                  <ImpactCard
                    key={i}
                    impact={turn.impact}
                    pending={!!turn.pending}
                    onProceed={() => proceedImpact(i)}
                    onCancel={() => cancelImpact(i)}
                  />
                ) : turn.quorum ? (
                  <QuorumCard key={i} quorum={turn.quorum} />
                ) : turn.analyzing ? (
                  <AnalyzingRow key={i} />
                ) : turn.notice ? (
                  <ModelSwitchNotice key={i} text={turn.notice} />
                ) : turn.tool ? (
                  <ToolTrace key={i} tool={turn.tool} />
                ) : (
                  <Fragment key={i}>
                    {turn.plan ? <TaskPlanCard plan={turn.plan} /> : null}
                    <Bubble
                      turn={turn}
                      streaming={streaming && i === turns.length - 1}
                      onRetry={() => retryFrom(i)}
                      onContinue={() => continueJob(i)}
                    />
                  </Fragment>
                ),
              )}
            </div>
          </div>
          <div className="mx-auto w-full max-w-2xl px-6 pb-6">
            {composer}
            <p className="mt-2 text-center text-[11px] text-faint">
              Codexa reasons over the knowledge graph. Verify decisions before you ship them.
            </p>
          </div>
        </>
      )}

      <input
        ref={fileRef}
        type="file"
        multiple
        accept=".txt,.md,.py,.ts,.tsx,.js,.json,.yaml,.yml,.toml"
        className="hidden"
        onChange={(e) => onFiles(e.target.files)}
      />

      <RepoDialog
        open={repoDialogOpen}
        onClose={() => setRepoDialogOpen(false)}
        onLoaded={(info) => switchRepo(info.name)}
        onDeleted={(name) => {
          if (name === activeRepo) switchRepo("codexa-os");
        }}
      />
      </div>
    </div>
  );
}

function ChatHistory({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
}: {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-panel-2 md:flex">
      <div className="p-3">
        <button
          onClick={onNew}
          className="flex w-full items-center gap-2 rounded-lg border border-line-strong px-3 py-2 text-sm font-medium text-ink transition-colors hover:bg-paper-sunk"
        >
          <Plus size={15} /> New chat
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        <p className="status-line px-2 py-1.5">History</p>
        {conversations.length === 0 ? (
          <p className="px-2 text-xs text-faint">No conversations yet.</p>
        ) : (
          conversations.map((c) => (
            <div
              key={c.id}
              className={`group flex items-center gap-1 rounded-lg pr-1 ${c.id === activeId ? "bg-signal-wash" : ""}`}
            >
              <button
                onClick={() => onSelect(c.id)}
                className={`min-w-0 flex-1 rounded-lg px-2.5 py-2 text-left ${
                  c.id === activeId ? "text-signal" : "text-ink-soft hover:bg-paper-sunk"
                }`}
              >
                <span className={`block truncate text-[13px] ${c.id === activeId ? "font-medium" : ""}`}>
                  {c.title || "New chat"}
                </span>
                {c.totalTokens > 0 && (
                  <span className="num block text-[10.5px] text-faint">{formatTokenCount(c.totalTokens)} tokens</span>
                )}
              </button>
              <button
                onClick={() => onDelete(c.id)}
                aria-label="Delete conversation"
                className="grid h-6 w-6 shrink-0 place-items-center rounded text-faint opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}

function RecentActivity({ events }: { events: { id: string; summary: string; occurred_at: string; event_type: string }[] }) {
  if (events.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.3, duration: 0.5 }}
      className="mt-12"
    >
      <p className="status-line mb-3">Recent activity</p>
      <ul className="divide-y divide-line">
        {events.map((e) => (
          <li key={e.id} className="flex items-center gap-4 py-2.5">
            <span className="min-w-0 flex-1 truncate text-sm text-ink-soft">{e.summary}</span>
            <span className="num shrink-0 text-[11px] text-faint">
              {new Date(e.occurred_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          </li>
        ))}
      </ul>
    </motion.div>
  );
}

function Bubble({
  turn, streaming, onRetry, onContinue,
}: {
  turn: Turn; streaming: boolean; onRetry: () => void; onContinue: () => void;
}) {
  if (turn.role === "user") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: EASE_OUT }}
        className="mb-6 flex flex-col items-end"
      >
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-sm leading-relaxed text-panel">
          {turn.content}
        </div>
        {turn.content && (
          <div className="mt-2">
            <CopyButton text={turn.content} />
          </div>
        )}
      </motion.div>
    );
  }
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: EASE_OUT }}
      className="mb-6 flex gap-3"
    >
      <div className="mt-0.5 shrink-0 text-ink">
        <Mark size={22} />
      </div>
      <div className={`min-w-0 text-sm leading-relaxed ${turn.error ? "whitespace-pre-wrap text-warn" : "text-ink-soft"}`}>
        {turn.thinking ? (
          <ThinkingPanel text={turn.thinking} live={streaming && !turn.content} />
        ) : null}
        {streaming && !turn.content && !turn.thinking ? (
          <div className="py-1">
            <ThinkingLoader label={turn.status} />
          </div>
        ) : turn.error ? (
          <>
            {turn.content}
            <div className="mt-2 flex items-center gap-2">
              {turn.continuable && (
                <button
                  onClick={onContinue}
                  className="flex items-center gap-1.5 rounded-md border border-signal/30 bg-signal/10 px-2 py-1 text-xs font-medium text-signal transition-colors hover:bg-signal/20"
                  title="Resume this exact response with more rounds — keeps everything it already figured out"
                >
                  <RotateCcw size={12} />
                  Continue
                </button>
              )}
              <button
                onClick={onRetry}
                className="flex items-center gap-1.5 rounded-md border border-warn/30 px-2 py-1 text-xs font-medium text-warn transition-colors hover:bg-warn/10"
                title={turn.continuable ? "Start over from scratch instead" : undefined}
              >
                <RotateCcw size={12} />
                Retry
              </button>
            </div>
          </>
        ) : turn.content ? (
          <>
            <div className="chat-md">
              <MarkdownView markdown={turn.content} />
            </div>
            {!streaming && (
              <div className="mt-2 flex items-center gap-3">
                <CopyButton text={turn.content} />
                {typeof turn.tokens === "number" && (
                  <span className="num text-xs text-faint">{formatTokenCount(turn.tokens)} tokens</span>
                )}
              </div>
            )}
          </>
        ) : null}
      </div>
    </motion.div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      return;
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <button
      onClick={copy}
      className="flex items-center gap-1.5 rounded-md px-1.5 py-1 text-xs text-faint transition-colors hover:bg-paper-sunk hover:text-ink-soft"
    >
      {copied ? <Check size={12} className="text-signal" /> : <Copy size={12} />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function ThinkingPanel({ text, live }: { text: string; live: boolean }) {
  const [open, setOpen] = useState(live);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (live && open) bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [text, live, open]);

  // Once the answer starts streaming, collapse automatically — matches the "thought, now
  // answering" transition rather than leaving a wall of reasoning text pinned open.
  useEffect(() => {
    if (!live) setOpen(false);
  }, [live]);

  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs font-medium text-faint transition-colors hover:text-muted"
      >
        <BrainCircuit size={12} className={live ? "animate-pulse text-signal" : ""} />
        {live ? "Thinking…" : "Thought process"}
        <ChevronDown size={11} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div
          ref={bodyRef}
          className="num mt-1.5 max-h-56 overflow-y-auto whitespace-pre-wrap rounded-lg border border-line bg-panel-2 p-2.5 text-[11px] leading-relaxed text-muted"
        >
          {text}
        </div>
      )}
    </div>
  );
}

/** A model/key rotation, marked inline in the transcript. Deliberately quiet — this is diagnostic
 *  provenance ("which of the eight buckets produced the next stretch of work"), not an alert, so it
 *  reads as a hairline divider rather than competing with the actual output around it. */
function ModelSwitchNotice({ text }: { text: string }) {
  return (
    <div className="mb-3 ml-9 flex items-center gap-2" role="status">
      <span className="h-px flex-1 bg-line" />
      <span className="num flex items-center gap-1.5 whitespace-nowrap text-[10px] uppercase tracking-[0.12em] text-faint">
        <ArrowLeftRight size={10} />
        {text}
      </span>
      <span className="h-px flex-1 bg-line" />
    </div>
  );
}

function ToolTrace({ tool }: { tool: { name: string; args: Record<string, unknown>; result?: string } }) {
  const [open, setOpen] = useState(false);
  const arg = tool.args.path ?? tool.args.query ?? tool.args.code ?? "";
  return (
    <div className="mb-3 ml-9">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-lg border border-line bg-panel-2 px-2.5 py-1.5 text-xs transition-colors hover:bg-paper-sunk"
      >
        <Wrench size={12} className="text-signal" />
        <span className="font-medium text-ink-soft">{tool.name}</span>
        {arg ? <span className="num max-w-[220px] truncate text-faint">{String(arg)}</span> : null}
        {!tool.result && <DotsLoader size={5} />}
        <ChevronDown size={12} className={`text-faint transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && tool.result && (
        <pre className="num mt-1 max-h-56 max-w-2xl overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-panel-2 p-2.5 text-[11px] text-ink-soft">
          {tool.result}
        </pre>
      )}
    </div>
  );
}

function QuorumCard({ quorum }: { quorum: QuorumRunResult }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-6 ml-9 max-w-2xl">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted">
        <Users size={13} className="text-signal" />
        <span>Quorum</span>
        <span className="rounded-full border border-line px-2 py-0.5 text-[10px] text-faint">
          {quorum.cards.length} agents{quorum.debated ? " · debated" : ""}
        </span>
      </div>

      {quorum.resolved ? (
        <MarkdownView markdown={quorum.winning_answer ?? ""} />
      ) : (
        <div className="rounded-lg border border-line-strong bg-panel-2 p-3 text-sm text-ink-soft">
          Panel couldn't reach a graph-grounded consensus — surfacing every surviving answer instead
          of guessing at one:
          <ul className="mt-2 space-y-2">
            {quorum.cards.map((c) => (
              <li key={c.model} className="rounded-md border border-line bg-panel p-2 text-xs">
                <span className="num text-faint">{c.model}</span> — {c.answer}
              </li>
            ))}
          </ul>
        </div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        className="mt-2 flex items-center gap-1.5 text-[11px] text-faint transition-colors hover:text-ink"
      >
        {open ? "Hide" : "Show"} panel breakdown
        <ChevronDown size={11} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <ul className="mt-2 space-y-1.5">
          {quorum.cards.map((c) => (
            <li key={c.model} className="rounded-md border border-line bg-panel-2 p-2 text-[11px]">
              <div className="flex items-center justify-between gap-2">
                <span className="num font-medium text-ink-soft">{c.model}</span>
                <span className="num text-faint">
                  conf {c.confidence.toFixed(2)}
                  {c.calibration < 1 ? ` (×${c.calibration.toFixed(2)} track record)` : ""} ·{" "}
                  {c.verified_count} verified / {c.failed_count} failed
                  {c.round > 1 ? " · revised" : ""}
                </span>
              </div>
              {c.failed_reasons.length > 0 && (
                <p className="mt-1 text-faint">{c.failed_reasons.join("; ")}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AnalyzingRow() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="mb-6 flex items-center gap-3 text-sm text-muted"
    >
      <span className="text-ink">
        <Mark size={22} />
      </span>
      <span className="flex items-center gap-3">
        Computing blast radius
        <DotsLoader size={8} />
      </span>
    </motion.div>
  );
}

function Composer(props: {
  input: string;
  setInput: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  streaming: boolean;
  attachments: Attachment[];
  removeAttachment: (name: string) => void;
  onAttachClick: () => void;
  activeRepo: string;
  onOpenRepo: () => void;
  model: ChatModel | null;
  models: ChatModel[];
  onModel: (m: ChatModel) => void;
  usedTokens: number;
  contextWindow: number;
  usedPct: number;
  quorumMode: boolean;
  onToggleQuorum: () => void;
  liveImpact: ImpactResult | null;
}) {
  const [pickerOpen, setPickerOpen] = useState(false);
  // Fresh chat centers the composer mid-viewport (see the `!started` branch above) — there isn't
  // always 320px (max-h-80) of room above the model button for the dropdown to open upward into,
  // which clipped the topmost model(s) against the scroll container's own top edge. Measure real
  // space above vs below the button each time it opens and flip direction instead of always
  // assuming "upward" (only true once the composer is docked at the bottom of an active thread).
  const [dropUp, setDropUp] = useState(true);
  const pickerBtnRef = useRef<HTMLButtonElement>(null);
  const canSend = props.input.trim().length > 0 && !props.streaming;

  function togglePicker() {
    if (!pickerOpen) {
      const rect = pickerBtnRef.current?.getBoundingClientRect();
      if (rect) setDropUp(rect.top > window.innerHeight - rect.bottom);
    }
    setPickerOpen((v) => !v);
  }

  return (
    <div className="rounded-2xl border border-line-strong bg-panel shadow-md transition-all duration-300 focus-within:border-signal/40 focus-within:shadow-[0_0_0_4px_var(--color-signal-wash)]">
      {props.liveImpact && (
        <div className="flex items-center gap-1.5 px-3 pt-3 text-[11px] text-muted">
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{
              background:
                props.liveImpact.risk_level === "Critical" || props.liveImpact.risk_level === "High"
                  ? "var(--color-danger)"
                  : props.liveImpact.risk_level === "Medium"
                    ? "var(--color-gold)"
                    : "var(--color-signal)",
            }}
          />
          <span className="num">{props.liveImpact.affected_count} downstream</span>
          <span>· {props.liveImpact.risk_level} risk</span>
          {props.liveImpact.coupling_risks.length > 0 && (
            <span className="text-[var(--color-warn)]">
              · {props.liveImpact.coupling_risks.length} historically risky
            </span>
          )}
        </div>
      )}

      {props.attachments.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-3 pt-3">
          {props.attachments.map((a) => (
            <span
              key={a.name}
              className="flex items-center gap-1.5 rounded-lg border border-line bg-paper-sunk px-2 py-1 text-[11px] text-ink-soft"
            >
              {a.name}
              <button onClick={() => props.removeAttachment(a.name)} aria-label={`Remove ${a.name}`}>
                <X size={12} className="text-faint hover:text-ink" />
              </button>
            </span>
          ))}
        </div>
      )}

      <textarea
        value={props.input}
        onChange={(e) => props.setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            props.onSend();
          }
        }}
        rows={1}
        placeholder="Ask the engineering brain…"
        className="max-h-48 min-h-[52px] w-full resize-none bg-transparent px-4 py-3.5 text-sm leading-relaxed text-ink outline-none placeholder:text-faint"
      />

      <div className="flex items-center justify-between gap-2 px-2.5 pb-2.5">
        <div className="flex items-center gap-1">
          <button
            onClick={props.onAttachClick}
            className="grid h-9 w-9 place-items-center rounded-lg text-muted transition-colors hover:bg-paper-sunk hover:text-ink"
            aria-label="Attach files"
          >
            <Paperclip size={17} />
          </button>
          <button
            onClick={props.onOpenRepo}
            className="flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-muted transition-colors hover:bg-paper-sunk hover:text-ink"
            aria-label="Load repository"
          >
            <GitBranch size={15} />
            <span className="num max-w-[120px] truncate">{props.activeRepo}</span>
          </button>
          <button
            onClick={props.onToggleQuorum}
            aria-pressed={props.quorumMode}
            title="Quorum: answer with a panel of agents that cross-check each other against the real codebase before responding"
            className={`flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium transition-colors ${
              props.quorumMode
                ? "bg-signal/15 text-signal"
                : "text-muted hover:bg-paper-sunk hover:text-ink"
            }`}
          >
            <Users size={15} />
            Quorum
          </button>
        </div>

        <div className="flex items-center gap-2">
          <ContextGauge used={props.usedTokens} total={props.contextWindow} pct={props.usedPct} />

          <div className="relative">
            <button
              ref={pickerBtnRef}
              onClick={togglePicker}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-ink-soft transition-colors hover:bg-paper-sunk"
            >
              {props.model?.label ?? "Model"}
              <ChevronDown size={13} className={`text-faint transition-transform ${pickerOpen ? "rotate-180" : ""}`} />
            </button>
            <AnimatePresence>
              {pickerOpen && (
                <motion.div
                  initial={{ opacity: 0, y: dropUp ? 6 : -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: dropUp ? 6 : -6 }}
                  transition={{ duration: 0.16, ease: EASE_OUT }}
                  className={`absolute right-0 z-30 max-h-80 w-60 overflow-y-auto rounded-xl border border-line bg-panel p-1 shadow-lg ${dropUp ? "bottom-11" : "top-11"}`}
                >
                  {props.models.length === 0 && (
                    <p className="px-3 py-2 text-xs text-muted">No models configured.</p>
                  )}
                  {props.models.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => {
                        props.onModel(m);
                        setPickerOpen(false);
                      }}
                      className={`flex w-full flex-col items-start gap-0.5 rounded-lg px-3 py-2 text-left transition-colors hover:bg-paper-sunk ${
                        m.id === props.model?.id ? "bg-signal-wash" : ""
                      }`}
                    >
                      <span className="text-xs font-medium text-ink">{m.label}</span>
                      <span className="status-line !tracking-[0.1em]">
                        {m.provider} · {(m.context_window / 1000).toFixed(0)}k ctx
                      </span>
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <button
            onClick={props.streaming ? props.onStop : props.onSend}
            disabled={!props.streaming && !canSend}
            className="grid h-9 w-9 place-items-center rounded-lg bg-ink text-panel transition-all hover:bg-ink-soft active:scale-95 disabled:opacity-30"
            aria-label={props.streaming ? "Stop" : "Send"}
          >
            {props.streaming ? <Square size={14} className="fill-current" /> : <ArrowUp size={17} />}
          </button>
        </div>
      </div>
    </div>
  );
}

function ContextGauge({ used, total, pct }: { used: number; total: number; pct: number }) {
  const near = pct > 80;
  return (
    <div className="hidden items-center gap-2 sm:flex" title={`${used} / ${total} tokens (approx)`}>
      <div className="h-1 w-16 overflow-hidden rounded-full bg-paper-sunk">
        <div
          className={`h-full rounded-full transition-all duration-500 ${near ? "bg-warn" : "bg-signal"}`}
          style={{ width: `${Math.max(3, pct)}%` }}
        />
      </div>
      <span className="num text-[10.5px] text-faint">{(used / 1000).toFixed(1)}k</span>
    </div>
  );
}
