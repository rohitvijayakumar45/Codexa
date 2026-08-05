"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { BookOpen, History, ListChecks, Users, ChevronDown } from "lucide-react";
import { api, type MemoryRecord, type MemoryType } from "@/lib/api";
import { useRepoStore } from "@/lib/repo-store";
import { PageHeader } from "@/components/shell/PageHeader";
import { CenteredError, CenteredLoading, CenteredEmpty } from "@/components/shell/States";
import { EASE_OUT } from "@/components/ui/primitives";

const TYPES: { key: MemoryType; label: string; icon: typeof BookOpen; blurb: string }[] = [
  { key: "semantic", label: "Semantic", icon: BookOpen, blurb: "what the system is and knows" },
  { key: "episodic", label: "Episodic", icon: History, blurb: "events over time" },
  { key: "procedural", label: "Procedural", icon: ListChecks, blurb: "how to build and run" },
  { key: "organizational", label: "Organizational", icon: Users, blurb: "conventions and culture" },
];

export default function MemoryPage() {
  const activeRepo = useRepoStore((s) => s.activeRepo);
  const setActiveRepo = useRepoStore((s) => s.setActiveRepo);

  const reposQ = useQuery({ queryKey: ["memory-repos"], queryFn: api.memoryRepositories });
  const recordsQ = useQuery({
    queryKey: ["memory-records", activeRepo],
    queryFn: () => api.memoryRecords(activeRepo),
  });

  const byType = useMemo(() => {
    const map: Record<MemoryType, MemoryRecord[]> = { semantic: [], episodic: [], procedural: [], organizational: [] };
    for (const r of recordsQ.data ?? []) map[r.memory_type]?.push(r);
    return map;
  }, [recordsQ.data]);

  const repos = reposQ.data ?? [];

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow="Persistent · shared by all models" title="Memory">
        <RepoSelect repos={repos.map((r) => r.repository)} active={activeRepo} onChange={setActiveRepo} />
      </PageHeader>

      {recordsQ.isLoading ? (
        <CenteredLoading label="Recalling memory" />
      ) : recordsQ.error ? (
        <CenteredError message={(recordsQ.error as Error).message} onRetry={() => recordsQ.refetch()} />
      ) : (recordsQ.data ?? []).length === 0 ? (
        <CenteredEmpty title="No memory for this repository yet">
          Load a repository from Chat and a permanent memory is written here automatically.
        </CenteredEmpty>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto grid max-w-5xl gap-6 px-8 py-8 md:grid-cols-2">
            {TYPES.map((t, i) => (
              <MemoryColumn key={t.key} type={t} records={byType[t.key]} index={i} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MemoryColumn({
  type,
  records,
  index,
}: {
  type: (typeof TYPES)[number];
  records: MemoryRecord[];
  index: number;
}) {
  const Icon = type.icon;
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.06, ease: EASE_OUT }}
      className="rounded-2xl border border-line bg-panel p-5"
    >
      <div className="flex items-center gap-2.5">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-paper-sunk text-ink">
          <Icon size={16} strokeWidth={1.75} />
        </span>
        <div>
          <h2 className="text-sm font-semibold text-ink">{type.label}</h2>
          <p className="status-line">{type.blurb}</p>
        </div>
        <span className="num ml-auto text-sm text-faint">{records.length}</span>
      </div>

      <div className="mt-4 space-y-3">
        {records.length === 0 ? (
          <p className="text-xs text-faint">Nothing recorded.</p>
        ) : (
          records.map((r) => (
            <div key={r.id} className="border-t border-line pt-3 first:border-t-0 first:pt-0">
              <p className="text-sm font-medium text-ink">{r.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-muted">{r.content}</p>
              <p className="status-line mt-1.5">{new Date(r.created_at).toLocaleString()}</p>
            </div>
          ))
        )}
      </div>
    </motion.section>
  );
}

function RepoSelect({
  repos,
  active,
  onChange,
}: {
  repos: string[];
  active: string;
  onChange: (r: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const options = repos.includes(active) ? repos : [active, ...repos];
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-lg border border-line-strong px-3 py-1.5 text-sm text-ink transition-colors hover:bg-paper-sunk"
      >
        <span className="num">{active}</span>
        <ChevronDown size={14} className={`text-faint transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-30 w-56 overflow-hidden rounded-xl border border-line bg-panel p-1 shadow-lg">
          {options.map((r) => (
            <button
              key={r}
              onClick={() => {
                onChange(r);
                setOpen(false);
              }}
              className={`num flex w-full items-center rounded-lg px-3 py-2 text-left text-xs transition-colors hover:bg-paper-sunk ${
                r === active ? "bg-signal-wash text-signal" : "text-ink-soft"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
