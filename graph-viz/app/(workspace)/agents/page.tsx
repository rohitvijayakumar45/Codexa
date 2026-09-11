"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2, Play, X } from "lucide-react";
import {
  api,
  type AgentNode,
  type EventRecord,
  type PlanResult,
  type ProposeChangeResult,
  type ResearchAskResult,
  type UsageRecord,
} from "@/lib/api";
import { PageHeader } from "@/components/shell/PageHeader";
import { CenteredError, CenteredLoading } from "@/components/shell/States";
import { EASE_OUT } from "@/components/ui/primitives";
import { useRepoStore } from "@/lib/repo-store";
import { useJobStore } from "@/lib/job-store";
import { route, taper, type Box } from "@/lib/strata/geometry";

/*
  Agent network — who is working right now, and on what.

  Two real sources, polled every two seconds:
    - the graph event ledger, attributed to the orchestration agent that produced each event
    - the LLM usage log, which records every model call with the agent that made it
  An agent is WORKING if it produced anything in the last minute, RECENT within fifteen, IDLE
  otherwise. (The backend's own `status` flag means "ever produced anything", so it is not used for
  liveness.) Agents seen only in the usage log — the chat agent, delegate workers, the plan builder —
  are real runtime agents and appear in their lane; nothing here is invented.
*/

const RUNNABLE_AGENTS = new Set(["planner", "coder", "research"]);
const LAYERS = ["Perception", "Understanding", "Planning", "Simulation", "Verification", "Execution", "Learning"];
const MIN = 60_000;
const WORKING_MS = MIN;
const RECENT_MS = 15 * MIN;
const BUCKETS = 30;
const POLL_MS = 2_000;

type Status = "working" | "recent" | "idle";

interface Activity {
  id: string;
  agent: string;
  at: number;
  kind: "llm" | "event";
  text: string;
  tokens?: number;
}

interface Agent {
  id: string;
  name: string;
  role: string;
  layer: string;
  depends_on: string[];
  runtime: boolean;
  lastAt: number | null;
  status: Status;
  buckets: number[];
  calls: number;
  tokens: number;
  total: number;
  task: string | null;
  model?: string;
}

// Agents that only show up in the LLM usage log. Lineage is listed only where the code makes it
// certain (the chat agent calls the plan builder and fans out to delegate workers).
const RUNTIME: Record<string, { name: string; role: string; layer: string; depends_on: string[] }> = {
  chat: { name: "Codexa Agent", role: "Runs chat jobs and tool calls", layer: "Execution", depends_on: ["plan"] },
  plan: { name: "Plan Builder", role: "Turns a request into tasks", layer: "Planning", depends_on: [] },
  delegate_build: { name: "Delegate Workers", role: "Build files in parallel", layer: "Execution", depends_on: ["chat"] },
  symbol_annotation: { name: "Symbol Annotator", role: "Summarises code symbols", layer: "Understanding", depends_on: [] },
  claim_extraction: { name: "Claim Extractor", role: "Pulls claims into memory", layer: "Learning", depends_on: [] },
  docs: { name: "Docs Writer", role: "Generates documentation", layer: "Understanding", depends_on: [] },
};

