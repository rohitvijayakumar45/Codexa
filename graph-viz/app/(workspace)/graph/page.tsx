"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { api, type GraphEdge, type GraphNode } from "@/lib/api";
import { useRepoStore } from "@/lib/repo-store";
import { FAMILY_META, NODE_STYLE, STATE_ACCENT, nodeLabel, nodeRadius, type NodeFamily } from "@/lib/graph-visual";
import type { SceneEdge, SceneNode } from "@/components/graph/GraphScene";
import { Inspector } from "@/components/graph/Inspector";
import { GraphSearch } from "@/components/graph/GraphSearch";
import { Mark } from "@/components/shell/Mark";
import { Button } from "@/components/ui/primitives";

const GraphScene = dynamic(() => import("@/components/graph/GraphScene").then((m) => m.GraphScene), {
  ssr: false,
});

const SURFACE =
  "radial-gradient(circle at 1px 1px, rgba(26,26,24,0.045) 1px, transparent 0) 0 0 / 27px 27px, " +
  "radial-gradient(38% 42% at 14% 12%, rgba(99,102,241,0.10) 0%, transparent 60%), " +
  "radial-gradient(34% 38% at 90% 20%, rgba(244,63,94,0.08) 0%, transparent 60%), " +
  "radial-gradient(40% 44% at 78% 92%, rgba(245,158,11,0.08) 0%, transparent 60%), " +
  "radial-gradient(120% 100% at 50% 18%, #fffffe 0%, #f5f3ef 52%, #ecebe6 100%)";

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

function seedPosition(i: number, n: number): [number, number, number] {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const y = 1 - (i / Math.max(n - 1, 1)) * 2;
  const r = Math.sqrt(Math.max(1 - y * y, 0));
  const theta = golden * i;
  const radius = 11;
  return [Math.cos(theta) * r * radius, y * radius, Math.sin(theta) * r * radius];
}

const edgeActive = (e: GraphEdge, t: number) =>
  Date.parse(e.valid_from) <= t && (e.valid_to == null || Date.parse(e.valid_to) > t);

// Thin data owner: runs the queries and handles loading/empty/error. The graph view (with its own
// large set of memo hooks) only mounts once data is ready, so react-query's internal hook count
// can't shift downstream hook order between the loading and loaded renders.
export default function GraphPage() {
  const activeRepo = useRepoStore((s) => s.activeRepo);
  const timelineQuery = useQuery({ queryKey: ["timeline"], queryFn: api.timeline });
  const nodesQuery = useQuery({ queryKey: ["nodes", activeRepo], queryFn: () => api.nodes(activeRepo) });
  const edgesQuery = useQuery({
    queryKey: ["edges", "all", activeRepo],
    queryFn: () => api.allEdges(activeRepo),
  });

  const isLoading = timelineQuery.isLoading || nodesQuery.isLoading || edgesQuery.isLoading;
  const error = timelineQuery.error ?? nodesQuery.error ?? edgesQuery.error;
  const nodes = nodesQuery.data ?? [];
  const edges = edgesQuery.data ?? [];
  const startMs = timelineQuery.data?.starts_at ? Date.parse(timelineQuery.data.starts_at) : null;
  const endMs = timelineQuery.data?.ends_at ? Date.parse(timelineQuery.data.ends_at) : null;

  const ready = !isLoading && !error && nodes.length > 0 && startMs != null && endMs != null;

  return (
    <div className="flex h-full flex-col">
      {ready ? (
        <GraphView nodes={nodes} edges={edges} startMs={startMs!} endMs={endMs!} />
      ) : (
        <>
          <Header nodeCount={0} totalNodes={nodes.length} edgeCount={0} atMax />
          <div className="relative min-h-0 flex-1" style={{ background: SURFACE }}>
            {isLoading && <LoadingState />}
            {error && <ErrorState message={(error as Error).message} onRetry={() => nodesQuery.refetch()} />}
            {!isLoading && !error && nodes.length === 0 && <EmptyState />}
          </div>
        </>
      )}
    </div>
  );
}

