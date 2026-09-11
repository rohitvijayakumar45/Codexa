"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { AlertTriangle, ShieldAlert, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { useRepoStore } from "@/lib/repo-store";
import { PageHeader } from "@/components/shell/PageHeader";
import { CenteredError, CenteredLoading, CenteredEmpty } from "@/components/shell/States";
import { EASE_OUT } from "@/components/ui/primitives";

/*
  Repository score — the verdict first, then why, then what to do.

  Everything shown is measured: the score and its components, the backend's per-component reasoning,
  the raw facts it measured, and where this repository sits among every repository Codexa has
  ingested. Verdict colour is semantic (ink / warn / danger) and always paired with an icon and a
  word — the theme signal colour is reserved for live agent state and never appears here.
*/

const TARGET = 0.7;

const METRIC_LABEL: Record<string, string> = {
  maintainability: "Maintainability",
  testability: "Testability",
  test_coverage: "Test coverage",
  coupling: "Decoupling",
  modularity: "Modularity",
  doc_coverage: "Documentation",
  documentation: "Documentation",
  type_safety: "Type safety",
  structure: "Structure",
  architecture_stability: "Architecture stability",
  deployment_safety: "Deployment safety",
  ownership_clarity: "Ownership clarity",
  tech_debt: "Tech-debt headroom",
  confidence: "Signal confidence",
};

const MEASURED_LABEL: Record<string, { label: string; fmt?: (v: number) => string }> = {
  source_files: { label: "Source files" },
  test_files: { label: "Test files" },
  avg_loc: { label: "Lines per file", fmt: (v) => v.toFixed(0) },
  avg_imports: { label: "Imports per file", fmt: (v) => v.toFixed(1) },
  ts_files: { label: "TypeScript files" },
};

const SUGGESTIONS: Record<string, string> = {
  maintainability: "Break up the largest modules and reduce cyclomatic complexity in the hotspots the graph flags.",
  testability: "Introduce seams and dependency injection around the core services so they can be unit-tested in isolation.",
  test_coverage: "Add unit tests around the core modules first — they carry the most risk per line.",
  coupling: "Inter-module coupling is high. Extract interfaces and break the cyclic imports surfaced in the graph.",
  doc_coverage: "Documentation is thin. Add module docstrings and usage examples, then regenerate the Documentation tab.",
  documentation: "Documentation is thin. Add a README with setup and usage, plus per-module docs.",
  architecture_stability: "Core contracts are drifting. Freeze the graph service interfaces and record decisions as ADRs.",
  deployment_safety: "Harden the release path with smoke tests and a staged rollout gate before production.",
  ownership_clarity: "Ownership is fragmented. Assign module owners in CODEOWNERS to cut review latency.",
  tech_debt: "Tech-debt is accruing. Schedule a paydown sprint targeting the modules with rising coupling.",
  confidence: "Signal confidence is low. Ingest more commit and incident history so the graph can calibrate.",
  type_safety: "Add types at module boundaries first; that is where untyped code causes the most bugs.",
  structure: "Organise code into conventional directories (src, components, services, tests).",
};

type Verdict = { word: string; color: string; Icon: typeof ShieldCheck; sentence: string };
function verdictFor(score: number): Verdict {
  if (score >= 75)
    return { word: "Healthy", color: "var(--color-ink)", Icon: ShieldCheck, sentence: "in good health" };
  if (score >= 50)
    return { word: "Watch", color: "var(--color-warn)", Icon: AlertTriangle, sentence: "holding, with clear pressure points" };
  return { word: "At risk", color: "var(--color-danger)", Icon: ShieldAlert, sentence: "at risk" };
}

type Metric = { key: string; label: string; value: number; reason?: string };

