"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { GitBranch } from "lucide-react";
import { useRepoStore } from "@/lib/repo-store";
import { RepoDialog } from "@/components/chat/RepoDialog";
import type { RepositoryInfo } from "@/lib/api";

/** Global repo switcher — mounted once in the Rail so every page (not just Chat) can load, create,
    or switch the active repository. Reuses the same RepoDialog the chat composer already had. */
export function RepoSwitcher() {
  const activeRepo = useRepoStore((s) => s.activeRepo);
  const setActiveRepo = useRepoStore((s) => s.setActiveRepo);
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  function switchRepo(info: RepositoryInfo) {
    setActiveRepo(info.name);
    qc.invalidateQueries();
    setOpen(false);
  }

  function handleDeleted(name: string) {
    if (name === activeRepo) {
      setActiveRepo("codexa-os");
      qc.invalidateQueries();
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label={`Switch repository (current: ${activeRepo})`}
        className="group relative grid h-11 w-11 place-items-center rounded-xl text-muted transition-colors duration-200 ease-out hover:bg-paper-sunk hover:text-ink"
      >
        <GitBranch size={19} strokeWidth={1.75} />
        <span className="pointer-events-none absolute left-[52px] z-30 flex translate-x-[-4px] items-center gap-2 whitespace-nowrap rounded-lg border border-line bg-panel px-2.5 py-1.5 text-xs font-medium text-ink opacity-0 shadow-md transition-all duration-200 ease-out group-hover:translate-x-0 group-hover:opacity-100">
          {activeRepo}
        </span>
      </button>
      <RepoDialog
        open={open}
        onClose={() => setOpen(false)}
        onLoaded={switchRepo}
        onDeleted={handleDeleted}
        defaultMode="switch"
      />
    </>
  );
}
