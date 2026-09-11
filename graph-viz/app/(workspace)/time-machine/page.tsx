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
  Time machine — laid out like the Usage page (stat row, one chart section, two ranked columns, a
  recent-activity list), with the graph-growth line chart in place of Usage's daily bars.

  The window is the active repository's own history (its earliest relation, e.g. its first commit,
  to now), narrowed by the range control. Scrubbing the slider views the graph at an earlier moment;
  the stats and the ledger follow it.
*/

const DAY = 86_400_000;
const POINTS = 60;
const RANGES = [
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
  { label: "All history", days: undefined },
] as const;

const edgeActive = (e: GraphEdge, t: number) =>
  Date.parse(e.valid_from) <= t && (e.valid_to == null || Date.parse(e.valid_to) > t);

const category = (eventType: string) => eventType.split(".")[0] || eventType;
const verb = (eventType: string) => eventType.split(".").slice(-1)[0].replace(/_/g, " ");

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function fmtTime(ms: number, refMs: number) {
  const d = new Date(ms);
  const sameDay = new Date(refMs).toDateString() === d.toDateString();
  return sameDay
    ? d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

const shortDate = (ms: number) => new Date(ms).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const isoDate = (ms: number) => new Date(ms).toISOString().slice(0, 10);

type LedgerGroup = { id: string; ev: EventRecord; count: number; latestMs: number };

/** Consecutive events with the same type and summary become one row with a count. */
function groupLedger(events: EventRecord[]): LedgerGroup[] {
  const out: LedgerGroup[] = [];
  for (const ev of events) {
    const last = out[out.length - 1];
    if (last && last.ev.event_type === ev.event_type && last.ev.summary === ev.summary) last.count++;
    else out.push({ id: ev.id, ev, count: 1, latestMs: Date.parse(ev.occurred_at) });
  }
  return out;
}

/** "calls relation formed" / "Decision · React for the UI" -> the kind of event, for the By-event column. */
function eventKind(ev: EventRecord): string {
  if (ev.event_type === "graph.edge.created") return ev.summary.replace(/ relation formed$/, "") + " relations";
  if (ev.event_type === "graph.node.created") return `${ev.summary.split(" · ")[0]} nodes`;
  return verb(ev.event_type);
}

export default function TimeMachinePage() {
  const activeRepo = useRepoStore((s) => s.activeRepo);
  const [range, setRange] = useState<(typeof RANGES)[number]>(RANGES[3]);
  // null = pinned to "now", so the view follows the end of the window as it moves.
  const [picked, setPicked] = useState<number | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [allSnaps, setAllSnaps] = useState(false);
  const [ledgerLimit, setLedgerLimit] = useState(40);

  const timelineQ = useQuery({ queryKey: ["timeline"], queryFn: api.timeline });
  const edgesQ = useQuery({ queryKey: ["edges", "all", activeRepo], queryFn: () => api.allEdges(activeRepo) });
  const eventsQ = useQuery({ queryKey: ["events", 300], queryFn: () => api.events(300), refetchInterval: 10_000 });
  const snapsQ = useQuery({ queryKey: ["snapshots"], queryFn: api.snapshots, refetchInterval: 30_000 });

  const edges = useMemo(() => edgesQ.data ?? [], [edgesQ.data]);
  const tlStart = timelineQ.data?.starts_at ? Date.parse(timelineQ.data.starts_at) : null;
  const tlEnd = timelineQ.data?.ends_at ? Date.parse(timelineQ.data.ends_at) : null;

  // The repository's own span: its earliest relation to now, narrowed by the range control.
  const window_ = useMemo(() => {
    if (tlEnd == null) return null;
    let first = Infinity;
    let end = tlEnd;
    for (const e of edges) {
      const t = Date.parse(e.valid_from);
      if (!Number.isFinite(t)) continue;
      if (t < first) first = t;
      if (t > end) end = t;
    }
    if (!Number.isFinite(first)) first = tlStart ?? end - 30 * DAY;
    let start = range.days ? end - range.days * DAY : first;
    if (end - start < DAY) start = end - 30 * DAY;
    return { start, end };
  }, [edges, tlStart, tlEnd, range]);
  const startMs = window_?.start ?? null;
  const endMs = window_?.end ?? null;
  const now = endMs == null ? 0 : Math.min(endMs, Math.max(startMs ?? endMs, picked ?? endMs));
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
    return Array.from({ length: POINTS }, (_, i) => {
      const time = startMs + ((endMs - startMs) * i) / (POINTS - 1);
      return { time, count: edges.filter((e) => edgeActive(e, time)).length };
    });
  }, [edges, startMs, endMs]);

  const events = useMemo(() => eventsQ.data ?? [], [eventsQ.data]);
  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const ev of events) counts.set(category(ev.event_type), (counts.get(category(ev.event_type)) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [events]);
  const groups = useMemo(
    () => groupLedger(events.filter((ev) => filter === "all" || category(ev.event_type) === filter)),
    [events, filter],
  );
  const kindRows = useMemo(() => {
    const counts = new Map<string, number>();
    for (const ev of events) counts.set(eventKind(ev), (counts.get(eventKind(ev)) ?? 0) + 1);
    const entries = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
    const max = Math.max(1, ...entries.map(([, n]) => n));
    return entries.map(([kind, n]) => ({ kind, n, pct: (n / max) * 100 }));
  }, [events]);
  const snapshots = useMemo(
    () => [...(snapsQ.data ?? [])].sort((a, b) => Date.parse(b.at) - Date.parse(a.at)),
    [snapsQ.data],
  );

  const isLoading = timelineQ.isLoading || edgesQ.isLoading;
  const error = timelineQ.error ?? edgesQ.error;

  const header = (
    <PageHeader eyebrow={`Replay · ${activeRepo}`} title="Time machine">
      <span className="status-line hidden sm:inline">Scrub the chart to view the graph at any moment</span>
      <div className="flex items-center gap-1 rounded-lg border border-line bg-panel-2 p-0.5">
        {RANGES.map((r) => (
          <button
            key={r.label}
            onClick={() => {
              setRange(r);
              setPicked(null);
            }}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              r.label === range.label ? "bg-panel text-ink shadow-sm" : "text-muted hover:text-ink"
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>
    </PageHeader>
  );

  if (isLoading)
    return (
      <div className="flex h-full flex-col">
        {header}
        <CenteredLoading label="Rewinding the graph" />
      </div>
    );
  if (error)
    return (
      <div className="flex h-full flex-col">
        {header}
        <CenteredError message={(error as Error).message} onRetry={() => edgesQ.refetch()} />
      </div>
    );

  const refMs = endMs ?? now;
  const shownSnaps = allSnaps ? snapshots : snapshots.slice(0, 8);
  const futureCount = atMax ? 0 : groups.filter((g) => g.latestMs > now).reduce((s, g) => s + g.count, 0);
  const pick = (s: SnapshotMarker) => {
    const at = Date.parse(s.at);
    if (startMs != null && at < startMs) setRange(RANGES[3]);
    setPicked(endMs != null && at >= endMs ? null : at);
  };

  return (
    <div className="flex h-full flex-col">
      {header}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-8 py-10">
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            <Stat
              label="viewing"
              value={atMax ? "Now" : shortDate(now)}
              sub={atMax ? undefined : new Date(now).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
            />
            <Stat label="connected nodes" value={fmt(nodeCount)} />
            <Stat label="relations" value={fmt(activeCount)} accent />
            <Stat label="snapshots" value={fmt(snapshots.length)} sub={`${fmt(events.length)} recent events`} />
          </div>

          {startMs != null && endMs != null && series.length > 1 ? (
            <div className="mt-10">
              <div className="flex items-baseline justify-between gap-4">
                <span className="status-line">Graph growth</span>
                {!atMax ? (
                  <button onClick={() => setPicked(null)} className="text-xs font-medium text-signal underline-offset-4 hover:underline">
                    Jump to now
                  </button>
                ) : null}
              </div>
              <GrowthChart series={series} now={now} startMs={startMs} endMs={endMs} />
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
                className="themed-range mt-3"
                style={{ "--p": `${((now - startMs) / Math.max(1, endMs - startMs)) * 100}%` } as React.CSSProperties}
              />
              <div className="mt-1.5 flex justify-between">
                <span className="status-line">{isoDate(startMs)}</span>
                <span className="status-line">{isoDate(endMs)}</span>
              </div>
            </div>
          ) : null}

          <div className="mt-12 grid gap-12 md:grid-cols-2">
            <div>
              <span className="status-line">Snapshots</span>
              <div className="mt-4 space-y-4">
                {shownSnaps.map((s, i) => (
                  <SnapshotBar
                    key={`${s.repository}-${s.at}-${i}`}
                    s={s}
                    index={i}
                    active={!atMax && Math.abs(Date.parse(s.at) - now) < 1000}
                    onPick={() => pick(s)}
                  />
                ))}
                {snapshots.length === 0 ? <p className="text-sm text-muted">No ingestions recorded.</p> : null}
              </div>
              {snapshots.length > 8 ? (
                <button onClick={() => setAllSnaps((v) => !v)} className="mt-4 text-xs text-muted underline-offset-4 hover:text-ink hover:underline">
                  {allSnaps ? "Show fewer" : `Show all ${snapshots.length}`}
                </button>
              ) : null}
            </div>
            <div>
              <span className="status-line">By event</span>
              <div className="mt-4 space-y-4">
                {kindRows.map((row, i) => (
                  <RankBar key={row.kind} label={row.kind} value={`${fmt(row.n)} event${row.n === 1 ? "" : "s"}`} pct={row.pct} index={i} />
                ))}
                {kindRows.length === 0 ? <p className="text-sm text-muted">Nothing recorded yet.</p> : null}
              </div>
            </div>
          </div>

          <div className="mt-14">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="status-line">
                System ledger
                {futureCount ? ` · ${futureCount} after the viewed moment` : ""}
              </span>
              <div className="flex flex-wrap gap-1 rounded-lg border border-line bg-panel-2 p-0.5" role="tablist" aria-label="Filter the ledger">
                {[["all", events.length] as const, ...categories].map(([key, n]) => (
                  <button
                    key={key}
                    role="tab"
                    aria-selected={filter === key}
                    onClick={() => setFilter(key)}
                    className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                      filter === key ? "bg-panel text-ink shadow-sm" : "text-muted hover:text-ink"
                    }`}
                  >
                    {key} <span className="num opacity-60">{n}</span>
                  </button>
                ))}
              </div>
            </div>
            {groups.length === 0 ? (
              <p className="mt-4 text-sm text-muted">Nothing recorded yet.</p>
            ) : (
              <ul className="mt-3 divide-y divide-line">
                {groups.slice(0, ledgerLimit).map((g) => (
                  <li key={g.id} className={`flex items-center gap-4 py-2.5 text-sm transition-opacity ${!atMax && g.latestMs > now ? "opacity-40" : ""}`}>
                    <span className="num w-24 shrink-0 text-[11px] text-faint">{fmtTime(g.latestMs, refMs)}</span>
                    <span className="min-w-0 flex-1 truncate text-ink-soft" title={g.ev.summary}>
                      {g.ev.summary}
                    </span>
                    {g.count > 1 ? <span className="num shrink-0 text-[11px] text-muted">×{g.count}</span> : null}
                    <span className="num shrink-0 text-[10.5px] text-faint">
                      {category(g.ev.event_type)} · {verb(g.ev.event_type)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {groups.length > ledgerLimit ? (
              <button onClick={() => setLedgerLimit((n) => n + 60)} className="mt-3 text-xs text-muted underline-offset-4 hover:text-ink hover:underline">
                Show more
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div>
      <span className={`num text-2xl font-medium leading-none ${accent ? "text-signal" : "text-ink"}`}>{value}</span>
      <p className="status-line mt-1.5">{label}</p>
      {sub && <p className="num mt-0.5 text-[10.5px] text-faint">{sub}</p>}
    </div>
  );
}

/** The graph-growth line, in the Usage chart's frame: faint per-period columns (hover for the count),
    the area in the signal wash, the line in the signal colour, and a marker at the viewed moment. */
function GrowthChart({
  series,
  now,
  startMs,
  endMs,
}: {
  series: { time: number; count: number }[];
  now: number;
  startMs: number;
  endMs: number;
}) {
  // Square-root height: an ingest adds thousands of relations at once, which on a linear scale
  // flattens every earlier step of the repository's history into the baseline.
  const max = Math.sqrt(Math.max(1, ...series.map((s) => s.count)));
  const n = series.length;
  const pts = series.map((s, i) => [(i / (n - 1)) * 100, 100 - (Math.sqrt(s.count) / max) * 92] as const);
  const line = pts.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `0,100 ${line} 100,100`;
  const nowX = ((now - startMs) / Math.max(1, endMs - startMs)) * 100;
  return (
    <div className="mt-4">
      <div className="relative h-32">
        <div className="absolute inset-0 flex gap-[1px]">
          {series.map((s) => (
            <div key={s.time} className="group relative flex-1 rounded-[2px] bg-paper-sunk">
              <div className="pointer-events-none absolute -top-8 left-1/2 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-line bg-panel px-2 py-1 text-[10px] text-ink shadow-md group-hover:block">
                {isoDate(s.time)}: {fmt(s.count)} relations
              </div>
            </div>
          ))}
        </div>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
          <motion.polygon
            points={area}
            style={{ fill: "color-mix(in srgb, var(--color-signal) 30%, transparent)" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, ease: EASE_OUT }}
          />
          <polyline points={line} fill="none" stroke="var(--color-signal)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          <line x1={nowX} x2={nowX} y1={0} y2={100} stroke="var(--color-ink)" strokeOpacity={0.55} strokeWidth={1} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
        </svg>
      </div>
    </div>
  );
}

function RankBar({ label, value, pct, index }: { label: string; value: string; pct: number; index: number }) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="truncate text-sm text-ink-soft">{label}</span>
        <span className="num shrink-0 text-xs text-muted">{value}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-paper-sunk">
        <motion.div
          className="h-full rounded-full bg-signal"
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(2, pct)}%` }}
          transition={{ duration: 0.7, delay: 0.1 + index * 0.04, ease: EASE_OUT }}
        />
      </div>
    </div>
  );
}

function SnapshotBar({ s, index, active, onPick }: { s: SnapshotMarker; index: number; active: boolean; onPick: () => void }) {
  const score = Math.round(s.score * 100);
  return (
    <button onClick={onPick} className={`block w-full rounded-md text-left ${active ? "ring-1 ring-signal/50 ring-offset-4 ring-offset-panel" : ""}`} title={`View the graph at ${new Date(s.at).toLocaleString()}`}>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="truncate text-sm text-ink-soft">{s.repository}</span>
        <span className="num shrink-0 text-xs text-muted">
          {score} · {s.files} file{s.files === 1 ? "" : "s"}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-paper-sunk">
        <motion.div
          className="h-full rounded-full bg-signal"
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(2, score)}%` }}
          transition={{ duration: 0.7, delay: 0.1 + index * 0.04, ease: EASE_OUT }}
        />
      </div>
    </button>
  );
}
