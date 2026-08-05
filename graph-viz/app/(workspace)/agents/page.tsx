"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { api, type AgentNode } from "@/lib/api";
import { PageHeader } from "@/components/shell/PageHeader";
import { CenteredError, CenteredLoading } from "@/components/shell/States";
import { EASE_OUT } from "@/components/ui/primitives";

const LAYERS = ["Perception", "Understanding", "Planning", "Simulation", "Execution", "Verification", "Learning"];
const COL_W = 190;
const ROW_H = 104;
const PAD = 70;

export default function AgentsPage() {
  const q = useQuery({
    queryKey: ["agents"],
    queryFn: api.agents,
    refetchInterval: 4000,
  });
  const [selected, setSelected] = useState<string | null>(null);

  const agents = q.data?.agents ?? [];
  const activeCount = agents.filter((a) => a.status === "active").length;

  const { positions, width, height } = useMemo(() => {
    const byLayer = new Map<string, AgentNode[]>();
    for (const a of agents) {
      const arr = byLayer.get(a.layer) ?? [];
      arr.push(a);
      byLayer.set(a.layer, arr);
    }
    const pos = new Map<string, { x: number; y: number }>();
    let maxRows = 1;
    LAYERS.forEach((layer, col) => {
      const list = byLayer.get(layer) ?? [];
      maxRows = Math.max(maxRows, list.length);
      list.forEach((a, row) => {
        pos.set(a.id, { x: PAD + col * COL_W, y: PAD + row * ROW_H });
      });
    });
    return { positions: pos, width: PAD * 2 + (LAYERS.length - 1) * COL_W, height: PAD * 2 + (maxRows - 1) * ROW_H };
  }, [agents]);

  if (q.isLoading) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Orchestration" title="Agent network" />
        <CenteredLoading label="Reading agent status" />
      </div>
    );
  }
  if (q.error) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Orchestration" title="Agent network" />
        <CenteredError message={(q.error as Error).message} onRetry={() => q.refetch()} />
      </div>
    );
  }

  const selectedAgent = agents.find((a) => a.id === selected) ?? null;

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow="Orchestration" title="Agent network">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full bg-signal-live opacity-60" style={{ animation: "breathe 2.4s ease-in-out infinite" }} />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-signal" />
          </span>
          <span className="num text-sm font-medium text-ink">{activeCount}</span>
          <span className="status-line">active</span>
        </div>
      </PageHeader>

      <div className="relative min-h-0 flex-1 overflow-auto" style={{ background: "radial-gradient(circle at 1px 1px, rgba(26,26,24,0.035) 1px, transparent 0) 0 0 / 26px 26px, linear-gradient(#faf9f6, #f3f1ec)" }}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="mx-auto block"
          style={{ width: Math.max(width, 700), height, maxWidth: "none" }}
        >
          {/* Layer labels */}
          {LAYERS.map((layer, col) => (
            <text
              key={layer}
              x={PAD + col * COL_W}
              y={26}
              textAnchor="middle"
              className="fill-[color:var(--color-faint)]"
              style={{ fontSize: 10, letterSpacing: 1.5, textTransform: "uppercase", fontFamily: "var(--font-mono)" }}
            >
              {layer}
            </text>
          ))}

          {/* Dependency links */}
          {agents.flatMap((a) =>
            a.depends_on.map((depId) => {
              const from = positions.get(depId);
              const to = positions.get(a.id);
              if (!from || !to) return null;
              const mx = (from.x + to.x) / 2;
              const highlight = selected === a.id || selected === depId;
              return (
                <path
                  key={`${depId}-${a.id}`}
                  d={`M ${from.x} ${from.y} C ${mx} ${from.y}, ${mx} ${to.y}, ${to.x} ${to.y}`}
                  fill="none"
                  stroke={highlight ? "var(--color-signal)" : "var(--color-line-strong)"}
                  strokeWidth={highlight ? 1.8 : 1.1}
                  opacity={selected && !highlight ? 0.3 : 0.9}
                />
              );
            }),
          )}

          {/* Agent nodes */}
          {agents.map((a) => {
            const p = positions.get(a.id);
            if (!p) return null;
            const active = a.status === "active";
            const dimmed = selected && selected !== a.id && !a.depends_on.includes(selected) &&
              !agents.find((x) => x.id === selected)?.depends_on.includes(a.id);
            return (
              <g
                key={a.id}
                transform={`translate(${p.x} ${p.y})`}
                onClick={() => setSelected(a.id === selected ? null : a.id)}
                style={{ cursor: "pointer", opacity: dimmed ? 0.35 : 1, transition: "opacity 0.2s" }}
              >
                {active && (
                  <circle r={26} fill="var(--color-signal)" opacity={0.12} style={{ animation: "breathe 2.6s ease-in-out infinite" }} />
                )}
                <circle
                  r={18}
                  fill={active ? "var(--color-signal)" : "#ffffff"}
                  stroke={active ? "var(--color-signal)" : "var(--color-line-strong)"}
                  strokeWidth={1.5}
                />
                {a.activity_count > 0 && (
                  <text textAnchor="middle" dy={4} style={{ fontSize: 11, fontFamily: "var(--font-mono)", fill: active ? "#fff" : "var(--color-muted)" }}>
                    {a.activity_count}
                  </text>
                )}
                <text textAnchor="middle" y={34} style={{ fontSize: 11, fontWeight: 500, fill: "var(--color-ink)" }}>
                  {a.name}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <AnimatePresence>
        {selectedAgent && <AgentDetail agent={selectedAgent} onClose={() => setSelected(null)} />}
      </AnimatePresence>
    </div>
  );
}

function AgentDetail({ agent, onClose }: { agent: AgentNode; onClose: () => void }) {
  return (
    <motion.aside
      initial={{ x: 24, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 24, opacity: 0 }}
      transition={{ duration: 0.28, ease: EASE_OUT }}
      className="absolute right-4 top-20 z-20 w-80 rounded-xl border border-line bg-panel/95 p-4 shadow-lg backdrop-blur-sm"
    >
      <div className="flex items-start justify-between">
        <div>
          <span className="status-line">{agent.layer}</span>
          <h2 className="display text-[15px] font-semibold text-ink">{agent.name}</h2>
        </div>
        <span className={`flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10.5px] font-medium ${agent.status === "active" ? "bg-signal-wash text-signal" : "bg-paper-sunk text-muted"}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${agent.status === "active" ? "bg-signal" : "bg-faint"}`} />
          {agent.status}
        </span>
      </div>
      <p className="mt-2 text-sm text-muted">{agent.role}</p>
      <dl className="mt-4 space-y-2 border-t border-line pt-3 text-xs">
        <Row label="Events" value={String(agent.activity_count)} />
        <Row label="Last active" value={agent.last_active ? new Date(agent.last_active).toLocaleString() : "—"} />
        <Row label="Now" value={agent.current_task ?? "Idle"} />
        <Row label="Upstream" value={agent.depends_on.length ? agent.depends_on.join(", ") : "root"} />
      </dl>
      <button onClick={onClose} className="mt-4 text-xs text-signal hover:text-ink">
        Close
      </button>
    </motion.aside>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <dt className="w-20 shrink-0 text-faint">{label}</dt>
      <dd className="min-w-0 flex-1 text-ink-soft">{value}</dd>
    </div>
  );
}