const humanize = (s: string) => s.replace(/[_-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());

/** Mirrors the backend's attribution (observability/api.py `_attribute`) from what the ledger exposes. */
function attributeEvent(ev: EventRecord): string {
  const t = ev.event_type;
  if (t.startsWith("planner.")) return "planner";
  if (t.startsWith("coder.")) return "coder";
  if (t.startsWith("retrieval.")) return "retrieval";
  if (t === "graph.node.created") {
    const kind = ev.summary.split(" · ")[0];
    if (kind === "CausalEvent") return "causal";
    if (kind === "ArchitectureTrend") return "architecture";
    if (kind === "HealthMetric") return "health";
    if (kind === "ExternalArtifact") return "research";
  }
  return "perception";
}

const fmtTokens = (n: number) => (n >= 1_000_000 ? `${(n / 1e6).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));

function ago(ms: number | null, now: number): string {
  if (ms == null) return "never";
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  return h < 48 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
}

function buildNetwork(curated: AgentNode[], events: EventRecord[], usage: UsageRecord[], now: number) {
  const feed: Activity[] = [
    ...events.map((ev) => ({ id: ev.id, agent: attributeEvent(ev), at: Date.parse(ev.occurred_at), kind: "event" as const, text: ev.summary })),
    ...usage.map((r, i) => ({
      id: `llm-${r.at}-${i}`,
      agent: r.agent,
      at: Date.parse(r.at),
      kind: "llm" as const,
      text: `${r.model.split("/").pop()} · ${fmtTokens(r.total_tokens)} tokens`,
      tokens: r.total_tokens,
    })),
  ].sort((a, b) => b.at - a.at);

  const defs = new Map<string, Omit<Agent, "lastAt" | "status" | "buckets" | "calls" | "tokens" | "total" | "task"> & { base?: AgentNode }>();
  for (const a of curated)
    defs.set(a.id, { id: a.id, name: a.name, role: a.role, layer: a.layer, depends_on: a.depends_on, runtime: false, base: a });
  for (const r of usage) {
    if (defs.has(r.agent)) continue;
    const known = RUNTIME[r.agent];
    defs.set(r.agent, {
      id: r.agent,
      name: known?.name ?? humanize(r.agent),
      role: known?.role ?? "LLM agent",
      layer: known?.layer ?? "Execution",
      depends_on: known?.depends_on ?? [],
      runtime: true,
    });
  }

  const agents: Agent[] = [...defs.values()].map((d) => {
    const acts = feed.filter((f) => f.agent === d.id);
    const baseLast = d.base?.last_active ? Date.parse(d.base.last_active) : null;
    const lastAt = Math.max(acts[0]?.at ?? -Infinity, baseLast ?? -Infinity);
    const last = Number.isFinite(lastAt) ? lastAt : null;
    const buckets = new Array<number>(BUCKETS).fill(0);
    let calls = 0;
    let tokens = 0;
    for (const a of acts) {
      const age = now - a.at;
      if (age < 0 || age >= BUCKETS * MIN) continue;
      buckets[BUCKETS - 1 - Math.floor(age / MIN)]++;
      if (a.kind === "llm") {
        calls++;
        tokens += a.tokens ?? 0;
      }
    }
    const age = last == null ? Infinity : now - last;
    const llmActs = acts.filter((a) => a.kind === "llm");
    return {
      id: d.id,
      name: d.name,
      role: d.role,
      layer: d.layer,
      depends_on: d.depends_on,
      runtime: d.runtime,
      lastAt: last,
      status: age < WORKING_MS ? "working" : age < RECENT_MS ? "recent" : "idle",
      buckets,
      calls,
      tokens,
      total: d.runtime ? llmActs.length : (d.base?.activity_count ?? acts.length),
      task: acts[0]?.text ?? d.base?.current_task ?? null,
      model: usage.find((u) => u.agent === d.id)?.model.split("/").pop(),
    };
  });
  return { agents, feed };
}

/** A one-second clock for the "12s ago" labels. Starts at 0 so the first render stays pure. */
function useNow() {
  const [now, setNow] = useState(0);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, []);
  return now;
}

// ---- Lane layout (SVG units; the canvas scales to its container).
const VW = 1000;
const LABEL_W = 128;
const CARD_W = 164;
const CARD_H = 90;
const GAP_X = 12;
const GAP_Y = 14;
const LANE_PAD = 16;
const PER_LINE = 5;
const BOX: Box = { hw: CARD_W / 2, hh: CARD_H / 2 };

function layoutLanes(agents: Agent[]) {
  const pos = new Map<string, { x: number; y: number }>();
  const lanes: { name: string; y: number; h: number; working: number; count: number }[] = [];
  let y = 0;
  for (const layer of LAYERS) {
    const list = agents
      .filter((a) => a.layer === layer)
      .sort((a, b) => Number(a.runtime) - Number(b.runtime) || a.name.localeCompare(b.name));
    if (!list.length) continue;
    const lines = Math.ceil(list.length / PER_LINE);
    const h = LANE_PAD * 2 + lines * CARD_H + (lines - 1) * GAP_Y;
    list.forEach((a, i) =>
      pos.set(a.id, {
        x: LABEL_W + (i % PER_LINE) * (CARD_W + GAP_X),
        y: y + LANE_PAD + Math.floor(i / PER_LINE) * (CARD_H + GAP_Y),
      }),
    );
    lanes.push({ name: layer, y, h, working: list.filter((a) => a.status === "working").length, count: list.length });
    y += h;
  }
  return { pos, lanes, height: Math.max(y, 200) };
}

const STATUS_LABEL: Record<Status, string> = { working: "Working", recent: "Recent", idle: "Idle" };
const STATUS_COLOR: Record<Status, string> = {
  working: "var(--color-signal)",
  recent: "var(--color-ink-soft)",
  idle: "var(--color-faint)",
};

export default function AgentsPage() {
  const qc = useQueryClient();
  const activeRepo = useRepoStore((s) => s.activeRepo);
  const jobId = useJobStore((s) => s.jobId);
  const jobStatus = useJobStore((s) => s.status);
  const jobTask = useJobStore((s) => s.task);
  const agentsQ = useQuery({ queryKey: ["agents"], queryFn: api.agents, refetchInterval: POLL_MS });
  const eventsQ = useQuery({ queryKey: ["events", 500], queryFn: () => api.events(500), refetchInterval: POLL_MS });
  const usageQ = useQuery({ queryKey: ["usage-records", 500], queryFn: () => api.usageRecords(500), refetchInterval: POLL_MS });
  const [selected, setSelected] = useState<string | null>(null);
  const clock = useNow();

  const curated = agentsQ.data?.agents;
  const events = eventsQ.data;
  const usage = usageQ.data;
  const latestSeen = useMemo(() => {
    const ts = [...(events ?? []).map((e) => Date.parse(e.occurred_at)), ...(usage ?? []).map((u) => Date.parse(u.at))];
    return ts.length ? Math.max(...ts) : 0;
  }, [events, usage]);
  // Until the clock's first tick, measure ages from the newest record so nothing flashes "working".
  const now = clock || latestSeen;

  const { agents, feed } = useMemo(
    () => buildNetwork(curated ?? [], events ?? [], usage ?? [], now),
    [curated, events, usage, now],
  );
  const layout = useMemo(() => layoutLanes(agents), [agents]);
  const byId = useMemo(() => new Map(agents.map((a) => [a.id, a])), [agents]);

  if (agentsQ.isLoading) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Orchestration" title="Agent network" />
        <CenteredLoading label="Reading agent status" />
      </div>
    );
  }
  if (agentsQ.error) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Orchestration" title="Agent network" />
        <CenteredError message={(agentsQ.error as Error).message} onRetry={() => agentsQ.refetch()} />
      </div>
    );
  }

  const working = agents.filter((a) => a.status === "working");
  const calls30 = agents.reduce((s, a) => s + a.calls, 0);
  const tokens30 = agents.reduce((s, a) => s + a.tokens, 0);
  const updated = Math.max(agentsQ.dataUpdatedAt, eventsQ.dataUpdatedAt, usageQ.dataUpdatedAt);
  const stale = clock > 0 && clock - updated > POLL_MS * 4;
  const selectedAgent = selected ? (byId.get(selected) ?? null) : null;
  const isNeighbour = (id: string) =>
    !selectedAgent || id === selectedAgent.id || selectedAgent.depends_on.includes(id) || (byId.get(id)?.depends_on.includes(selectedAgent.id) ?? false);

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow="Orchestration" title="Agent network">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            {!stale ? (
              <span className="absolute inline-flex h-full w-full rounded-full bg-signal-live opacity-60" style={{ animation: "breathe 2.4s ease-in-out infinite" }} />
            ) : null}
            <span className={`relative inline-flex h-2 w-2 rounded-full ${stale ? "bg-faint" : "bg-signal"}`} />
          </span>
          <span className="num text-sm font-medium text-ink">{working.length}</span>
          <span className="status-line">working</span>
          <span className="status-line ml-3 !normal-case !tracking-normal">
            {stale ? "connection lost — retrying" : `updated ${ago(updated, clock || updated)}`}
          </span>
        </div>
      </PageHeader>

      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className="flex min-h-0 flex-col">
          <div className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-2 border-b border-line bg-panel px-6 py-3">
            <Metric label="LLM calls · 30 min" value={String(calls30)} />
            <Metric label="Tokens · 30 min" value={fmtTokens(tokens30)} />
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
              {working.length === 0 ? (
                <span className="text-xs text-muted">Nothing is running right now.</span>
              ) : (
                working.map((a) => (
                  <button
                    key={a.id}
                    onClick={() => setSelected(a.id)}
                    className="flex items-center gap-1.5 rounded-full border border-signal/40 bg-signal-wash px-2.5 py-0.5 text-[11.5px] font-medium text-ink"
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-signal" style={{ animation: "breathe 2s ease-in-out infinite" }} />
                    {a.name}
                  </button>
                ))
              )}
            </div>
            {jobId ? (
              <span className="max-w-[360px] truncate text-xs text-ink-soft" title={jobTask || jobStatus}>
                <span className="status-line mr-2">Job</span>
                {jobStatus || "Running"}
                {jobTask ? ` — ${jobTask}` : ""}
              </span>
            ) : null}
          </div>

          <div
            className="min-h-0 flex-1 overflow-auto"
            style={{ background: "radial-gradient(circle at 1px 1px, color-mix(in srgb, var(--color-ink) 5%, transparent) 1px, transparent 0) 0 0 / 26px 26px, var(--color-g-canvas)" }}
            onClick={() => setSelected(null)}
          >
            <svg viewBox={`0 0 ${VW} ${layout.height}`} className="block w-full" style={{ minWidth: 760 }} role="img" aria-label="Agent network by layer">
              {layout.lanes.map((l, i) => (
                <g key={l.name}>
                  {i > 0 ? <line x1={12} x2={VW - 12} y1={l.y} y2={l.y} stroke="var(--color-line)" /> : null}
                  <text x={20} y={l.y + LANE_PAD + 16} style={{ font: "500 10.5px var(--font-mono)", letterSpacing: "0.14em", fill: "var(--color-muted)" }}>
                    {l.name.toUpperCase()}
                  </text>
                  <text x={20} y={l.y + LANE_PAD + 34} style={{ font: "11px var(--font-mono)", fill: l.working ? "var(--color-signal)" : "var(--color-faint)" }}>
                    {l.working ? `${l.working} working` : `${l.count} idle`.replace(/^(\d+) idle$/, (_, n) => `${n} agent${n === "1" ? "" : "s"}`)}
                  </text>
                </g>
              ))}

              {agents.flatMap((a) =>
                a.depends_on.map((dep) => {
                  const from = layout.pos.get(dep);
                  const to = layout.pos.get(a.id);
                  if (!from || !to) return null;
                  const c = route(
                    {},
                    BOX,
                    { x: from.x + BOX.hw, y: from.y + BOX.hh },
                    BOX,
                    { x: to.x + BOX.hw, y: to.y + BOX.hh },
                  );
                  const live = a.status === "working";
                  const dim = selectedAgent && !(isNeighbour(a.id) && isNeighbour(dep));
                  const d = `M${c[0].x} ${c[0].y}C${c[1].x} ${c[1].y} ${c[2].x} ${c[2].y} ${c[3].x} ${c[3].y}`;
                  return (
                    <g key={`${dep}-${a.id}`} style={{ opacity: dim ? 0.15 : 1, transition: "opacity .25s" }}>
                      <path d={taper(c, 2.6, 0.6)} style={{ fill: live ? "var(--color-signal)" : "var(--color-g-edge)", opacity: live ? 0.75 : 0.55 }} />
                      {live ? (
                        <path
                          d={d}
                          fill="none"
                          stroke="var(--color-signal)"
                          strokeWidth={1.2}
                          strokeDasharray="3 6"
                          className="motion-safe:animate-[flow_1.1s_linear_infinite]"
                        />
                      ) : null}
                    </g>
                  );
                }),
              )}

              {agents.map((a) => {
                const p = layout.pos.get(a.id);
                if (!p) return null;
                const isSel = a.id === selected;
                const live = a.status === "working";
                const maxB = Math.max(1, ...a.buckets);
                const sparkW = CARD_W - 28;
                const bw = sparkW / BUCKETS;
                return (
                  <g
                    key={a.id}
                    transform={`translate(${p.x} ${p.y})`}
                    role="button"
                    tabIndex={0}
                    aria-label={`${a.name}, ${STATUS_LABEL[a.status]}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelected(isSel ? null : a.id);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelected(isSel ? null : a.id);
                      }
                    }}
                    style={{ cursor: "pointer", opacity: isNeighbour(a.id) ? 1 : 0.3, transition: "opacity .25s", outline: "none" }}
                  >
                    {live ? (
                      <rect
                        x={-4}
                        y={-4}
                        width={CARD_W + 8}
                        height={CARD_H + 8}
                        rx={15}
                        fill="none"
                        stroke="var(--color-signal)"
                        strokeWidth={1.5}
                        style={{ animation: "breathe 2.4s ease-in-out infinite" }}
                      />
                    ) : null}
                    <rect
                      width={CARD_W}
                      height={CARD_H}
                      rx={11}
                      fill="var(--color-panel)"
                      stroke={isSel ? "var(--color-ink)" : live ? "var(--color-signal)" : "var(--color-line-strong)"}
                      strokeWidth={isSel || live ? 1.5 : 1}
                    />
                    <circle cx={14} cy={18} r={3.5} fill={STATUS_COLOR[a.status]} />
                    <text x={24} y={22} style={{ font: "600 12.5px var(--font-sans)", fill: "var(--color-ink)" }}>
                      {a.name.length > 17 ? `${a.name.slice(0, 16)}…` : a.name}
                    </text>
                    <text x={14} y={39} style={{ font: "11px var(--font-sans)", fill: "var(--color-muted)" }}>
                      {a.role.length > 26 ? `${a.role.slice(0, 25)}…` : a.role}
                    </text>
                    {a.buckets.map((v, i) =>
                      v ? (
                        <rect
                          key={i}
                          x={14 + i * bw + 0.5}
                          y={70 - (v / maxB) * 18}
                          width={Math.max(1, bw - 1.2)}
                          height={(v / maxB) * 18}
                          rx={1}
                          style={{ fill: i >= BUCKETS - 1 && live ? "var(--color-signal)" : "var(--color-ink-soft)", opacity: 0.7 }}
                        />
                      ) : null,
                    )}
                    <line x1={14} x2={14 + sparkW} y1={70.5} y2={70.5} stroke="var(--color-line)" />
                    <text x={14} y={83} style={{ font: "10px var(--font-mono)", fill: STATUS_COLOR[a.status] }}>
                      {STATUS_LABEL[a.status]}
                    </text>
                    <text x={CARD_W - 12} y={83} textAnchor="end" style={{ font: "10px var(--font-mono)", fill: "var(--color-faint)" }}>
                      {ago(a.lastAt, now)}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        </section>

        <aside className="flex min-h-0 flex-col border-t border-line bg-panel lg:border-l lg:border-t-0">
          <AnimatePresence mode="wait" initial={false}>
            {selectedAgent ? (
              <AgentDetail
                key={selectedAgent.id}
                agent={selectedAgent}
                byId={byId}
                feed={feed}
                now={now}
                repository={activeRepo}
                onClose={() => setSelected(null)}
                onRan={() => qc.invalidateQueries({ queryKey: ["agents"] })}
              />
            ) : (
              <LiveFeed key="feed" feed={feed} byId={byId} now={now} onPick={setSelected} />
            )}
          </AnimatePresence>
        </aside>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="num text-base font-medium leading-none text-ink">{value}</span>
      <span className="status-line mt-1">{label}</span>
    </div>
  );
}

