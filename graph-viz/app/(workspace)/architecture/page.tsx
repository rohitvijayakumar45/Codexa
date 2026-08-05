"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";
import { api, type GraphNode } from "@/lib/api";
import { useRepoStore } from "@/lib/repo-store";
import { PageHeader } from "@/components/shell/PageHeader";
import { CenteredError, CenteredLoading } from "@/components/shell/States";
import { EASE_OUT } from "@/components/ui/primitives";

const MODULE_TYPES = new Set(["File", "Repository"]);
const DEP_TYPES = new Set(["imports", "depends_on"]);

type ArchTrend = Awaited<ReturnType<typeof api.archTrends>>[number];

const CW = 214;
const CH = 66;
const GAP = 26;
const COLS = [30, 360, 690];
const VW = COLS[2] + CW + 30;

function name(node: GraphNode) {
  const path = (node.properties.path as string) ?? (node.properties.name as string) ?? node.stable_id;
  const parts = path.split("/");
  const sub = parts.slice(0, -1).join("/") || ((node.properties.role as string) ?? "");
  return { title: parts[parts.length - 1], sub };
}

export default function ArchitecturePage() {
  const activeRepo = useRepoStore((s) => s.activeRepo);
  const nodesQ = useQuery({ queryKey: ["nodes", activeRepo], queryFn: () => api.nodes(activeRepo) });
  const edgesQ = useQuery({
    queryKey: ["edges", "all", activeRepo],
    queryFn: () => api.allEdges(activeRepo),
  });
  const trendsQ = useQuery({ queryKey: ["arch-trends"], queryFn: api.archTrends });

  const modules = useMemo(
    () => (nodesQ.data ?? []).filter((n) => MODULE_TYPES.has(n.node_type)),
    [nodesQ.data],
  );

  const alertedPaths = useMemo(
    () => (trendsQ.data ?? []).filter((t) => t.alerts.length > 0).map((t) => t.module_path),
    [trendsQ.data],
  );

  const { cards, links, height } = useMemo(() => {
    const ids = new Set(modules.map((m) => m.id));
    const deps = (edgesQ.data ?? []).filter(
      (e) => DEP_TYPES.has(e.edge_type) && e.valid_to == null && ids.has(e.from_node_id) && ids.has(e.to_node_id),
    );
    const indeg = new Map<string, number>();
    const outdeg = new Map<string, number>();
    for (const e of deps) {
      outdeg.set(e.from_node_id, (outdeg.get(e.from_node_id) ?? 0) + 1);
      indeg.set(e.to_node_id, (indeg.get(e.to_node_id) ?? 0) + 1);
    }
    // Layer left→right by dependency role: sources, middle, sinks.
    const colOf = (id: string) => {
      const i = indeg.get(id) ?? 0;
      const o = outdeg.get(id) ?? 0;
      if (i === 0) return 0;
      if (o === 0) return 2;
      return 1;
    };
    const byCol: GraphNode[][] = [[], [], []];
    modules.forEach((m) => byCol[colOf(m.id)].push(m));

    const maxRows = Math.max(1, ...byCol.map((c) => c.length));
    const height = Math.max(360, maxRows * CH + (maxRows - 1) * GAP + 80);

    const pos = new Map<string, { x: number; y: number }>();
    byCol.forEach((col, ci) => {
      const total = col.length * CH + (col.length - 1) * GAP;
      const startY = (height - total) / 2;
      col.forEach((m, ri) => pos.set(m.id, { x: COLS[ci], y: startY + ri * (CH + GAP) }));
    });

    const cards = modules.map((m) => {
      const p = pos.get(m.id)!;
      const path = (m.properties.path as string) ?? "";
      const alerted = alertedPaths.some((ap) => path.startsWith(ap));
      return { node: m, x: p.x, y: p.y, alerted, isRepo: m.node_type === "Repository" };
    });

    const links = deps
      .map((e) => {
        const a = pos.get(e.from_node_id);
        const b = pos.get(e.to_node_id);
        if (!a || !b) return null;
        return {
          x1: a.x + CW,
          y1: a.y + CH / 2,
          x2: b.x,
          y2: b.y + CH / 2,
        };
      })
      .filter(Boolean) as { x1: number; y1: number; x2: number; y2: number }[];

    return { cards, links, height };
  }, [modules, edgesQ.data, alertedPaths]);

  const isLoading = nodesQ.isLoading || edgesQ.isLoading || trendsQ.isLoading;
  const error = nodesQ.error ?? edgesQ.error ?? trendsQ.error;

  if (isLoading)
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Live" title="Architecture" />
        <CenteredLoading label="Tracing module dependencies" />
      </div>
    );
  if (error)
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Live" title="Architecture" />
        <CenteredError message={(error as Error).message} onRetry={() => nodesQ.refetch()} />
      </div>
    );

  const trend = trendsQ.data?.[0] ?? null;

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow="Live" title="Architecture">
        <span className="num text-sm text-muted">{modules.length} modules · {links.length} dependencies</span>
      </PageHeader>

      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[1fr_360px]">
        <div
          className="min-h-0 overflow-auto p-8"
          style={{ background: "radial-gradient(circle at 1px 1px, rgba(26,26,24,0.03) 1px, transparent 0) 0 0 / 27px 27px, linear-gradient(#faf9f6, #f2f0eb)" }}
        >
          <div className="mx-auto max-w-3xl">
            <p className="display text-2xl font-semibold text-ink">Everything connects.</p>
            <p className="mt-1 max-w-md text-sm text-muted">
              Modules drawn as the dependency graph actually flows, left to right.
            </p>

            <svg viewBox={`0 0 ${VW} ${height}`} className="mt-6 w-full" style={{ minWidth: 640 }}>
              <defs>
                <filter id="cardshadow" x="-20%" y="-20%" width="140%" height="160%">
                  <feDropShadow dx="0" dy="6" stdDeviation="8" floodColor="#1a1a18" floodOpacity="0.08" />
                </filter>
              </defs>

              {links.map((l, i) => {
                const dx = Math.max(60, Math.abs(l.x2 - l.x1) * 0.5);
                return (
                  <path
                    key={i}
                    d={`M ${l.x1} ${l.y1} C ${l.x1 + dx} ${l.y1}, ${l.x2 - dx} ${l.y2}, ${l.x2} ${l.y2}`}
                    fill="none"
                    stroke="var(--color-gold)"
                    strokeWidth={1.4}
                    strokeDasharray="4 5"
                    strokeLinecap="round"
                    opacity={0.55}
                    className="motion-safe:animate-[flow_1.1s_linear_infinite]"
                  />
                );
              })}

              {cards.map((c, i) => {
                const { title, sub } = name(c.node);
                const dot = c.alerted ? "var(--color-danger)" : c.isRepo ? "var(--color-ink)" : "var(--color-signal)";
                return (
                  <motion.g
                    key={c.node.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, delay: i * 0.04, ease: EASE_OUT }}
                  >
                    <rect x={c.x} y={c.y} width={CW} height={CH} rx={16} fill="#ffffff" stroke="var(--color-line)" strokeWidth={1} filter="url(#cardshadow)" />
                    <circle cx={c.x + 18} cy={c.y + 24} r={4} fill={dot} />
                    <text x={c.x + 32} y={c.y + 28} style={{ fontSize: 13, fontWeight: 600, fill: "var(--color-ink)" }}>
                      {title}
                    </text>
                    <text x={c.x + 18} y={c.y + 47} style={{ fontSize: 10.5, fontFamily: "var(--font-mono)", fill: "var(--color-faint)" }}>
                      {sub.length > 26 ? `…${sub.slice(-25)}` : sub}
                    </text>
                    {typeof c.node.properties.loc === "number" && (
                      <text x={c.x + CW - 16} y={c.y + 47} textAnchor="end" style={{ fontSize: 10.5, fontFamily: "var(--font-mono)", fill: "var(--color-muted)" }}>
                        {c.node.properties.loc as number} LOC
                      </text>
                    )}
                  </motion.g>
                );
              })}
            </svg>
          </div>
        </div>

        <aside className="border-t border-line bg-panel p-6 lg:border-l lg:border-t-0">
          {trend ? <TrendPanel trend={trend} /> : <p className="text-sm text-muted">No architecture trends recorded.</p>}
        </aside>
      </div>
    </div>
  );
}

