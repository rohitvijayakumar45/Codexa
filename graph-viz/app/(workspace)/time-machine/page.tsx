"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api, type EventRecord, type GraphEdge, type SnapshotMarker } from "@/lib/api";
import { useRepoStore } from "@/lib/repo-store";
import { PageHeader } from "@/components/shell/PageHeader";
import { CenteredError, CenteredLoading } from "@/components/shell/States";
import { EASE_OUT } from "@/components/ui/primitives";

/*
  Time machine: scrub the graph's history and read the ledger of what happened.

  Layout rule that fixes the old page: the viewing panel is a fixed-height strip, snapshots live in
  their own scrolling column, and the ledger always owns the remaining height. Before, every
  snapshot was a chip in the header, so 30-odd ingested repositories wrapped into a wall that pushed
  the ledger off the bottom of the screen.
*/

const edgeActive = (e: GraphEdge, t: number) =>
  Date.parse(e.valid_from) <= t && (e.valid_to == null || Date.parse(e.valid_to) > t);

const category = (eventType: string) => eventType.split(".")[0] || eventType;
const verb = (eventType: string) => eventType.split(".").slice(-1)[0].replace(/_/g, " ");

function fmtTime(ms: number, refMs: number) {
  const d = new Date(ms);
  const sameDay = new Date(refMs).toDateString() === d.toDateString();
  return sameDay
    ? d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function TimeMachinePage() {
  const activeRepo = useRepoStore((s) => s.activeRepo);
  const timelineQ = useQuery({ queryKey: ["timeline"], queryFn: api.timeline });
  const edgesQ = useQuery({ queryKey: ["edges", "all", activeRepo], queryFn: () => api.allEdges(activeRepo) });
  const eventsQ = useQuery({ queryKey: ["events", 300], queryFn: () => api.events(300), refetchInterval: 10_000 });
  const snapsQ = useQuery({ queryKey: ["snapshots"], queryFn: api.snapshots, refetchInterval: 30_000 });

  const startMs = timelineQ.data?.starts_at ? Date.parse(timelineQ.data.starts_at) : null;
  const endMs = timelineQ.data?.ends_at ? Date.parse(timelineQ.data.ends_at) : null;
  // null = pinned to "now", so the view follows the timeline's end as it moves.
  const [picked, setPicked] = useState<number | null>(null);
  const [filter, setFilter] = useState<string>("all");

  const edges = useMemo(() => edgesQ.data ?? [], [edgesQ.data]);
  const now = picked ?? endMs ?? 0;
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

  const events = useMemo(() => eventsQ.data ?? [], [eventsQ.data]);
  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const ev of events) counts.set(category(ev.event_type), (counts.get(category(ev.event_type)) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [events]);
  const shown = useMemo(
    () => events.filter((ev) => filter === "all" || category(ev.event_type) === filter),
    [events, filter],
  );
  const snapshots = useMemo(
    () => [...(snapsQ.data ?? [])].sort((a, b) => Date.parse(b.at) - Date.parse(a.at)),
    [snapsQ.data],
  );

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

  const label = atMax ? "Now" : new Date(now).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  const refMs = endMs ?? now;
  // The ledger splits at the viewed moment: what had happened by then, and what hadn't yet.
  const futureCount = atMax ? 0 : shown.filter((ev) => Date.parse(ev.occurred_at) > now).length;

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow="Replay" title="Time machine">
        <span className="num text-sm text-muted">
          {snapshots.length} snapshots · {events.length} events
        </span>
      </PageHeader>

      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_320px]">
        <section className="flex min-h-0 flex-col">
          <div className="shrink-0 border-b border-line bg-panel px-8 py-6">
            <div className="mx-auto max-w-3xl">
              <div className="flex items-end justify-between gap-6">
                <div className="min-w-0">
                  <span className="status-line">Viewing the graph at</span>
                  <p className="display mt-1 truncate text-2xl font-semibold text-ink">{label}</p>
                </div>
                <div className="flex shrink-0 gap-8">
                  <Stat value={nodeCount} label="nodes" />
                  <Stat value={activeCount} label="relations" />
                </div>
              </div>

              {startMs != null && endMs != null ? (
                <>
                  <GrowthChart series={series} startMs={startMs} endMs={endMs} now={now} snapshots={snapshots} />
                  <input
                    type="range"
                    min={startMs}
                    max={endMs}
                    step={Math.max((endMs - startMs) / 600, 1)}
                    value={now}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      setPicked(v >= endMs ? null : v);
                    }}
                    aria-label="Scrub history"
                    className="mt-3 w-full accent-[var(--color-ink)]"
                  />
                  <div className="mt-1 flex items-center justify-between">
                    <span className="status-line">{new Date(startMs).toLocaleDateString()}</span>
                    {!atMax ? (
                      <button onClick={() => setPicked(null)} className="text-xs font-medium text-ink underline-offset-4 hover:underline">
                        Jump to now
                      </button>
                    ) : null}
                    <span className="status-line">{new Date(endMs).toLocaleDateString()}</span>
                  </div>
                </>
              ) : null}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-8 py-5">
            <div className="mx-auto max-w-3xl">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="status-line">
                  System ledger · {shown.length}
                  {futureCount ? ` · ${futureCount} after the viewed moment` : ""}
                </span>
                <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Filter the ledger">
                  {[["all", events.length] as const, ...categories].map(([key, n]) => (
                    <button
                      key={key}
                      role="tab"
                      aria-selected={filter === key}
                      onClick={() => setFilter(key)}
                      className={`rounded-md border px-2 py-0.5 text-[11px] transition-colors ${
                        filter === key
                          ? "border-ink bg-ink text-panel"
                          : "border-line text-ink-soft hover:border-line-strong hover:bg-paper-sunk"
                      }`}
                    >
                      {key} <span className="num opacity-70">{n}</span>
                    </button>
                  ))}
                </div>
              </div>
              {shown.length === 0 ? (
                <p className="mt-6 text-sm text-muted">Nothing recorded yet.</p>
              ) : (
                <ul className="mt-3 divide-y divide-line">
                  {shown.map((ev) => (
                    <LedgerRow key={ev.id} ev={ev} refMs={refMs} future={!atMax && Date.parse(ev.occurred_at) > now} />
                  ))}
                </ul>
              )}
            </div>
          </div>
        </section>

        <aside className="hidden min-h-0 flex-col border-l border-line bg-panel lg:flex">
          <div className="shrink-0 border-b border-line px-5 py-4">
            <span className="status-line">Snapshots · {snapshots.length}</span>
            <p className="mt-1 text-xs text-muted">One per repository ingestion. Pick one to view the graph at that moment.</p>
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
            {snapshots.map((s, i) => (
              <SnapshotRow
                key={`${s.repository}-${s.at}-${i}`}
                s={s}
                refMs={refMs}
                active={!atMax && Math.abs(Date.parse(s.at) - now) < 1000}
                onPick={() => {
                  const at = Date.parse(s.at);
                  setPicked(endMs != null && at >= endMs ? null : at);
                }}
              />
            ))}
            {snapshots.length === 0 ? <li className="px-3 py-2 text-xs text-muted">No ingestions recorded.</li> : null}
          </ul>
        </aside>
      </div>
    </div>
  );
}

