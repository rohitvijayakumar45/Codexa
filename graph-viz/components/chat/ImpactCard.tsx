"use client";

import { motion } from "framer-motion";
import { ArrowRight, ShieldCheck, AlertTriangle } from "lucide-react";
import type { ImpactResult } from "@/lib/api";
import { Button, EASE_OUT } from "@/components/ui/primitives";

const RISK: Record<string, { color: string; bg: string; fill: number }> = {
  None: { color: "var(--color-muted)", bg: "var(--color-paper-sunk)", fill: 0.08 },
  Low: { color: "var(--color-signal)", bg: "var(--color-signal-wash)", fill: 0.3 },
  Medium: { color: "var(--color-gold)", bg: "var(--color-gold-wash)", fill: 0.55 },
  // Tinted from the theme's own colour, so both themes get a readable badge (hex light tints stayed
  // light in Noir).
  High: { color: "var(--color-warn)", bg: "color-mix(in srgb, var(--color-warn) 15%, transparent)", fill: 0.8 },
  Critical: { color: "var(--color-danger)", bg: "color-mix(in srgb, var(--color-danger) 15%, transparent)", fill: 1 },
};

export function ImpactCard({
  impact,
  pending,
  onProceed,
  onCancel,
}: {
  impact: ImpactResult;
  pending: boolean;
  onProceed: () => void;
  onCancel: () => void;
}) {
  const risk = RISK[impact.risk_level] ?? RISK.None;
  const filesTouched = impact.files_touched ?? 0;
  const callEdges = impact.call_edges ?? 0;
  const importEdges = impact.import_edges ?? 0;
  const couplingPairs = Math.round((impact.coupling_edges ?? 0) / 2);
  const maxDepthReached = impact.max_depth_reached ?? 0;
  const breakdown = impact.breakdown ?? {};
  const composes = impact.composes ?? 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: EASE_OUT }}
      className="mb-6 overflow-hidden rounded-2xl border border-line bg-panel shadow-md"
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-3">
        <span className="status-line">Blast radius</span>
        <span
          className="rounded-full px-2.5 py-1 text-[11px] font-semibold"
          style={{ background: risk.bg, color: risk.color }}
        >
          {impact.risk_level} risk
        </span>
      </div>

      <div className="px-5 py-4">
        {impact.risk_reason ? <p className="mb-4 text-[13px] leading-relaxed text-ink-soft">{impact.risk_reason}</p> : null}
        <div className="flex items-end gap-6">
          <div>
            <span className="num text-4xl font-medium leading-none text-ink">{impact.affected_count}</span>
            <p className="status-line mt-1.5">downstream affected</p>
          </div>
          <div className="pb-1">
            <span className="num text-lg font-medium text-ink">{Math.round(impact.confidence * 100)}%</span>
            <p className="status-line mt-0.5">confidence</p>
          </div>
          <div className="flex-1 pb-2">
            <div className="h-1.5 overflow-hidden rounded-full bg-paper-sunk">
              <motion.div
                className="h-full rounded-full"
                style={{ background: risk.color }}
                initial={{ width: 0 }}
                animate={{ width: `${Math.max(6, impact.risk_score * 100)}%` }}
                transition={{ duration: 0.7, ease: EASE_OUT }}
              />
            </div>
          </div>
        </div>

        {(filesTouched > 0 || callEdges > 0 || importEdges > 0 || couplingPairs > 0 || composes > 0) && (
          <div className="mt-4 flex flex-wrap gap-4 border-t border-line pt-3">
            {filesTouched > 0 && <Metric value={filesTouched} label="files" />}
            {composes > 0 && <Metric value={composes} label={impact.root_component ? "files it renders" : "files it imports"} />}
            {callEdges > 0 && <Metric value={callEdges} label="function calls" />}
            {importEdges > 0 && <Metric value={importEdges} label="imports" />}
            {couplingPairs > 0 && <Metric value={couplingPairs} label="hidden coupling" />}
            {maxDepthReached > 0 && <Metric value={maxDepthReached} label="hops deep" />}
          </div>
        )}

        {Object.keys(breakdown).length > 0 && (
          <div className="mt-4">
            <p className="status-line mb-1.5">Affected by type</p>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(breakdown).map(([type, count]) => (
                <span key={type} className="num rounded-md border border-line bg-paper-sunk px-2 py-1 text-[11px] text-ink-soft">
                  {count} {type}
                  {count !== 1 ? "s" : ""}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="mt-4">
          <p className="status-line mb-1.5">Change targets</p>
          <div className="flex flex-wrap gap-1.5">
            {impact.targets.map((t) => (
              <span key={t.id} className="num rounded-md border border-line bg-paper-sunk px-2 py-1 text-[11px] text-ink-soft">
                {t.label}
              </span>
            ))}
          </div>
        </div>

        {impact.paths_preview.length > 0 && (
          <div className="mt-4">
            <p className="status-line mb-1.5">Propagation</p>
            <ul className="space-y-1">
              {impact.paths_preview.map((chain, i) => (
                <li key={i} className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
                  {chain.map((label, j) => (
                    <span key={j} className="flex items-center gap-1.5">
                      {j > 0 && <ArrowRight size={11} className="text-faint" />}
                      <span className="num text-ink-soft">{label}</span>
                    </span>
                  ))}
                </li>
              ))}
            </ul>
          </div>
        )}

        {impact.coupling_risks.length > 0 && (
          <div
            className="mt-4 rounded-lg border border-line-strong p-3"
            style={{ background: "color-mix(in srgb, var(--color-warn) 12%, transparent)" }}
          >
            <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold text-[var(--color-warn)]">
              <AlertTriangle size={12} />
              Historically risky — coupled with a real incident
            </p>
            <ul className="space-y-2">
              {impact.coupling_risks.map((r, i) => (
                <li key={i} className="text-[11px] text-ink-soft">
                  <span className="num font-medium">{r.file_label}</span> is git-coupled to a file
                  whose root cause was &ldquo;{r.root_cause_summary}&rdquo;
                  {r.incident_summary ? ` — incident: ${r.incident_summary}` : ""}
                  {r.prevention_rule ? (
                    <span className="block text-faint">Prevention rule: {r.prevention_rule}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {pending ? (
        <div className="flex items-center justify-between gap-3 border-t border-line bg-panel-2 px-5 py-3">
          <span className="text-xs text-muted">Review the impact, then decide.</span>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onCancel} className="px-3 py-1.5 text-xs">
              Cancel
            </Button>
            <Button onClick={onProceed} className="px-3 py-1.5 text-xs">
              Proceed <ArrowRight size={13} />
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2 border-t border-line bg-panel-2 px-5 py-2.5 text-xs text-signal">
          <ShieldCheck size={14} />
          Approved — planning the change
        </div>
      )}
    </motion.div>
  );
}

function Metric({ value, label }: { value: number; label: string }) {
  return (
    <div>
      <span className="num text-base font-medium leading-none text-ink">{value}</span>
      <p className="status-line mt-1">{label}</p>
    </div>
  );
}
