"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shell/PageHeader";
import { CenteredError, CenteredLoading, CenteredEmpty } from "@/components/shell/States";
import { EASE_OUT } from "@/components/ui/primitives";

const METRIC_LABEL: Record<string, string> = {
  maintainability: "Maintainability",
  testability: "Testability",
  coupling: "Decoupling",
  doc_coverage: "Documentation",
  architecture_stability: "Architecture stability",
  deployment_safety: "Deployment safety",
  ownership_clarity: "Ownership clarity",
  tech_debt: "Tech-debt headroom",
  confidence: "Signal confidence",
};

export default function RepositoryPage() {
  const q = useQuery({ queryKey: ["nodes"], queryFn: () => api.nodes() });

  const health = useMemo(() => {
    const node = (q.data ?? []).find((n) => n.node_type === "HealthMetric");
    if (!node) return null;
    const props = node.properties as {
      repository?: string;
      score?: number;
      components?: Record<string, number>;
    };
    return {
      repository: props.repository ?? "repository",
      score: props.score ?? 0,
      components: props.components ?? {},
    };
  }, [q.data]);

  if (q.isLoading)
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Evaluation" title="Repository score" />
        <CenteredLoading label="Scoring the repository" />
      </div>
    );
  if (q.error)
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Evaluation" title="Repository score" />
        <CenteredError message={(q.error as Error).message} onRetry={() => q.refetch()} />
      </div>
    );
  if (!health)
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Evaluation" title="Repository score" />
        <CenteredEmpty title="No health metric yet">
          Score the repository via <span className="num">POST /trust-safety/health/repository</span>.
        </CenteredEmpty>
      </div>
    );

  const score100 = Math.round(health.score * 100);
  const metrics = Object.entries(health.components)
    .map(([key, value]) => ({ key, label: METRIC_LABEL[key] ?? key, value }))
    .sort((a, b) => b.value - a.value);

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow="Evaluation" title="Repository score">
        <span className="num text-sm text-muted">{health.repository}</span>
      </PageHeader>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-4xl gap-12 px-8 pt-12 md:grid-cols-[280px_1fr] md:items-center">
          <Gauge score={score100} />
          <div>
            <span className="status-line">Breakdown</span>
            <div className="mt-4 space-y-4">
              {metrics.map((m, i) => (
                <MetricBar key={m.key} label={m.label} value={m.value} index={i} />
              ))}
            </div>
          </div>
        </div>

        <div className="mx-auto max-w-4xl px-8 pb-16 pt-12">
          <Analysis score={score100} metrics={metrics} />
        </div>
      </div>
    </div>
  );
}

function Gauge({ score }: { score: number }) {
  const r = 96;
  const c = 2 * Math.PI * r;
  const band = score >= 75 ? "var(--color-signal)" : score >= 50 ? "var(--color-gold)" : "var(--color-warn)";
  const verdict = score >= 75 ? "Healthy" : score >= 50 ? "Watch" : "At risk";
  return (
    <div className="flex flex-col items-center">
      <div className="relative h-[220px] w-[220px]">
        <svg viewBox="0 0 220 220" className="h-full w-full -rotate-90">
          <circle cx="110" cy="110" r={r} fill="none" stroke="var(--color-paper-sunk)" strokeWidth="12" />
          <motion.circle
            cx="110"
            cy="110"
            r={r}
            fill="none"
            stroke={band}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={c}
            initial={{ strokeDashoffset: c }}
            animate={{ strokeDashoffset: c - (score / 100) * c }}
            transition={{ duration: 1.1, ease: EASE_OUT }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="num text-[56px] font-medium leading-none text-ink">{score}</span>
          <span className="status-line mt-1">out of 100</span>
        </div>
      </div>
      <span
        className="mt-4 rounded-full px-3 py-1 text-xs font-medium"
        style={{ background: "var(--color-signal-wash)", color: band }}
      >
        {verdict}
      </span>
    </div>
  );
}

const SUGGESTIONS: Record<string, string> = {
  maintainability: "Break up the largest modules and reduce cyclomatic complexity in the hotspots the graph flags.",
  testability: "Introduce seams and dependency injection around the core services so they can be unit-tested in isolation.",
  coupling: "Inter-module coupling is high. Extract interfaces and break the cyclic imports surfaced in the graph.",
  doc_coverage: "Documentation is thin. Add module docstrings and usage examples, then regenerate the Documentation tab.",
  architecture_stability: "Core contracts are drifting. Freeze the graph service interfaces and record decisions as ADRs.",
  deployment_safety: "Harden the release path with smoke tests and a staged rollout gate before production.",
  ownership_clarity: "Ownership is fragmented. Assign module owners in CODEOWNERS to cut review latency.",
  tech_debt: "Tech-debt is accruing. Schedule a paydown sprint targeting the modules with rising coupling.",
  confidence: "Signal confidence is low. Ingest more commit and incident history so the graph can calibrate.",
};

type Metric = { key: string; label: string; value: number };

function Analysis({ score, metrics }: { score: number; metrics: Metric[] }) {
  const strong = metrics.filter((m) => m.value >= 0.75);
  const weak = [...metrics].filter((m) => m.value < 0.7).sort((a, b) => a.value - b.value);
  const verdict = score >= 75 ? "in good health" : score >= 50 ? "holding, with clear pressure points" : "at risk";

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.3, ease: EASE_OUT }}
    >
      <span className="status-line">Detailed analysis</span>
      <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-ink-soft">
        The repository scores <span className="num font-medium text-ink">{score}/100</span> and is {verdict}.
        {strong.length > 0 && (
          <>
            {" "}
            Its strongest signals are{" "}
            <span className="text-ink">{strong.slice(0, 3).map((m) => m.label.toLowerCase()).join(", ")}</span>.
          </>
        )}
        {weak.length > 0 && (
          <>
            {" "}
            The clearest pressure points are{" "}
            <span className="text-ink">{weak.slice(0, 3).map((m) => m.label.toLowerCase()).join(", ")}</span>,
            each below the 70% line.
          </>
        )}
      </p>

      <h3 className="status-line mt-10">Suggestions</h3>
      {weak.length === 0 ? (
        <p className="mt-3 text-sm text-muted">No metric falls below target. Hold the line and keep ingesting history.</p>
      ) : (
        <ol className="mt-4 space-y-4">
          {weak.map((m, i) => (
            <li key={m.key} className="flex gap-4">
              <span className="num mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-paper-sunk text-[11px] text-ink-soft">
                {i + 1}
              </span>
              <div>
                <p className="text-sm font-medium text-ink">
                  {m.label} <span className="num font-normal text-faint">· {Math.round(m.value * 100)}</span>
                </p>
                <p className="mt-0.5 max-w-2xl text-sm leading-relaxed text-muted">
                  {SUGGESTIONS[m.key] ?? "Investigate this signal and add coverage where the graph shows gaps."}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </motion.section>
  );
}

function MetricBar({ label, value, index }: { label: string; value: number; index: number }) {
  const pct = Math.round(value * 100);
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-sm text-ink-soft">{label}</span>
        <span className="num text-xs text-muted">{pct}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-paper-sunk">
        <motion.div
          className="h-full rounded-full bg-ink"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, delay: 0.15 + index * 0.05, ease: EASE_OUT }}
        />
      </div>
    </div>
  );
}
