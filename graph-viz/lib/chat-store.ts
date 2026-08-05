"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ChatMessage, ImpactResult } from "@/lib/api";

// A single message in a conversation. `analyzing` is transient and never persisted.
export interface StoredTurn {
  role: "user" | "assistant";
  content?: string;
  error?: boolean;
  impact?: ImpactResult;
  pending?: boolean;
  history?: ChatMessage[];
}

export interface Conversation {
  id: string;
  title: string;
  modelId: string | null;
  turns: StoredTurn[];
  createdAt: number;
  updatedAt: number;
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
  remove: (id: string) => void;
}

const uid = () => Math.random().toString(36).slice(2, 10);

function makeConversation(modelId: string | null = null): Conversation {
  const now = Date.now();
  return { id: uid(), title: "New chat", modelId, turns: [], createdAt: now, updatedAt: now };
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
