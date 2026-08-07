"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Paperclip, ArrowUp, ChevronDown, Square, X, GitBranch, Plus, Trash2, Wrench, BrainCircuit, Copy, Check, RotateCcw } from "lucide-react";
import { api, streamAgentChat, type ChatMessage, type ChatModel, type ImpactResult } from "@/lib/api";
import { Mark } from "@/components/shell/Mark";
import { EASE_OUT } from "@/components/ui/primitives";
import { ImpactCard } from "@/components/chat/ImpactCard";
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
      `You are working on the repository '${activeRepo}'. Answer strictly from the facts in its ` +
      `persistent memory below. Do NOT invent features, modules, or use-cases that aren't supported ` +
      `by these facts; if something isn't covered, say you don't have that detail.\n${lines}`
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

  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [model, setModel] = useState<ChatModel | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const turnsRef = useRef<Turn[]>(turns);
  turnsRef.current = turns;
  const skipSaveRef = useRef(false);

  useEffect(() => {
    ensureActive();
  }, [ensureActive]);

  // Load a conversation's turns when it becomes active.
  useEffect(() => {
    if (!activeId) return;
    const conv = useChatStore.getState().conversations[activeId];
    skipSaveRef.current = true;
    setTurns((conv?.turns as Turn[]) ?? []);
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
  useEffect(
    () => () => {
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
      .map((t) => ({ role: t.role, content: t.content as string }));
    return [...prior, { role: "user", content: outgoing }];
  }

  async function runCompletion(history: ChatMessage[], systemNote?: string) {
    setTurns((prev) => [...prev, { role: "assistant", content: "" }]);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const lastUserText = [...history].reverse().find((m) => m.role === "user")?.content ?? "";
    const repoContext = await buildRepoContext(lastUserText);
    const systemParts = [DESIGN_TOOL_HINT, repoContext, systemNote].filter(Boolean) as string[];
    const messages: ChatMessage[] = systemParts.length
      ? [{ role: "system", content: systemParts.join("\n\n") }, ...history]
      : history;

    if (controller.signal.aborted) return;

    await streamAgentChat(messages, model?.id ?? null, activeRepo, {
      signal: controller.signal,
      // Tool trace rows are inserted before the streaming text turn (kept last). Every updater
      // bails on `prev` unchanged if this stream was aborted — closes the race where a chunk was
      // already in flight the instant `abortActiveStream()` fired (the fetch abort itself is
      // handled below the closures, but a chunk mid-delivery can still land one tick later).
      onRepoSwitched: (repository) => {
        if (!controller.signal.aborted) switchRepo(repository);
      },
      onToolCall: ({ name, args }) =>
        setTurns((prev) => {
          if (controller.signal.aborted) return prev;
          const next = [...prev];
          next.splice(next.length - 1, 0, { role: "assistant", tool: { name, args } });
          return next;
        }),
      onToolResult: ({ name, result }) =>
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
      onThinking: (chunk) =>
        setTurns((prev) => {
          if (controller.signal.aborted) return prev;
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, role: "assistant", thinking: (last.thinking ?? "") + chunk };
          return next;
        }),
      onDelta: (delta) =>
        setTurns((prev) => {
          if (controller.signal.aborted) return prev;
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, role: "assistant", content: (last.content ?? "") + delta };
          return next;
        }),
      onError: (message) =>
        setTurns((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            role: "assistant",
            error: true,
            content:
              `The model endpoint didn't respond. ${message}\n\n` +
              `Chat routes to \`${model?.id ?? "?"}\` via the ${model?.provider ?? "local"} provider.`,
          };
          return next;
        }),
      onDone: () => {},
    });

    setStreaming(false);
    abortRef.current = null;
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

    if (CHANGE_INTENT.test(text)) {
      setTurns((prev) => [...prev, { role: "assistant", analyzing: true }]);
      let res: ImpactResult | null = null;
      try {
        res = await api.impact(text);
      } catch {
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
      .map((t) => ({ role: t.role, content: t.content as string }));
    setTurns(trimmed);
    await runCompletion(history);
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
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: EASE_OUT }}
            className="w-full max-w-2xl px-6 py-10"
          >
            <div className="mb-8 text-center">
              <h1 className="display text-4xl font-semibold tracking-tight text-ink">{greeting()}</h1>
              <p className="mt-3 text-sm text-muted">Ask the engineering brain anything about your codebase.</p>
            </div>
            {composer}
            <RecentActivity events={activityQuery.data ?? []} />
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
                ) : turn.analyzing ? (
                  <AnalyzingRow key={i} />
                ) : turn.tool ? (
                  <ToolTrace key={i} tool={turn.tool} />
                ) : (
                  <Bubble
                    key={i}
                    turn={turn}
                    streaming={streaming && i === turns.length - 1}
                    onRetry={() => retryFrom(i)}
                  />
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
                className={`min-w-0 flex-1 truncate rounded-lg px-2.5 py-2 text-left text-[13px] ${
                  c.id === activeId ? "font-medium text-signal" : "text-ink-soft hover:bg-paper-sunk"
                }`}
              >
                {c.title || "New chat"}
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

function Bubble({ turn, streaming, onRetry }: { turn: Turn; streaming: boolean; onRetry: () => void }) {
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
        {turn.content && <CopyButton text={turn.content} />}
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
            <ThinkingLoader />
          </div>
        ) : turn.error ? (
          <>
            {turn.content}
            <button
              onClick={onRetry}
              className="mt-2 flex items-center gap-1.5 rounded-md border border-warn/30 px-2 py-1 text-xs font-medium text-warn transition-colors hover:bg-warn/10"
            >
              <RotateCcw size={12} />
              Retry
            </button>
          </>
        ) : turn.content ? (
          <>
            <div className="chat-md">
              <MarkdownView markdown={turn.content} />
            </div>
            {!streaming && <CopyButton text={turn.content} />}
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
      className="mt-2 flex items-center gap-1.5 rounded-md px-1.5 py-1 text-xs text-faint transition-colors hover:bg-paper-sunk hover:text-ink-soft"
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
}) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const canSend = props.input.trim().length > 0 && !props.streaming;

  return (
    <div className="rounded-2xl border border-line-strong bg-panel shadow-md transition-colors focus-within:border-ink/30">
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
        </div>

        <div className="flex items-center gap-2">
          <ContextGauge used={props.usedTokens} total={props.contextWindow} pct={props.usedPct} />

          <div className="relative">
            <button
              onClick={() => setPickerOpen((v) => !v)}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-ink-soft transition-colors hover:bg-paper-sunk"
            >
              {props.model?.label ?? "Model"}
              <ChevronDown size={13} className={`text-faint transition-transform ${pickerOpen ? "rotate-180" : ""}`} />
            </button>
            <AnimatePresence>
              {pickerOpen && (
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 6 }}
                  transition={{ duration: 0.16, ease: EASE_OUT }}
                  className="absolute bottom-11 right-0 z-30 w-60 overflow-hidden rounded-xl border border-line bg-panel p-1 shadow-lg"
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