function LiveFeed({
  feed,
  byId,
  now,
  onPick,
}: {
  feed: Activity[];
  byId: Map<string, Agent>;
  now: number;
  onPick: (id: string) => void;
}) {
  const rows = feed.slice(0, 80);
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18 }}
      className="flex min-h-0 flex-1 flex-col"
    >
      <div className="shrink-0 border-b border-line px-5 py-4">
        <span className="status-line">Live feed</span>
        <p className="mt-1 text-xs text-muted">Every model call and graph event, newest first. Pick an agent for its detail.</p>
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        <AnimatePresence initial={false}>
          {rows.map((r) => {
            const a = byId.get(r.agent);
            return (
              <motion.li
                key={r.id}
                layout="position"
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, ease: EASE_OUT }}
              >
                <button
                  onClick={() => onPick(r.agent)}
                  className="grid w-full grid-cols-[52px_minmax(0,1fr)] gap-3 rounded-lg px-3 py-2 text-left transition-colors hover:bg-paper-sunk"
                >
                  <span className="num pt-0.5 text-[11px] text-faint">{ago(r.at, now)}</span>
                  <span className="min-w-0">
                    <span className="flex items-center gap-1.5 text-[12.5px] font-medium text-ink">
                      <span
                        className={r.kind === "llm" ? "h-1.5 w-1.5 rotate-45 bg-ink-soft" : "h-1.5 w-1.5 rounded-full bg-faint"}
                        aria-hidden
                      />
                      {a?.name ?? humanize(r.agent)}
                      <span className="status-line !text-[9.5px]">{r.kind === "llm" ? "model call" : "event"}</span>
                    </span>
                    <span className="block truncate text-xs text-muted" title={r.text}>
                      {r.text}
                    </span>
                  </span>
                </button>
              </motion.li>
            );
          })}
        </AnimatePresence>
        {rows.length === 0 ? <li className="px-3 py-2 text-xs text-muted">No activity recorded yet.</li> : null}
      </ul>
    </motion.div>
  );
}