export default function RepositoryPage() {
  const activeRepo = useRepoStore((s) => s.activeRepo);
  const q = useQuery({ queryKey: ["nodes", activeRepo], queryFn: () => api.nodes(activeRepo) });
  const snapsQ = useQuery({ queryKey: ["snapshots"], queryFn: api.snapshots });

  const health = useMemo(() => {
    const node = (q.data ?? []).find((n) => n.node_type === "HealthMetric");
    if (!node) return null;
    const props = node.properties as {
      repository?: string;
      score?: number;
      components?: Record<string, number>;
      reasoning?: Record<string, string>;
      suggestions?: string[];
      measured?: Record<string, number>;
    };
    return {
      repository: props.repository ?? activeRepo,
      score: props.score ?? 0,
      components: props.components ?? {},
      reasoning: props.reasoning ?? {},
      suggestions: props.suggestions ?? [],
      measured: props.measured ?? {},
    };
  }, [q.data, activeRepo]);

  // Latest score per repository, from every ingestion Codexa has recorded.
  const portfolio = useMemo(() => {
    const latest = new Map<string, { repo: string; score: number; at: number }>();
    for (const s of snapsQ.data ?? []) {
      const at = Date.parse(s.at);
      const prev = latest.get(s.repository);
      if (!prev || at >= prev.at) latest.set(s.repository, { repo: s.repository, score: s.score, at });
    }
    return [...latest.values()];
  }, [snapsQ.data]);

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
  const v = verdictFor(score100);
  const metrics: Metric[] = Object.entries(health.components)
    .map(([key, value]) => ({ key, label: METRIC_LABEL[key] ?? key.replace(/_/g, " "), value, reason: health.reasoning[key] }))
    .sort((a, b) => a.value - b.value);
  const weak = metrics.filter((m) => m.value < TARGET);
  const strong = metrics.filter((m) => m.value >= 0.75).sort((a, b) => b.value - a.value);

  // Rank among repositories: this repo's own health score, not a stale snapshot of it.
  const others = portfolio.filter((p) => p.repo !== health.repository);
  const all = [...others.map((p) => p.score), health.score].sort((a, b) => b - a);
  const rank = all.indexOf(health.score) + 1;

  const measured = Object.entries(health.measured).filter(([k, val]) => MEASURED_LABEL[k] && typeof val === "number");
  const suggestions = health.suggestions.length
    ? health.suggestions
    : weak.map((m) => `${m.label}: ${SUGGESTIONS[m.key] ?? "Investigate this signal and add coverage where the graph shows gaps."}`);

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow="Evaluation" title="Repository score">
        <span className="num text-sm text-muted">
          {health.repository}
          {all.length > 1 ? ` · #${rank} of ${all.length}` : ""}
        </span>
      </PageHeader>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-8 pb-16 pt-10">
          {/* Verdict */}
          <section className="grid gap-10 md:grid-cols-[260px_minmax(0,1fr)] md:items-center">
            <Gauge score={score100} verdict={v} />
            <div>
              <div className="flex items-center gap-2" style={{ color: v.color }}>
                <v.Icon size={18} strokeWidth={2} />
                <span className="text-sm font-semibold">{v.word}</span>
              </div>
              <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-ink-soft">
                <span className="text-ink">{health.repository}</span> scores <span className="num font-medium text-ink">{score100}/100</span> and
                is {v.sentence}.
                {strong.length > 0 && (
                  <>
                    {" "}Strongest: <span className="text-ink">{strong.slice(0, 3).map((m) => m.label.toLowerCase()).join(", ")}</span>.
                  </>
                )}
                {weak.length > 0 && (
                  <>
                    {" "}
                    {weak.length === 1 ? "One signal is" : `${weak.length} signals are`} below the {Math.round(TARGET * 100)} line:{" "}
                    <span className="text-ink">{weak.slice(0, 3).map((m) => m.label.toLowerCase()).join(", ")}</span>
                    {weak.length > 3 ? " and more" : ""}.
                  </>
                )}
              </p>
              {measured.length ? (
                <dl className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                  {measured.map(([k, val]) => (
                    <div key={k} className="rounded-xl border border-line bg-panel-2 px-3 py-2.5">
                      <dd className="num text-lg font-medium leading-none text-ink">
                        {MEASURED_LABEL[k].fmt ? MEASURED_LABEL[k].fmt!(val) : val}
                      </dd>
                      <dt className="mt-1.5 text-[11px] text-muted">{MEASURED_LABEL[k].label}</dt>
                    </div>
                  ))}
                </dl>
              ) : null}
            </div>
          </section>

          {/* Breakdown */}
          <section className="mt-14">
            <div className="flex items-baseline justify-between">
              <h2 className="status-line">Breakdown · weakest first</h2>
              <span className="status-line !normal-case !tracking-normal">tick = target {Math.round(TARGET * 100)}</span>
            </div>
            <ul className="mt-4 divide-y divide-line border-y border-line">
              {metrics.map((m, i) => (
                <MetricRow key={m.key} m={m} index={i} />
              ))}
            </ul>
          </section>

          {/* Portfolio */}
          {all.length > 1 ? (
            <section className="mt-14">
              <div className="flex items-baseline justify-between">
                <h2 className="status-line">Among {all.length} repositories</h2>
                <span className="num text-xs text-muted">
                  rank #{rank} · median {Math.round(median(all) * 100)}
                </span>
              </div>
              <Portfolio others={others} current={{ repo: health.repository, score: health.score }} />
            </section>
          ) : null}

          {/* Actions */}
          <section className="mt-14">
            <h2 className="status-line">What to do next · highest impact first</h2>
            {suggestions.length === 0 ? (
              <p className="mt-3 text-sm text-muted">No signal falls below target. Hold the line and keep ingesting history.</p>
            ) : (
              <ol className="mt-4 space-y-3">
                {suggestions.map((s, i) => {
                  const [head, ...rest] = s.split(": ");
                  const hasHead = rest.length > 0 && head.length < 40;
                  return (
                    <li key={i} className="grid grid-cols-[28px_minmax(0,1fr)] gap-3">
                      <span className="num mt-0.5 grid h-6 w-6 place-items-center rounded-full bg-paper-sunk text-[11px] text-ink-soft">{i + 1}</span>
                      <p className="max-w-2xl text-sm leading-relaxed text-ink-soft">
                        {hasHead ? (
                          <>
                            <span className="font-medium text-ink">{head}.</span> {rest.join(": ")}
                          </>
                        ) : (
                          s
                        )}
                      </p>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function median(xs: number[]) {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function Gauge({ score, verdict }: { score: number; verdict: Verdict }) {
  const r = 96;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative mx-auto h-[220px] w-[220px]">
      <svg viewBox="0 0 220 220" className="h-full w-full -rotate-90" aria-hidden>
        <circle cx="110" cy="110" r={r} fill="none" stroke="var(--color-paper-sunk)" strokeWidth="12" />
        {/* Target tick at 70. */}
        <line
          x1={110 + (r - 9) * Math.cos(TARGET * 2 * Math.PI)}
          y1={110 + (r - 9) * Math.sin(TARGET * 2 * Math.PI)}
          x2={110 + (r + 9) * Math.cos(TARGET * 2 * Math.PI)}
          y2={110 + (r + 9) * Math.sin(TARGET * 2 * Math.PI)}
          stroke="var(--color-faint)"
          strokeWidth="2"
        />
        <motion.circle
          cx="110"
          cy="110"
          r={r}
          fill="none"
          stroke={verdict.color}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c - (score / 100) * c }}
          transition={{ duration: 1.1, ease: EASE_OUT }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="display text-[64px] font-semibold leading-none text-ink">{score}</span>
        <span className="status-line mt-1">out of 100</span>
      </div>
    </div>
  );
}

function MetricRow({ m, index }: { m: Metric; index: number }) {
  const pct = Math.round(m.value * 100);
  const below = m.value < TARGET;
  return (
    <li className="grid grid-cols-1 gap-x-8 gap-y-1.5 py-3.5 md:grid-cols-[200px_minmax(0,1fr)]">
      <div className="flex items-center gap-2">
        {below ? <AlertTriangle size={13} className="shrink-0 text-warn" aria-label="Below target" /> : <span className="w-[13px]" />}
        <span className={`text-sm ${below ? "text-ink" : "text-ink-soft"}`}>{m.label}</span>
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-3">
          <div className="relative h-1.5 flex-1 rounded-full bg-paper-sunk">
            <motion.div
              className="h-full rounded-full"
              style={{ background: below ? "var(--color-warn)" : "var(--color-ink-soft)" }}
              initial={{ width: 0 }}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.8, delay: 0.1 + index * 0.04, ease: EASE_OUT }}
            />
            <span className="absolute -top-1 h-3.5 w-px bg-faint" style={{ left: `${TARGET * 100}%` }} aria-hidden />
          </div>
          <span className="num w-8 text-right text-xs text-ink">{pct}</span>
        </div>
        {m.reason ? <p className="mt-1 text-[12px] leading-snug text-muted">{m.reason}</p> : null}
      </div>
    </li>
  );
}

function Portfolio({
  others,
  current,
}: {
  others: { repo: string; score: number }[];
  current: { repo: string; score: number };
}) {
  const [hover, setHover] = useState<{ repo: string; score: number } | null>(null);
  const W = 1000;
  const X0 = 20;
  const X1 = W - 20;
  const x = (s: number) => X0 + s * (X1 - X0);
  // Stack dots that would overlap so every repository stays visible.
  const placed: { repo: string; score: number; cx: number; cy: number }[] = [];
  for (const o of [...others].sort((a, b) => a.score - b.score)) {
    const cx = x(o.score);
    let lane = 0;
    while (placed.some((p) => Math.abs(p.cx - cx) < 11 && p.cy === 40 - lane * 11)) lane++;
    placed.push({ ...o, cx, cy: 40 - Math.min(lane, 3) * 11 });
  }
  const shown = hover ?? current;
  return (
    <div className="mt-4">
      <svg viewBox={`0 0 ${W} 74`} className="block w-full" role="img" aria-label="Scores of all ingested repositories">
        <line x1={X0} x2={X1} y1={50} y2={50} stroke="var(--color-line-strong)" />
        {[0, 0.25, 0.5, 0.7, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={47} y2={53} stroke={t === 0.7 ? "var(--color-faint)" : "var(--color-line-strong)"} />
            {t !== 0.7 ? (
              <text x={x(t)} y={68} textAnchor="middle" style={{ font: "10.5px var(--font-mono)", fill: "var(--color-faint)" }}>
                {Math.round(t * 100)}
              </text>
            ) : null}
          </g>
        ))}
        {placed.map((p) => (
          <circle
            key={p.repo}
            cx={p.cx}
            cy={p.cy}
            r={4.5}
            style={{ fill: "var(--color-faint)", opacity: hover && hover.repo !== p.repo ? 0.4 : 0.85, cursor: "default" }}
            onMouseEnter={() => setHover(p)}
            onMouseLeave={() => setHover(null)}
          >
            <title>{`${p.repo} · ${Math.round(p.score * 100)}`}</title>
          </circle>
        ))}
        <circle cx={x(current.score)} cy={40} r={8} fill="var(--color-panel)" stroke="var(--color-ink)" strokeWidth={2} />
        <circle cx={x(current.score)} cy={40} r={3.5} fill="var(--color-ink)" />
      </svg>
      <p className="mt-1 text-xs text-muted">
        <span className="font-medium text-ink">{shown.repo}</span>{" "}
        <span className="num">{Math.round(shown.score * 100)}</span>
        {hover ? "" : " — this repository (ringed). Hover a dot for another."}
      </p>
    </div>
  );
}
