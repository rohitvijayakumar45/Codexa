"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

// The active repository is shared app-wide: chat loads/injects its permanent memory, the Memory tab
// shows it. Persisted so it survives reloads. Defaults to the platform's own repo.
interface RepoState {
  activeRepo: string;
  setActiveRepo: (repo: string) => void;
}

export const useRepoStore = create<RepoState>()(
  persist(
    (set) => ({
      activeRepo: "codexa-os",
      setActiveRepo: (repo) => set({ activeRepo: repo }),
    }),
    { name: "codexa-active-repo" },
  ),
);