function AgentDetail({
  agent,
  byId,
  feed,
  now,
  repository,
  onClose,
  onRan,
}: {
  agent: Agent;
  byId: Map<string, Agent>;
  feed: Activity[];
  now: number;
  repository: string;
  onClose: () => void;
  onRan: () => void;
}) {
  const runnable = RUNNABLE_AGENTS.has(agent.id);
  const downstream = [...byId.values()].filter((a) => a.depends_on.includes(agent.id));
  const recent = feed.filter((f) => f.agent === agent.id).slice(0, 12);
  const maxB = Math.max(1, ...agent.buckets);
  return (
    <motion.div
      initial={{ x: 16, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 16, opacity: 0 }}
      transition={{ duration: 0.24, ease: EASE_OUT }}
      className="flex min-h-0 flex-1 flex-col"
    >
      <div className="flex shrink-0 items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div className="min-w-0">
          <span className="status-line">
            {agent.layer}
            {agent.runtime ? " · runtime" : ""}
          </span>
          <h2 className="display mt-0.5 text-[17px] font-semibold text-ink">{agent.name}</h2>
          <p className="mt-0.5 text-xs text-muted">{agent.role}</p>
        </div>
        <button
          onClick={onClose}
          className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-muted transition-colors hover:bg-paper-sunk hover:text-ink"
          aria-label="Back to the live feed"
        >
          <X size={15} />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <span
          className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium"
          style={{
            color: STATUS_COLOR[agent.status],
            background: agent.status === "working" ? "var(--color-signal-wash)" : "var(--color-paper-sunk)",
          }}
        >
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: STATUS_COLOR[agent.status] }} />
          {STATUS_LABEL[agent.status]} · {ago(agent.lastAt, now)}
        </span>

        <svg viewBox={`0 0 ${BUCKETS * 8} 40`} className="mt-4 block h-12 w-full" preserveAspectRatio="none" aria-label="Activity per minute, last 30 minutes">
          {agent.buckets.map((v, i) =>
            v ? <rect key={i} x={i * 8 + 1} y={38 - (v / maxB) * 36} width={6} height={(v / maxB) * 36} rx={1.5} style={{ fill: "var(--color-ink-soft)" }} /> : null,
          )}
          <line x1={0} x2={BUCKETS * 8} y1={38.5} y2={38.5} stroke="var(--color-line)" vectorEffect="non-scaling-stroke" />
        </svg>
        <div className="mt-1 flex justify-between text-[10px] text-faint">
          <span className="num">30 min ago</span>
          <span className="num">now</span>
        </div>

        <dl className="mt-4 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-xs">
          <Row label="Model calls" value={`${agent.calls} in 30 min`} />
          <Row label="Tokens" value={`${fmtTokens(agent.tokens)} in 30 min`} />
          <Row label="All time" value={`${agent.total} ${agent.runtime ? "calls" : "events"}`} />
          {agent.model ? <Row label="Model" value={agent.model} /> : null}
          <Row label="Now" value={agent.status === "working" ? (agent.task ?? "Working") : "Idle"} />
          <Row label="Upstream" value={agent.depends_on.map((d) => byId.get(d)?.name ?? d).join(", ") || "none"} />
          <Row label="Downstream" value={downstream.map((d) => d.name).join(", ") || "none"} />
        </dl>

        <h3 className="status-line mt-5">Recent activity</h3>
        {recent.length ? (
          <ul className="mt-2 divide-y divide-line">
            {recent.map((r) => (
              <li key={r.id} className="grid grid-cols-[52px_minmax(0,1fr)] gap-3 py-1.5 text-xs">
                <span className="num text-faint">{ago(r.at, now)}</span>
                <span className="truncate text-ink-soft" title={r.text}>
                  {r.text}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-xs text-muted">Nothing recorded for this agent yet.</p>
        )}

        {runnable ? (
          <div className="mt-5 border-t border-line pt-4">
            {agent.id === "planner" && <PlannerRunPanel repository={repository} onRan={onRan} />}
            {agent.id === "coder" && <CoderRunPanel repository={repository} onRan={onRan} />}
            {agent.id === "research" && <ResearchRunPanel repository={repository} onRan={onRan} />}
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}

function RunButton({ pending, label = "Run" }: { pending: boolean; label?: string }) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-xs font-medium text-panel transition-colors hover:bg-ink-soft disabled:opacity-40"
    >
      {pending ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
      {pending ? "Running…" : label}
    </button>
  );
}

const inputCls =
  "w-full rounded-lg border border-line bg-paper-sunk px-2.5 py-2 text-xs text-ink outline-none placeholder:text-faint focus:border-line-strong";

function PlannerRunPanel({ repository, onRan }: { repository: string; onRan: () => void }) {
  const [goal, setGoal] = useState("");
  const m = useMutation({
    mutationFn: () => api.planGoal(repository, goal),
    onSuccess: onRan,
  });
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (goal.trim()) m.mutate();
      }}
    >
      <p className="status-line">Run it — repository: {repository}</p>
      <textarea
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
        placeholder="Goal, e.g. 'add rate limiting to the chat endpoint'"
        rows={2}
        className={inputCls}
      />
      <RunButton pending={m.isPending} label="Synthesize plan" />
      {m.isError && <p className="text-xs text-warn">{(m.error as Error).message}</p>}
      {m.data && <PlanOutput result={m.data} />}
    </form>
  );
}