function TrendPanel({ trend }: { trend: ArchTrend }) {
  const wanted = ["coupling", "cyclomatic_complexity", "file_churn"];
  const metrics = trend.trends.filter((t) => wanted.includes(t.metric));
  return (
    <div>
      <span className="status-line">Evolution</span>
      <h2 className="display mt-1 text-base font-semibold text-ink">{trend.module_path}</h2>

      <div className="mt-5 space-y-4">
        {metrics.map((m) => {
          const rising = m.slope_per_day > 0;
          return (
            <div key={m.metric} className="flex items-center justify-between border-b border-line pb-3">
              <div>
                <p className="text-sm capitalize text-ink-soft">{m.metric.replace(/_/g, " ")}</p>
                <p className="status-line mt-0.5">
                  {m.first_value.toFixed(2)} → {m.latest_value.toFixed(2)}
                </p>
              </div>
              <span className={`flex items-center gap-1 text-xs ${rising ? "text-warn" : "text-signal"}`}>
                {rising ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                <span className="num">{(m.slope_per_day * 100).toFixed(1)}/d</span>
              </span>
            </div>
          );
        })}
      </div>

      {trend.bottleneck_eta_days != null && (
        <div className="mt-5 rounded-lg bg-gold-wash px-3 py-2.5">
          <p className="status-line" style={{ color: "var(--color-gold)" }}>Projected bottleneck</p>
          <p className="num mt-1 text-lg font-medium text-ink">{Math.round(trend.bottleneck_eta_days)} days</p>
        </div>
      )}

      {trend.alerts.length > 0 && (
        <div className="mt-5">
          <span className="status-line">Alerts</span>
          <ul className="mt-2 space-y-1.5">
            {trend.alerts.map((a) => (
              <li key={a} className="flex items-center gap-2 text-xs text-warn">
                <AlertTriangle size={13} />
                {a.replace(/_/g, " ")}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