function GraphView({
  nodes,
  edges,
  startMs,
  endMs,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  startMs: number;
  endMs: number;
}) {
  const reducedMotion = useReducedMotion();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [timeMs, setTimeMs] = useState<number>(endMs);
  const atMax = timeMs >= endMs;
  const t = timeMs;

  const nodesById = useMemo(() => new Map(nodes.map((n) => [n.id, n] as const)), [nodes]);
  const indexById = useMemo(() => new Map(nodes.map((n, i) => [n.id, i] as const)), [nodes]);

  const degree = useMemo(() => {
    const d = new Map<string, number>();
    for (const e of edges) {
      d.set(e.from_node_id, (d.get(e.from_node_id) ?? 0) + 1);
      d.set(e.to_node_id, (d.get(e.to_node_id) ?? 0) + 1);
    }
    return d;
  }, [edges]);

  const sceneNodes: SceneNode[] = useMemo(
    () =>
      nodes.map((n, i) => ({
        id: n.id,
        color: NODE_STYLE[n.node_type].color,
        radius: nodeRadius(n.node_type, degree.get(n.id) ?? 0),
        label: nodeLabel(n.properties, n.stable_id),
        seed: seedPosition(i, nodes.length),
      })),
    [nodes, degree],
  );

  const sceneEdges: SceneEdge[] = useMemo(() => {
    const out: SceneEdge[] = [];
    for (const e of edges) {
      const from = indexById.get(e.from_node_id);
      const to = indexById.get(e.to_node_id);
      if (from == null || to == null) continue;
      out.push({
        from,
        to,
        confidence: e.confidence,
        source: e.source_type,
        validFrom: Date.parse(e.valid_from),
        validTo: e.valid_to ? Date.parse(e.valid_to) : null,
      });
    }
    return out;
  }, [edges, indexById]);

  // Header + inspector reflect state at the viewed time.
  const activeEdges = useMemo(() => edges.filter((e) => edgeActive(e, t)), [edges, t]);
  const presentNodeCount = useMemo(() => {
    const s = new Set<string>();
    for (const e of activeEdges) {
      s.add(e.from_node_id);
      s.add(e.to_node_id);
    }
    return s.size;
  }, [activeEdges]);

  const selectedNode = selectedId ? (nodesById.get(selectedId) ?? null) : null;
  const selectedEdges = useMemo(
    () =>
      selectedId
        ? activeEdges.filter((e) => e.from_node_id === selectedId || e.to_node_id === selectedId)
        : [],
    [selectedId, activeEdges],
  );

  const layoutKey = useMemo(() => nodes.map((n) => n.id).join(","), [nodes]);
  const activeTypes = useMemo(() => new Set(nodes.map((n) => n.node_type)), [nodes]);

  return (
    <>
      <Header
        nodeCount={presentNodeCount}
        totalNodes={nodes.length}
        edgeCount={activeEdges.length}
        atMax={atMax}
      />

      <div className="relative min-h-0 flex-1" style={{ background: SURFACE }}>
        <GraphScene
          nodes={sceneNodes}
          edges={sceneEdges}
          selectedId={selectedId}
          hoveredId={hoveredId}
          timeMs={t}
          reducedMotion={reducedMotion}
          layoutKey={layoutKey}
          onHover={setHoveredId}
          onSelect={setSelectedId}
        />
        <FamilyLegend activeTypes={activeTypes} />
        <GraphSearch nodes={nodes} onSelect={setSelectedId} />
        <Inspector
          node={selectedNode}
          edges={selectedEdges}
          nodesById={nodesById}
          onClose={() => setSelectedId(null)}
        />
        <Scrubber
          startMs={startMs}
          endMs={endMs}
          valueMs={timeMs}
          atMax={atMax}
          onChange={setTimeMs}
          onReset={() => setTimeMs(endMs)}
        />
      </div>
    </>
  );
}

function Header({
  nodeCount,
  totalNodes,
  edgeCount,
  atMax,
}: {
  nodeCount: number;
  totalNodes: number;
  edgeCount: number;
  atMax: boolean;
}) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-line bg-panel px-7">
      <div className="flex flex-col">
        <span className="status-line">Engineering brain</span>
        <h1 className="display text-lg font-semibold leading-tight text-ink">Knowledge graph</h1>
      </div>
      <div className="flex items-center gap-7">
        <Stat label="nodes" value={atMax ? String(totalNodes) : `${nodeCount}/${totalNodes}`} />
        <span className="h-8 w-px bg-line" />
        <Stat label="relations" value={String(edgeCount)} />
      </div>
    </header>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex flex-col items-end">
      <span className="num text-lg font-medium leading-none text-ink">{value}</span>
      <span className="status-line mt-1">{label}</span>
    </span>
  );
}