function PlanOutput({ result }: { result: PlanResult }) {
  return (
    <div className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg border border-line bg-paper-sunk p-2.5 text-[11px] leading-relaxed text-ink-soft">
      {result.plan}
    </div>
  );
}

function CoderRunPanel({ repository, onRan }: { repository: string; onRan: () => void }) {
  const [objective, setObjective] = useState("");
  const [filePaths, setFilePaths] = useState("");
  const m = useMutation({
    mutationFn: () =>
      api.proposeChange(
        repository,
        objective,
        filePaths.split(",").map((p) => p.trim()).filter(Boolean),
      ),
    onSuccess: onRan,
  });
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (objective.trim()) m.mutate();
      }}
    >
      <p className="status-line">Run it — repository: {repository}</p>
      <textarea
        value={objective}
        onChange={(e) => setObjective(e.target.value)}
        placeholder="Objective, e.g. 'add input validation to compute_shipping_cost'"
        rows={2}
        className={inputCls}
      />
      <input
        value={filePaths}
        onChange={(e) => setFilePaths(e.target.value)}
        placeholder="File paths, comma-separated (e.g. calc.py, utils.py)"
        className={inputCls}
      />
      <RunButton pending={m.isPending} label="Propose change" />
      {m.isError && <p className="text-xs text-warn">{(m.error as Error).message}</p>}
      {m.data && <ProposalOutput result={m.data} />}
    </form>
  );
}