function LedgerRow({ ev, refMs, future }: { ev: EventRecord; refMs: number; future: boolean }) {
  return (
    <li className={`grid grid-cols-[92px_minmax(0,1fr)_auto] items-center gap-4 py-2.5 transition-opacity ${future ? "opacity-40" : ""}`}>
      <span className="num text-[11px] text-faint">{fmtTime(Date.parse(ev.occurred_at), refMs)}</span>
      <span className="min-w-0 truncate text-sm text-ink-soft" title={ev.summary}>
        {ev.summary}
      </span>
      <span className="status-line shrink-0 !tracking-[0.08em]">
        {category(ev.event_type)} · {verb(ev.event_type)}
      </span>
    </li>
  );
}

function SnapshotRow({
  s,
  refMs,
  active,
  onPick,
}: {
  s: SnapshotMarker;
  refMs: number;
  active: boolean;
  onPick: () => void;
}) {
  const score = Math.round(s.score * 100);
  return (
    <li>
      <button
        onClick={onPick}
        title={new Date(s.at).toLocaleString()}
        className={`grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-lg px-3 py-2 text-left transition-colors ${
          active ? "bg-paper-sunk" : "hover:bg-paper-sunk"
        }`}
      >
        <span className="truncate text-[13px] font-medium text-ink">{s.repository}</span>
        <span className="num text-[11px] text-faint">{fmtTime(Date.parse(s.at), refMs)}</span>
        <span className="flex items-center gap-2">
          <span className="h-1 w-20 overflow-hidden rounded-full bg-line">
            <span className="block h-full rounded-full bg-ink-soft" style={{ width: `${score}%` }} />
          </span>
          <span className="num text-[11px] text-muted">{score}</span>
        </span>
        <span className="num text-[11px] text-muted">
          {s.files} files{s.symbols ? ` · ${s.symbols} sym` : ""}
        </span>
      </button>
    </li>
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
  snapshots,
}: {
  series: { time: number; count: number }[];
  startMs: number;
  endMs: number;
  now: number;
  snapshots: SnapshotMarker[];
}) {
  if (series.length < 2) return null;
  const W = 100;
  const H = 34;
  const span = Math.max(1, endMs - startMs);
  const max = Math.max(...series.map((s) => s.count), 1);
  const pts = series.map((s, i) => [(i / (series.length - 1)) * W, H - (s.count / max) * (H - 2)] as const);
  const line = pts.map(([x, y]) => `${x},${y}`).join(" ");
  const nowX = ((now - startMs) / span) * W;
  const ticks = snapshots.map((s) => ((Date.parse(s.at) - startMs) / span) * W).filter((x) => x >= 0 && x <= W);

  return (
    <div className="relative mt-5">
      <svg viewBox={`0 0 ${W} ${H + 4}`} preserveAspectRatio="none" className="h-16 w-full" aria-hidden>
        <polygon points={`0,${H} ${line} ${W},${H}`} style={{ fill: "color-mix(in srgb, var(--color-ink) 7%, transparent)" }} />
        <polyline points={line} fill="none" stroke="var(--color-ink-soft)" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
        {ticks.map((x, i) => (
          <line key={i} x1={x} x2={x} y1={H + 0.5} y2={H + 4} stroke="var(--color-faint)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        ))}
        <line x1={nowX} y1="0" x2={nowX} y2={H} stroke="var(--color-ink)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
      <span className="status-line absolute -bottom-0.5 right-0 translate-y-full !text-[10px]">ticks = snapshots</span>
    </div>
  );
}
