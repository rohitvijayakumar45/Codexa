"use client";

import { useMemo, useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api, type GraphEdge } from "@/lib/api";
import { useRepoStore } from "@/lib/repo-store";
import { PageHeader } from "@/components/shell/PageHeader";
import { CenteredError, CenteredLoading } from "@/components/shell/States";
import { EASE_OUT } from "@/components/ui/primitives";

const edgeActive = (e: GraphEdge, t: number) =>
  Date.parse(e.valid_from) <= t && (e.valid_to == null || Date.parse(e.valid_to) > t);

export default function TimeMachinePage() {
  const activeRepo = useRepoStore((s) => s.activeRepo);
  const timelineQ = useQuery({ queryKey: ["timeline"], queryFn: api.timeline });
  const edgesQ = useQuery({
    queryKey: ["edges", "all", activeRepo],
    queryFn: () => api.allEdges(activeRepo),
  });
  const eventsQ = useQuery({ queryKey: ["events"], queryFn: () => api.events(120) });

  const startMs = timelineQ.data?.starts_at ? Date.parse(timelineQ.data.starts_at) : null;
  const endMs = timelineQ.data?.ends_at ? Date.parse(timelineQ.data.ends_at) : null;
  const [t, setT] = useState<number | null>(null);
  useEffect(() => {
    if (endMs != null && t == null) setT(endMs);
  }, [endMs, t]);

  const edges = edgesQ.data ?? [];
  const now = t ?? endMs ?? Date.now();
  const atMax = endMs != null && now >= endMs;

  const { activeCount, nodeCount } = useMemo(() => {
    const active = edges.filter((e) => edgeActive(e, now));
    const nodes = new Set<string>();
    active.forEach((e) => {
      nodes.add(e.from_node_id);
      nodes.add(e.to_node_id);
    });
    return { activeCount: active.length, nodeCount: nodes.size };
  }, [edges, now]);

  const series = useMemo(() => {
    if (startMs == null || endMs == null) return [];
    const N = 64;
    return Array.from({ length: N }, (_, i) => {
      const time = startMs + ((endMs - startMs) * i) / (N - 1);
      return { time, count: edges.filter((e) => edgeActive(e, time)).length };
    });
  }, [edges, startMs, endMs]);

  const isLoading = timelineQ.isLoading || edgesQ.isLoading;
  const error = timelineQ.error ?? edgesQ.error;

  if (isLoading)
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Replay" title="Time machine" />
        <CenteredLoading label="Rewinding the graph" />
      </div>
    );
  if (error)
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Replay" title="Time machine" />
        <CenteredError message={(error as Error).message} onRetry={() => edgesQ.refetch()} />
      </div>
    );

  const label = atMax
    ? "now"
    : new Date(now).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  const recentEvents = (eventsQ.data ?? []).slice(0, 40);

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow="Replay" title="Time machine" />

      <div className="grid min-h-0 flex-1 grid-rows-[auto_1fr] overflow-hidden">
        <div className="border-b border-line bg-panel px-8 py-7">
          <div className="mx-auto max-w-3xl">
            <div className="flex items-end justify-between">
              <div>
                <span className="status-line">Viewing the graph at</span>
                <p className="display mt-1 text-2xl font-semibold text-ink">{label}</p>
              </div>
              <div className="flex gap-8">
                <Stat value={nodeCount} label="nodes" />
                <Stat value={activeCount} label="relations" />
              </div>
            </div>

            <GrowthChart series={series} startMs={startMs!} endMs={endMs!} now={now} />

            {startMs != null && endMs != null && t != null && (
              <input
                type="range"
                min={startMs}
                max={endMs}
                step={Math.max((endMs - startMs) / 600, 1)}
                value={t}
                onChange={(e) => setT(Number(e.target.value))}
                aria-label="Scrub history"
                className="mt-4 w-full accent-signal"
              />
            )}
            <div className="mt-1 flex justify-between">
              <span className="status-line">{startMs ? new Date(startMs).toLocaleDateString() : ""}</span>
              {!atMax && (
                <button onClick={() => endMs != null && setT(endMs)} className="text-xs text-signal hover:text-ink">
                  jump to now
                </button>
              )}
              <span className="status-line">{endMs ? new Date(endMs).toLocaleDateString() : ""}</span>
            </div>
          </div>
        </div>

        <div className="min-h-0 overflow-y-auto px-8 py-6">
          <div className="mx-auto max-w-3xl">
            <span className="status-line">System ledger</span>
            <ul className="mt-3 divide-y divide-line">
              {recentEvents.map((ev) => (
                <li key={ev.id} className="flex items-center gap-4 py-2.5">
                  <span className="num w-28 shrink-0 text-[11px] text-faint">
                    {new Date(ev.occurred_at).toLocaleTimeString()}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm text-ink-soft">{ev.summary}</span>
                  <span className="status-line !tracking-[0.08em] shrink-0">
                    {ev.event_type.split(".").slice(-1)[0]}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="flex flex-col items-end">
      <motion.span
        key={value}
        initial={{ opacity: 0.4, y: -3 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: EASE_OUT }}
        className="num text-2xl font-medium leading-none text-ink"
      >
        {value}
      </motion.span>
      <span className="status-line mt-1">{label}</span>
    </div>
  );
}

function GrowthChart({
  series,
  startMs,
  endMs,
  now,
}: {
  series: { time: number; count: number }[];
  startMs: number;
  endMs: number;
  now: number;
}) {
  if (series.length < 2) return null;
  const W = 100;
  const H = 34;
  const max = Math.max(...series.map((s) => s.count), 1);
  const pts = series.map((s, i) => {
    const x = (i / (series.length - 1)) * W;
    const y = H - (s.count / max) * H;
    return [x, y] as const;
  });
  const line = pts.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `0,${H} ${line} ${W},${H}`;
  const nowX = ((now - startMs) / (endMs - startMs)) * W;

  return (
    <div className="mt-6">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-16 w-full">
        <polygon points={area} fill="var(--color-signal-wash)" />
        <polyline points={line} fill="none" stroke="var(--color-signal)" strokeWidth="0.7" vectorEffect="non-scaling-stroke" />
        <line x1={nowX} y1="0" x2={nowX} y2={H} stroke="var(--color-ink)" strokeWidth="0.6" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}