function ProposalOutput({ result }: { result: ProposeChangeResult }) {
  return (
    <div className="mt-2 space-y-2">
      <p className="text-[11px] text-ink-soft">{result.rationale}</p>
      {result.changes.map((c) => (
        <div key={c.path} className="rounded-lg border border-line bg-paper-sunk p-2">
          <p className="num text-[10.5px] font-medium text-muted">{c.path}</p>
          <pre className="num mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-[10.5px] text-ink-soft">{c.diff}</pre>
        </div>
      ))}
    </div>
  );
}

function ResearchRunPanel({ repository, onRan }: { repository: string; onRan: () => void }) {
  const [query, setQuery] = useState("");
  const m = useMutation({
    mutationFn: () => api.askResearch(repository, query),
    onSuccess: onRan,
  });
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (query.trim()) m.mutate();
      }}
    >
      <p className="status-line">Run it — repository: {repository}</p>
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Question, e.g. 'what's the current best practice for X'"
        rows={2}
        className={inputCls}
      />
      <RunButton pending={m.isPending} label="Ask" />
      {m.isError && <p className="text-xs text-warn">{(m.error as Error).message}</p>}
      {m.data && <ResearchOutput result={m.data} />}
    </form>
  );
}

function ResearchOutput({ result }: { result: ResearchAskResult }) {
  return (
    <div className="mt-2 space-y-2">
      <p className="text-[11px] text-ink-soft">{result.recommendation}</p>
      <p className="text-[10.5px] text-faint">
        Confidence {Math.round(result.confidence * 100)}% ·{" "}
        {result.used_web_search ? "grounded in live web search" : "no web search configured"}
      </p>
      <ul className="space-y-1">
        {result.citations.map((c) => (
          <li key={c.url} className="rounded-lg border border-line bg-paper-sunk p-2 text-[10.5px]">
            <p className="font-medium text-ink-soft">{c.title}</p>
            <p className="text-faint">{c.summary}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-faint">{label}</dt>
      <dd className="min-w-0 break-words text-ink-soft">{value}</dd>
    </>
  );
}