function FamilyLegend({ activeTypes }: { activeTypes: Set<string> }) {
  const [open, setOpen] = useState(false);
  const families = Object.entries(FAMILY_META) as [NodeFamily, (typeof FAMILY_META)[NodeFamily]][];
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.25, duration: 0.4 }}
      className="absolute left-5 top-5 z-10 w-56 overflow-hidden rounded-xl border border-line bg-panel/85 shadow-sm backdrop-blur-md"
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2.5 text-left"
      >
        <span className="flex items-center gap-2">
          {families.map(([k, f]) => (
            <span key={k} className="h-2.5 w-2.5 rounded-full" style={{ background: f.swatch }} />
          ))}
          <span className="ml-1 text-[11px] font-medium uppercase tracking-wide text-muted">Legend</span>
        </span>
        <ChevronDown
          size={14}
          className={`text-faint transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="space-y-3 border-t border-line px-3 py-3">
              {families.map(([key, f]) => {
                const types = (Object.keys(NODE_STYLE) as (keyof typeof NODE_STYLE)[]).filter(
                  (tp) => NODE_STYLE[tp].family === key && activeTypes.has(tp),
                );
                if (types.length === 0) return null;
                return (
                  <div key={key}>
                    <div className="flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-full" style={{ background: f.swatch }} />
                      <span className="text-[11px] font-medium text-ink">{f.label}</span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-2.5 gap-y-0.5 pl-4">
                      {types.map((tp) => (
                        <span key={tp} className="flex items-center gap-1 text-[10.5px] text-muted">
                          <span
                            className="h-1.5 w-1.5 rounded-full"
                            style={{ background: NODE_STYLE[tp].color }}
                          />
                          {NODE_STYLE[tp].label}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
              <div className="space-y-1 border-t border-line pt-2 text-[10.5px] text-faint">
                <p>
                  <span className="mr-1 inline-block h-1.5 w-3 rounded-full align-middle" style={{ background: STATE_ACCENT }} />
                  teal = recently changed
                </p>
                <p>Edge weight = confidence · dashed = LLM-inferred</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function Scrubber({
  startMs,
  endMs,
  valueMs,
  atMax,
  onChange,
  onReset,
}: {
  startMs: number;
  endMs: number;
  valueMs: number;
  atMax: boolean;
  onChange: (ms: number) => void;
  onReset: () => void;
}) {
  const label = atMax
    ? "now"
    : new Date(valueMs).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  return (
    <div className="absolute bottom-5 left-1/2 z-10 w-[min(620px,calc(100%-2.5rem))] -translate-x-1/2 rounded-xl border border-line bg-panel/90 px-4 py-3 shadow-lg backdrop-blur-md">
      <div className="mb-1.5 flex items-center justify-between text-[11px]">
        <span className="font-medium uppercase tracking-wide text-muted">Time machine</span>
        <span className="flex items-center gap-3">
          <span className="num text-ink">{label}</span>
          {!atMax && (
            <button onClick={onReset} className="text-signal transition-colors hover:text-ink">
              now
            </button>
          )}
        </span>
      </div>
      <input
        type="range"
        min={startMs}
        max={endMs}
        step={Math.max((endMs - startMs) / 500, 1)}
        value={valueMs}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label="Replay graph history"
        className="w-full accent-signal"
      />
      <div className="mt-1 flex justify-between text-[10px] text-faint">
        <span className="num">{new Date(startMs).toLocaleDateString()}</span>
        <span className="num">{new Date(endMs).toLocaleDateString()}</span>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="absolute inset-0 grid place-items-center">
      <div className="flex flex-col items-center gap-5 text-center">
        <div className="animate-pulse">
          <Mark size={40} className="text-ink" />
        </div>
        <p className="status-line">Assembling the engineering brain</p>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="absolute inset-0 grid place-items-center p-6">
      <div className="max-w-md rounded-xl border border-line bg-panel p-6 text-center shadow-sm">
        <h2 className="display text-base font-semibold text-ink">The graph is empty</h2>
        <p className="mt-2 text-sm text-muted">
          The backend responded, but no nodes exist yet. Start the API with seeding enabled to
          populate real data:
        </p>
        <pre className="num mt-3 overflow-x-auto rounded-lg bg-paper-sunk px-3 py-2 text-left text-[11px] text-ink-soft">
          CODEXA_SEED=1 uvicorn backend.main:app
        </pre>
      </div>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="absolute inset-0 grid place-items-center p-6">
      <div className="max-w-md rounded-xl border border-danger/30 bg-panel p-6 text-center shadow-sm">
        <h2 className="display text-base font-semibold text-danger">Can&apos;t load the graph</h2>
        <p className="mt-2 text-sm text-muted">{message}</p>
        <Button onClick={onRetry} className="mt-4">
          Try again
        </Button>
      </div>
    </div>
  );
}
