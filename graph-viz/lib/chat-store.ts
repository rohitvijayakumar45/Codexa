"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ChatMessage, ImpactResult, PlanSnapshot, QuorumRunResult } from "@/lib/api";

// A single message in a conversation. `analyzing` is transient and never persisted.
export interface StoredTurn {
  role: "user" | "assistant";
  content?: string;
  thinking?: string;
  // Latest human-readable status ("Writing app.py", "Running tests") from the backend's status
  // events — shown in place of the generic "thinking" loader while streaming, since most models
  // never emit reasoning_content at all and this is otherwise the only sign of real progress.
  status?: string;
  // A model/key rotation, kept as its own row in the transcript rather than as transient loader
  // text. The loader label disappears the moment tokens start streaming, which is exactly when a
  // switch matters least to see and most to remember — for debugging you need to look back and
  // find which bucket was live when things slowed down or output changed character.
  notice?: string;
  // Latest snapshot of the backend's execution plan for this turn's job. Persisted like `status`
  // rather than kept in transient state: the plan is what a long build's scrollback is actually
  // about, and a reload mid-job (or a later visit to a finished one) should still show which tasks
  // Codexa verified. Each plan event replaces this wholesale — it is a snapshot, never a patch.
  plan?: PlanSnapshot;
  error?: boolean;
  // Only meaningful alongside error: true. When set, this turn's agent job errored out solely
  // from running out of tool-calling rounds and can be resumed (same job id, full history intact)
  // via continueAgentJob instead of losing all progress to a fresh retry — see chat/page.tsx's
  // continueJob(). jobId is the errored job to resume; continuable says whether that's possible.
  continuable?: boolean;
  jobId?: string;
  impact?: ImpactResult;
  quorum?: QuorumRunResult;
  // A phased build started from this turn; the card polls its live status by id.
  phasedBuildId?: string;
  pending?: boolean;
  history?: ChatMessage[];
  tool?: { name: string; args: Record<string, unknown>; result?: string };
  tokens?: number; // this response's own prompt+completion total, from the backend's done event
}

export interface Conversation {
  id: string;
  title: string;
  modelId: string | null;
  turns: StoredTurn[];
  createdAt: number;
  updatedAt: number;
  totalTokens: number; // cumulative prompt+completion across every message sent in this conversation
  // Backend agent job id for an in-flight response, if any. Survives tab switches, reloads, and
  // backend restarts (checkpointed server-side) — set when a job starts, cleared once it's done,
  // so reopening this conversation later can reattach to work that kept running unattended.
  pendingJobId?: string | null;
}

interface ChatState {
  conversations: Record<string, Conversation>;
  order: string[]; // most-recently-updated first
  activeId: string | null;
  newConversation: (modelId?: string | null) => string;
  ensureActive: () => string;
  setActive: (id: string) => void;
  setTurns: (id: string, turns: StoredTurn[]) => void;
  setModel: (id: string, modelId: string | null) => void;
  setTitle: (id: string, title: string) => void;
  addTokens: (id: string, count: number) => void;
  setJobId: (id: string, jobId: string | null) => void;
  remove: (id: string) => void;
}

const uid = () => Math.random().toString(36).slice(2, 10);

function makeConversation(modelId: string | null = null): Conversation {
  const now = Date.now();
  return { id: uid(), title: "New chat", modelId, turns: [], createdAt: now, updatedAt: now, totalTokens: 0 };
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      conversations: {},
      order: [],
      activeId: null,

      newConversation: (modelId = null) => {
        const conv = makeConversation(modelId);
        set((s) => ({
          conversations: { ...s.conversations, [conv.id]: conv },
          order: [conv.id, ...s.order],
          activeId: conv.id,
        }));
        return conv.id;
      },

      ensureActive: () => {
        const { activeId, conversations } = get();
        if (activeId && conversations[activeId]) return activeId;
        return get().newConversation();
      },

      setActive: (id) => set({ activeId: id }),

      setTurns: (id, turns) =>
        set((s) => {
          const conv = s.conversations[id];
          if (!conv) return s;
          const clean = turns.filter((t) => !("analyzing" in t) || !(t as { analyzing?: boolean }).analyzing);
          const updated: Conversation = { ...conv, turns: clean, updatedAt: Date.now() };
          return {
            conversations: { ...s.conversations, [id]: updated },
            order: [id, ...s.order.filter((x) => x !== id)],
          };
        }),

      setModel: (id, modelId) =>
        set((s) => {
          const conv = s.conversations[id];
          if (!conv) return s;
          return { conversations: { ...s.conversations, [id]: { ...conv, modelId } } };
        }),

      setTitle: (id, title) =>
        set((s) => {
          const conv = s.conversations[id];
          if (!conv) return s;
          return { conversations: { ...s.conversations, [id]: { ...conv, title } } };
        }),

      addTokens: (id, count) =>
        set((s) => {
          const conv = s.conversations[id];
          if (!conv || count <= 0) return s;
          return {
            conversations: { ...s.conversations, [id]: { ...conv, totalTokens: (conv.totalTokens ?? 0) + count } },
          };
        }),

      setJobId: (id, jobId) =>
        set((s) => {
          const conv = s.conversations[id];
          if (!conv) return s;
          return { conversations: { ...s.conversations, [id]: { ...conv, pendingJobId: jobId } } };
        }),

      remove: (id) =>
        set((s) => {
          const rest = { ...s.conversations };
          delete rest[id];
          const order = s.order.filter((x) => x !== id);
          const activeId = s.activeId === id ? (order[0] ?? null) : s.activeId;
          return { conversations: rest, order, activeId };
        }),
    }),
    { name: "codexa-chat" },
  ),
);
