"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Download, FileCode, Folder, FolderOpen, X } from "lucide-react";
import { api, type FileTreeNode } from "@/lib/api";
import { useRepoStore } from "@/lib/repo-store";
import { PageHeader } from "@/components/shell/PageHeader";
import { CenteredError, CenteredLoading, CenteredEmpty } from "@/components/shell/States";
import { CodeView } from "@/components/ide/CodeView";

const base = (p: string) => p.split("/").pop() ?? p;

export default function IdePage() {
  const activeRepo = useRepoStore((s) => s.activeRepo);
  const treeQ = useQuery({ queryKey: ["file-tree", activeRepo], queryFn: () => api.fileTree(activeRepo) });
  const [open, setOpen] = useState<string[]>([]);
  const [active, setActive] = useState<string | null>(null);

  const fileQ = useQuery({
    queryKey: ["file-read", activeRepo, active],
    queryFn: () => api.fileRead(activeRepo, active!),
    enabled: !!active,
  });

  function openFile(path: string) {
    setOpen((o) => (o.includes(path) ? o : [...o, path]));
    setActive(path);
  }
  function closeFile(path: string) {
    setOpen((o) => {
      const next = o.filter((p) => p !== path);
      if (active === path) setActive(next[next.length - 1] ?? null);
      return next;
    });
  }

  function downloadActive() {
    if (!active || !fileQ.data) return;
    const blob = new Blob([fileQ.data.content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = base(active);
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow={`Repository · ${activeRepo}`} title="Codebase">
        {active && (
          <div className="flex items-center gap-3">
            <span className="num text-xs text-muted">{active}</span>
            <button
              onClick={downloadActive}
              disabled={!fileQ.data}
              className="flex items-center gap-1.5 rounded-md border border-line px-2 py-1 text-xs text-ink-soft transition-colors hover:bg-paper-sunk disabled:opacity-40"
              title={`Download ${base(active)}`}
            >
              <Download size={12} />
              Export
            </button>
          </div>
        )}
      </PageHeader>

      <div className="grid min-h-0 flex-1 grid-cols-[260px_1fr] overflow-hidden">
        <nav className="min-h-0 overflow-y-auto border-r border-line bg-panel-2 py-2">
          {treeQ.isLoading ? (
            <CenteredLoading label="Reading the tree" />
          ) : treeQ.error ? (
            <CenteredError message={(treeQ.error as Error).message} onRetry={() => treeQ.refetch()} />
          ) : (
            <Tree nodes={treeQ.data ?? []} depth={0} onOpen={openFile} active={active} />
          )}
        </nav>

        <div className="flex min-h-0 min-w-0 flex-col">
          {open.length > 0 && (
            <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-line bg-panel px-2 py-1.5">
              {open.map((p) => (
                <button
                  key={p}
                  onClick={() => setActive(p)}
                  className={`group flex shrink-0 items-center gap-2 rounded-md px-2.5 py-1 text-xs transition-colors ${
                    active === p ? "bg-signal-wash text-signal" : "text-ink-soft hover:bg-paper-sunk"
                  }`}
                >
                  <FileCode size={13} />
                  <span className="num">{base(p)}</span>
                  <X
                    size={12}
                    className="text-faint opacity-0 transition-opacity hover:text-ink group-hover:opacity-100"
                    onClick={(e) => {
                      e.stopPropagation();
                      closeFile(p);
                    }}
                  />
                </button>
              ))}
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-auto bg-panel-2">
            {!active ? (
              <CenteredEmpty title="Select a file">
                Browse the real repository on the left. Files open here with syntax highlighting.
              </CenteredEmpty>
            ) : fileQ.isLoading ? (
              <CenteredLoading label="Opening file" />
            ) : fileQ.error ? (
              <CenteredError message={(fileQ.error as Error).message} onRetry={() => fileQ.refetch()} />
            ) : (
              <CodeView code={fileQ.data!.content} language={fileQ.data!.language} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Tree({
  nodes,
  depth,
  onOpen,
  active,
}: {
  nodes: FileTreeNode[];
  depth: number;
  onOpen: (path: string) => void;
  active: string | null;
}) {
  return (
    <ul>
      {nodes.map((node) =>
        node.type === "dir" ? (
          <DirRow key={node.path} node={node} depth={depth} onOpen={onOpen} active={active} />
        ) : (
          <li key={node.path}>
            <button
              onClick={() => onOpen(node.path)}
              style={{ paddingLeft: 8 + depth * 14 }}
              className={`flex w-full items-center gap-2 py-1 pr-2 text-left text-[13px] transition-colors ${
                active === node.path ? "bg-signal-wash text-signal" : "text-ink-soft hover:bg-paper-sunk"
              }`}
            >
              <FileCode size={14} className="shrink-0 text-faint" />
              {/* Proportional, not mono: trees are scanned, not aligned, and Geist fits noticeably
                  more of a long filename in the same rail. Mono stays where character alignment
                  actually earns it — the path breadcrumb and the code itself. */}
              <span className="truncate">{node.name}</span>
            </button>
          </li>
        ),
      )}
    </ul>
  );
}

function DirRow({
  node,
  depth,
  onOpen,
  active,
}: {
  node: FileTreeNode;
  depth: number;
  onOpen: (path: string) => void;
  active: string | null;
}) {
  const [open, setOpen] = useState(depth < 1);
  return (
    <li>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{ paddingLeft: 8 + depth * 14 }}
        className="flex w-full items-center gap-1.5 py-1 pr-2 text-left text-[13px] text-ink transition-colors hover:bg-paper-sunk"
      >
        <ChevronRight size={13} className={`shrink-0 text-faint transition-transform ${open ? "rotate-90" : ""}`} />
        {open ? <FolderOpen size={14} className="shrink-0 text-muted" /> : <Folder size={14} className="shrink-0 text-muted" />}
        <span className="truncate font-medium">{node.name}</span>
      </button>
      {open && node.children && (
        <Tree nodes={node.children} depth={depth + 1} onOpen={onOpen} active={active} />
      )}
    </li>
  );
}
