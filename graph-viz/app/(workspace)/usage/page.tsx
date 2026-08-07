"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api, type UsageBucket } from "@/lib/api";
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

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export default function UsagePage() {
  const summaryQ = useQuery({
    queryKey: ["usage-summary"],
    queryFn: api.usageSummary,
    refetchInterval: 15_000,
  });
  const recordsQ = useQuery({
    queryKey: ["usage-records"],
    queryFn: () => api.usageRecords(60),
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

  const totals = summaryQ.data?.totals ?? { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, calls: 0 };
  const empty = totals.calls === 0;

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow="Observability" title="Usage">
        <span className="status-line">Real provider-reported token counts, per agent</span>
      </PageHeader>

      {empty ? (
        <CenteredEmpty title="No LLM calls recorded yet">
          Usage fills in as chat, docs generation, and symbol annotation run — real token counts
          reported by each provider, not an estimate.
        </CenteredEmpty>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-4xl px-8 py-10">
            <div className="grid grid-cols-4 gap-4">
              <Stat label="calls" value={fmt(totals.calls)} />
              <Stat label="prompt tokens" value={fmt(totals.prompt_tokens)} />
              <Stat label="completion tokens" value={fmt(totals.completion_tokens)} />
              <Stat label="total tokens" value={fmt(totals.total_tokens)} accent />
            </div>

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

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <span className={`num text-2xl font-medium leading-none ${accent ? "text-signal" : "text-ink"}`}>
        {value}
      </span>
      <p className="status-line mt-1.5">{label}</p>
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
