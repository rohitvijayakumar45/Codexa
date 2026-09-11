"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { X, GitBranch, Check, Sparkles, FolderOpen, Loader2, Trash2 } from "lucide-react";
import { api, type RepositoryInfo } from "@/lib/api";
import { Button, EASE_OUT } from "@/components/ui/primitives";

type Mode = "switch" | "load" | "create";

export function RepoDialog({
  open,
  onClose,
  onLoaded,
  onDeleted,
  defaultMode = "load",
}: {
  open: boolean;
  onClose: () => void;
  onLoaded: (info: RepositoryInfo) => void;
  onDeleted?: (name: string) => void;
  defaultMode?: Mode;
}) {
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode>(defaultMode);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [activating, setActivating] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<(RepositoryInfo & { switched?: boolean }) | null>(null);

  const listQuery = useQuery({
    queryKey: ["repo-listing"],
    queryFn: api.listRepositories,
    enabled: open && mode === "switch",
  });

  async function activate(target: string) {
    if (activating) return;
    setActivating(target);
    setError(null);
    try {
      const info = await api.activateRepository(target);
      setDone({ ...info, switched: true });
      onLoaded(info);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActivating(null);
    }
  }

  async function deleteRepo(target: string) {
    if (confirmDelete !== target) {
      setConfirmDelete(target);
      return;
    }
    setDeleting(target);
    setError(null);
    try {
      await api.deleteRepository(target);
      qc.invalidateQueries({ queryKey: ["repo-listing"] });
      onDeleted?.(target);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDeleting(null);
      setConfirmDelete(null);
    }
  }

  async function load() {
    const trimmed = url.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setError(null);
    try {
      const info = await api.loadRepository(trimmed);
      setDone(info);
      onLoaded(info);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function create() {
    const trimmed = name.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setError(null);
    try {
      const info = await api.createRepository(trimmed, description.trim());
      setDone(info);
      onLoaded(info);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setUrl("");
    setName("");
    setDescription("");
    setError(null);
    setDone(null);
    setConfirmDelete(null);
    setMode(defaultMode);
    onClose();
  }

  const TITLES: Record<Mode, string> = {
    switch: "Switch repository",
    load: "Load a repository",
    create: "Create a new project",
  };
  const ICONS: Record<Mode, typeof GitBranch> = { switch: FolderOpen, load: GitBranch, create: Sparkles };
  const Icon = ICONS[mode];

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 grid place-items-center bg-ink/20 p-6 backdrop-blur-sm"
          onClick={reset}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.25, ease: EASE_OUT }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md overflow-hidden rounded-2xl border border-line bg-panel shadow-lg"
          >
            <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
              <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                <Icon size={16} className="text-signal" />
                {TITLES[mode]}
              </span>
              <button onClick={reset} className="text-muted hover:text-ink" aria-label="Close">
                <X size={16} />
              </button>
            </div>

            {done ? (
              <div className="px-5 py-6">
                <div className="flex items-center gap-2 text-signal">
                  <Check size={18} />
                  <span className="text-sm font-medium">{done.name} is ready</span>
                </div>
                <p className="mt-2 text-sm text-muted">
                  {done.switched
                    ? "Switched — its memory and graph are active."
                    : done.already_loaded
                      ? "Already loaded — its memory is available."
                      : done.url
                        ? `Cloned ${done.file_count} files${done.languages.length ? `, ${done.languages.slice(0, 3).join(", ")}` : ""}. Wrote ${done.memories_created} permanent memories.`
                        : `Scaffolded from nothing. Wrote ${done.memories_created} permanent memories — ready to build with the chat agent.`}
                </p>
                <Button onClick={reset} className="mt-5 w-full">
                  Start working
                </Button>
              </div>
            ) : (
              <div className="px-5 py-5">
                <div className="mb-4 flex gap-1 rounded-lg border border-line bg-panel-2 p-0.5">
                  <button
                    onClick={() => setMode("switch")}
                    className={`flex-1 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                      mode === "switch" ? "bg-panel text-ink shadow-sm" : "text-muted hover:text-ink"
                    }`}
                  >
                    Switch
                  </button>
                  <button
                    onClick={() => setMode("load")}
                    className={`flex-1 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                      mode === "load" ? "bg-panel text-ink shadow-sm" : "text-muted hover:text-ink"
                    }`}
                  >
                    Git URL
                  </button>
                  <button
                    onClick={() => setMode("create")}
                    className={`flex-1 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                      mode === "create" ? "bg-panel text-ink shadow-sm" : "text-muted hover:text-ink"
                    }`}
                  >
                    New
                  </button>
                </div>

                {mode === "switch" ? (
                  <>
                    <p className="text-sm text-muted">
                      Repositories already on disk — switching is instant, nothing is re-cloned.
                    </p>
                    <div className="mt-3 max-h-72 overflow-y-auto rounded-lg border border-line">
                      {listQuery.isLoading ? (
                        <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted">
                          <Loader2 size={14} className="animate-spin" />
                          Reading disk…
                        </div>
                      ) : listQuery.error ? (
                        <p className="px-3 py-6 text-center text-xs text-danger">
                          {(listQuery.error as Error).message}
                        </p>
                      ) : (
                        (listQuery.data ?? []).map((r) => (
                          <div
                            key={r.name}
                            className="flex w-full items-center justify-between border-b border-line last:border-b-0 hover:bg-panel-2"
                          >
                            <button
                              onClick={() => activate(r.name)}
                              disabled={!!activating}
                              className="flex-1 px-3 py-2.5 text-left disabled:opacity-60"
                            >
                              <span className="num block text-sm text-ink">{r.name}</span>
                              <span className="text-[11px] text-faint">
                                {r.url || "Scaffolded project"} {r.loaded ? "· in memory" : "· on disk"}
                              </span>
                            </button>
                            {activating === r.name && (
                              <Loader2 size={14} className="mr-3 shrink-0 animate-spin text-signal" />
                            )}
                            {r.name !== "codexa-os" && (
                              <button
                                onClick={() => deleteRepo(r.name)}
                                disabled={deleting === r.name}
                                title={confirmDelete === r.name ? "Click again to confirm" : `Delete ${r.name}`}
                                className={`mr-2 shrink-0 rounded-md p-1.5 transition-colors ${
                                  confirmDelete === r.name
                                    ? "bg-danger/10 text-danger"
                                    : "text-faint hover:bg-danger/10 hover:text-danger"
                                }`}
                              >
                                {deleting === r.name ? (
                                  <Loader2 size={14} className="animate-spin" />
                                ) : (
                                  <Trash2 size={14} />
                                )}
                              </button>
                            )}
                          </div>
                        ))
                      )}
                      {!listQuery.isLoading && !listQuery.error && (listQuery.data ?? []).length === 0 && (
                        <p className="px-3 py-6 text-center text-xs text-faint">No repositories on disk yet.</p>
                      )}
                    </div>
                    {error && <p className="mt-2 text-xs text-danger">{error}</p>}
                  </>
                ) : mode === "load" ? (
                  <>
                    <p className="text-sm text-muted">
                      Paste a repository URL — the GitHub page address works too. Codexa clones it,
                      reads it, and builds its graph, architecture and memory.
                    </p>
                    <input
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && load()}
                      placeholder="https://github.com/owner/repo"
                      autoFocus
                      className="num mt-4 w-full rounded-lg border border-line-strong bg-panel px-3 py-2.5 text-sm text-ink outline-none placeholder:text-faint focus:border-ink/30"
                    />
                    {error && <p className="mt-2 text-xs text-danger">{error}</p>}
                    <Button onClick={load} disabled={loading || !url.trim()} className="mt-4 w-full">
                      {loading ? "Cloning & analysing — large repositories take a minute…" : "Clone & analyze"}
                    </Button>
                  </>
                ) : (
                  <>
                    <p className="text-sm text-muted">
                      Scaffold an empty project — no clone, nothing to point at. The chat agent can
                      then build it up from scratch with its file tools, or you can ask it to right
                      after creating.
                    </p>
                    <input
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && create()}
                      placeholder="my-new-app"
                      autoFocus
                      className="num mt-4 w-full rounded-lg border border-line-strong bg-panel px-3 py-2.5 text-sm text-ink outline-none placeholder:text-faint focus:border-ink/30"
                    />
                    <input
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && create()}
                      placeholder="One-line description (optional)"
                      className="mt-2 w-full rounded-lg border border-line-strong bg-panel px-3 py-2.5 text-sm text-ink outline-none placeholder:text-faint focus:border-ink/30"
                    />
                    {error && <p className="mt-2 text-xs text-danger">{error}</p>}
                    <Button onClick={create} disabled={loading || !name.trim()} className="mt-4 w-full">
                      {loading ? "Creating…" : "Create project"}
                    </Button>
                  </>
                )}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
