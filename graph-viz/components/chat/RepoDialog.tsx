"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X, GitBranch, Check } from "lucide-react";
import { api, type RepositoryInfo } from "@/lib/api";
import { Button, EASE_OUT } from "@/components/ui/primitives";

export function RepoDialog({
  open,
  onClose,
  onLoaded,
}: {
  open: boolean;
  onClose: () => void;
  onLoaded: (info: RepositoryInfo) => void;
}) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<RepositoryInfo | null>(null);

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

  function reset() {
    setUrl("");
    setError(null);
    setDone(null);
    onClose();
  }

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
                <GitBranch size={16} className="text-signal" /> Load a repository
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
                  {done.already_loaded
                    ? "Already loaded — its memory is available."
                    : `Cloned ${done.file_count} files${done.languages.length ? `, ${done.languages.slice(0, 3).join(", ")}` : ""}. Wrote ${done.memories_created} permanent memories.`}
                </p>
                <Button onClick={reset} className="mt-5 w-full">
                  Start working
                </Button>
              </div>
            ) : (
              <div className="px-5 py-5">
                <p className="text-sm text-muted">
                  Paste a git URL. Codexa clones it, reads it, and writes a permanent memory every model
                  can use.
                </p>
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && load()}
                  placeholder="https://github.com/owner/repo.git"
                  autoFocus
                  className="num mt-4 w-full rounded-lg border border-line-strong bg-panel px-3 py-2.5 text-sm text-ink outline-none placeholder:text-faint focus:border-ink/30"
                />
                {error && <p className="mt-2 text-xs text-danger">{error}</p>}
                <Button onClick={load} disabled={loading || !url.trim()} className="mt-4 w-full">
                  {loading ? "Cloning…" : "Clone & analyze"}
                </Button>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
