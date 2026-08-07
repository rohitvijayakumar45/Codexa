"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api, type UsageBucket, type UsageDailyBucket } from "@/lib/api";
import { PageHeader } from "@/components/shell/PageHeader";
import { CenteredError, CenteredLoading, CenteredEmpty } from "@/components/shell/States";
import { EASE_OUT } from "@/components/ui/primitives";

const AGENT_LABEL: Record<string, string> = {
  chat: "Chat",
  planner: "Planner",
  coder: "Coder",
  research: "Research agent",
  architecture: "Architecture evolution",
  docs: "Documentation generator",
  symbol_annotation: "Symbol semantic annotation",
  reasoning: "Reasoning",
  retrieval: "Context assembly",
  generate: "Other generation",
};

const RANGES = [
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
  { label: "All time", days: undefined },
] as const;

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export default function UsagePage() {
  const [range, setRange] = useState<(typeof RANGES)[number]>(RANGES[1]);
  const chartDays = range.days ?? 90;

  const summaryQ = useQuery({
    queryKey: ["usage-summary", range.days],
    queryFn: () => api.usageSummary(range.days),
    refetchInterval: 15_000,
  });
  const recordsQ = useQuery({
    queryKey: ["usage-records", range.days],
    queryFn: () => api.usageRecords(60, range.days),
    refetchInterval: 15_000,
  });
  const dailyQ = useQuery({
    queryKey: ["usage-daily", chartDays],
    queryFn: () => api.usageDaily(chartDays),
    refetchInterval: 15_000,
  });

  const agentRows = useMemo(() => {
    const entries = Object.entries(summaryQ.data?.by_agent ?? {});
    const max = Math.max(1, ...entries.map(([, b]) => b.total_tokens));
    return entries
      .sort((a, b) => b[1].total_tokens - a[1].total_tokens)
      .map(([agent, bucket]) => ({ agent, bucket, pct: (bucket.total_tokens / max) * 100 }));
  }, [summaryQ.data]);

  const modelRows = useMemo(() => {
    const entries = Object.entries(summaryQ.data?.by_model ?? {});
    const max = Math.max(1, ...entries.map(([, b]) => b.total_tokens));
    return entries
      .sort((a, b) => b[1].total_tokens - a[1].total_tokens)
      .map(([model, bucket]) => ({ model, bucket, pct: (bucket.total_tokens / max) * 100 }));
  }, [summaryQ.data]);

  if (summaryQ.isLoading)
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Observability" title="Usage" />
        <CenteredLoading label="Tallying token usage" />
      </div>
    );
  if (summaryQ.error)
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Observability" title="Usage" />
        <CenteredError message={(summaryQ.error as Error).message} onRetry={() => summaryQ.refetch()} />
      </div>
    );

  const totals: UsageBucket = summaryQ.data?.totals ?? {
    prompt_tokens: 0, completion_tokens: 0, reasoning_tokens: 0, total_tokens: 0, calls: 0,
  };
  const empty = totals.calls === 0;
  const visibleCompletion = totals.completion_tokens - totals.reasoning_tokens;

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow="Observability" title="Usage">
        <span className="status-line hidden sm:inline">Real provider-reported counts · persists across restarts</span>
        <div className="flex items-center gap-1 rounded-lg border border-line bg-panel-2 p-0.5">
          {RANGES.map((r) => (
            <button
              key={r.label}
              onClick={() => setRange(r)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                r.label === range.label ? "bg-panel text-ink shadow-sm" : "text-muted hover:text-ink"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </PageHeader>

      {empty ? (
        <CenteredEmpty title="No LLM calls recorded yet">
          Usage fills in as chat, docs generation, and symbol annotation run — real token counts
          reported by each provider, not an estimate. History persists to disk and survives a restart.
        </CenteredEmpty>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-4xl px-8 py-10">
            <div className="grid grid-cols-4 gap-4">
              <Stat label="calls" value={fmt(totals.calls)} />
              <Stat label="prompt tokens" value={fmt(totals.prompt_tokens)} />
              <Stat
                label="completion tokens"
                value={fmt(totals.completion_tokens)}
                sub={totals.reasoning_tokens > 0 ? `${fmt(visibleCompletion)} visible · ${fmt(totals.reasoning_tokens)} reasoning` : undefined}
              />
              <Stat label="total tokens" value={fmt(totals.total_tokens)} accent />
            </div>

            {(dailyQ.data?.length ?? 0) > 0 && (
              <div className="mt-10">
                <span className="status-line">Daily usage</span>
                <DailyChart data={dailyQ.data ?? []} />
              </div>
            )}

            <div className="mt-12 grid gap-12 md:grid-cols-2">
              <div>
                <span className="status-line">By agent</span>
                <div className="mt-4 space-y-4">
                  {agentRows.map((row, i) => (
                    <UsageBar
                      key={row.agent}
                      label={AGENT_LABEL[row.agent] ?? row.agent}
                      bucket={row.bucket}
                      pct={row.pct}
                      index={i}
                    />
                  ))}
                </div>
              </div>
              <div>
                <span className="status-line">By model</span>
                <div className="mt-4 space-y-4">
                  {modelRows.map((row, i) => (
                    <UsageBar key={row.model} label={row.model} bucket={row.bucket} pct={row.pct} index={i} />
                  ))}
                </div>
              </div>
            </div>

            {(recordsQ.data?.length ?? 0) > 0 && (
              <div className="mt-14">
                <span className="status-line">Recent calls</span>
                <ul className="mt-3 divide-y divide-line">
                  {(recordsQ.data ?? []).slice(0, 20).map((r, i) => (
                    <li key={i} className="flex items-center gap-4 py-2.5 text-sm">
                      <span className="num w-24 shrink-0 text-[11px] text-faint">
                        {new Date(r.at).toLocaleTimeString()}
                      </span>
                      <span className="w-44 shrink-0 truncate text-ink-soft">
                        {AGENT_LABEL[r.agent] ?? r.agent}
                      </span>
                      <span className="num min-w-0 flex-1 truncate text-xs text-faint">{r.model}</span>
                      {r.reasoning_tokens > 0 && (
                        <span className="num shrink-0 text-[10px] text-faint">{fmt(r.reasoning_tokens)} reasoning</span>
                      )}
                      <span className="num shrink-0 text-xs text-muted">{fmt(r.total_tokens)} tok</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div>
      <span className={`num text-2xl font-medium leading-none ${accent ? "text-signal" : "text-ink"}`}>
        {value}
      </span>
      <p className="status-line mt-1.5">{label}</p>
      {sub && <p className="num mt-0.5 text-[10.5px] text-faint">{sub}</p>}
    </div>
  );
}

function DailyChart({ data }: { data: UsageDailyBucket[] }) {
  const max = Math.max(1, ...data.map((d) => d.total_tokens));
  const barW = 100 / data.length;
  return (
    <div className="mt-4">
      <div className="flex h-32 items-end gap-[1px]">
        {data.map((d, i) => {
          const h = Math.max(1, (d.total_tokens / max) * 100);
          const hasReasoning = d.reasoning_tokens > 0;
          const reasoningH = hasReasoning ? (d.reasoning_tokens / d.total_tokens) * h : 0;
          return (
            <div
              key={d.date}
              className="group relative flex-1"
              style={{ height: "100%" }}
              title={`${d.date}: ${d.total_tokens} tokens, ${d.calls} calls`}
            >
              <div className="absolute bottom-0 w-full overflow-hidden rounded-[2px] bg-paper-sunk" style={{ height: "100%" }}>
                <motion.div
                  className="absolute bottom-0 w-full bg-signal/30"
                  initial={{ height: 0 }}
                  animate={{ height: `${h}%` }}
                  transition={{ duration: 0.5, delay: i * 0.01, ease: EASE_OUT }}
                />
                {hasReasoning && (
                  <motion.div
                    className="absolute bottom-0 w-full bg-signal"
                    initial={{ height: 0 }}
                    animate={{ height: `${reasoningH}%` }}
                    transition={{ duration: 0.5, delay: i * 0.01, ease: EASE_OUT }}
                  />
                )}
              </div>
              <div className="pointer-events-none absolute -top-8 left-1/2 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-line bg-panel px-2 py-1 text-[10px] text-ink shadow-md group-hover:block">
                {d.date}: {fmt(d.total_tokens)} tok
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 flex justify-between">
        <span className="status-line">{data[0]?.date}</span>
        <span className="status-line">{data[data.length - 1]?.date}</span>
      </div>
    </div>
  );
}

function UsageBar({
  label,
  bucket,
  pct,
  index,
}: {
  label: string;
  bucket: UsageBucket;
  pct: number;
  index: number;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="truncate text-sm text-ink-soft">{label}</span>
        <span className="num shrink-0 text-xs text-muted">
          {fmt(bucket.total_tokens)} · {bucket.calls} call{bucket.calls !== 1 ? "s" : ""}
        </span>
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
